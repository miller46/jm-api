package server

import (
	"context"
	"errors"
	"fmt"
	"io/fs"
	"log/slog"
	"net/http"
	"net/http/pprof"
	"runtime"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/cors"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/redis/go-redis/v9"

	"github.com/jack/jm-api-go/internal/config"
	"github.com/jack/jm-api-go/internal/db/sqlc"
	"github.com/jack/jm-api-go/internal/dbconn"
	"github.com/jack/jm-api-go/internal/handler"
	"github.com/jack/jm-api-go/internal/middleware"
	"github.com/jack/jm-api-go/internal/observability"
	"github.com/jack/jm-api-go/internal/service"
	"github.com/jack/jm-api-go/static"
)

type Server struct {
	cfg           *config.Config
	router        chi.Router
	db            *pgxpool.Pool
	redis         *redis.Client
	redisLastErr  error
	redisFailures uint64
	shutdownGuard *middleware.ShutdownGuard
	queries       *sqlc.Queries
	authService   *service.AuthService
	webhookSvc    *service.WebhookService
	cleanupCancel chan struct{}
}

func New(cfg *config.Config) (*Server, error) {
	s := &Server{
		cfg:           cfg,
		router:        chi.NewRouter(),
		shutdownGuard: middleware.NewShutdownGuard(),
	}

	// Setup logging
	observability.SetupLogging(cfg.LogLevel, cfg.LogJSON, cfg.LogSampleRate)

	// Setup database
	if err := s.setupDB(); err != nil {
		return nil, fmt.Errorf("setting up database: %w", err)
	}

	// Setup Redis (optional)
	if cfg.RedisURL != "" {
		s.setupRedis(cfg)
	}

	// Setup services
	s.queries = sqlc.New(sqlc.WithQueryTimeout(s.db, cfg.QueryTimeout))
	s.authService = service.NewAuthService(
		s.queries,
		cfg.JWTSigningKeys,
		cfg.JWTAlgorithm,
		cfg.JWTAccessTokenExpireMin,
		cfg.JWTRefreshTokenExpireDays,
	)

	var cbConfig *service.CircuitBreakerConfig
	if cfg.CircuitBreakerEnabled {
		cbConfig = &service.CircuitBreakerConfig{
			MaxRequests:        cfg.CircuitBreakerMaxRequests,
			Interval:           cfg.CircuitBreakerInterval,
			Timeout:            cfg.CircuitBreakerTimeout,
			FailureThreshold:   cfg.CircuitBreakerFailureThreshold,
			MinRequests:        cfg.CircuitBreakerMinRequests,
			ConsecutiveFailure: cfg.CircuitBreakerConsecutiveFailures,
			OpenDuration:       cfg.CircuitBreakerOpenDuration,
		}
	}
	s.webhookSvc = service.NewWebhookService(s.queries, cbConfig)

	s.setupProfiling()
	s.setupRoutes()

	// Start session cleanup with cancellable context
	s.cleanupCancel = make(chan struct{})
	go s.sessionCleanupLoop(cfg.SessionCleanupIntervalSec)

	return s, nil
}

func (s *Server) setupDB() error {
	pool, err := dbconn.ConnectWithRetry(context.Background(), s.cfg)
	if err != nil {
		return err
	}

	s.db = pool
	slog.Info("database connected", "db_pool_max_conns", s.cfg.DBPoolMaxConns, "db_pool_min_conns", s.cfg.DBPoolMinConns)
	return nil
}

func (s *Server) setupRedis(cfg *config.Config) {
	s.redis = redis.NewClient(&redis.Options{
		Addr:         fmt.Sprintf("%s:%d", cfg.RedisURL, cfg.RedisPort),
		Password:     cfg.RedisPassword,
		DB:           cfg.RedisDB,
		PoolSize:     cfg.RedisConnPoolSize,
		MaxIdleConns: cfg.RedisConnPoolMax,
		DialTimeout:  time.Duration(cfg.RedisConnectTimeout) * time.Second,
		ReadTimeout:  time.Duration(cfg.RedisSocketTimeout) * time.Second,
	})
	if err := s.redis.Ping(context.Background()).Err(); err != nil {
		s.redisLastErr = err
		s.redisFailures++
		observability.RecordRedisConnectionFailure("startup")
		slog.Error("redis.connection.failed",
			"timestamp", time.Now().UTC().Format(time.RFC3339Nano),
			"error", err.Error(),
			"retry_count", s.redisFailures,
			"required", cfg.RedisRequired,
		)
		s.redis = nil
	} else {
		s.redisLastErr = nil
		slog.Info("redis connected")
	}
}

func (s *Server) redisHealthCheck(ctx context.Context) error {
	if s.redis == nil {
		if s.redisLastErr != nil {
			return s.redisLastErr
		}
		return errors.New("redis not configured")
	}

	if err := s.redis.Ping(ctx).Err(); err != nil {
		s.redisLastErr = err
		s.redisFailures++
		observability.RecordRedisConnectionFailure("healthcheck")
		slog.Error("redis.connection.failed",
			"timestamp", time.Now().UTC().Format(time.RFC3339Nano),
			"error", err.Error(),
			"retry_count", s.redisFailures,
			"required", s.cfg.RedisRequired,
		)
		return err
	}

	s.redisLastErr = nil
	return nil
}

func (s *Server) Router() chi.Router {
	return s.router
}

func (s *Server) StartShutdown() {
	s.shutdownGuard.StartShutdown()
}

func (s *Server) Close() {
	if s.cleanupCancel != nil {
		close(s.cleanupCancel)
	}
	if s.db != nil {
		s.db.Close()
	}
	if s.redis != nil {
		s.redis.Close()
	}
}

func (s *Server) DB() *pgxpool.Pool {
	return s.db
}

func (s *Server) Queries() *sqlc.Queries {
	return s.queries
}

func (s *Server) setupProfiling() {
	runtime.SetMutexProfileFraction(1)
	runtime.SetBlockProfileRate(1)
}

func registerPprofRoutes(r chi.Router, authMW func(http.Handler) http.Handler) {
	r.Route("/debug/pprof", func(r chi.Router) {
		r.Use(authMW)
		r.Use(middleware.RequireAdmin)

		r.Get("/", pprof.Index)
		r.Get("/cmdline", pprof.Cmdline)
		r.Get("/profile", pprof.Profile)
		r.Get("/symbol", pprof.Symbol)
		r.Post("/symbol", pprof.Symbol)
		r.Get("/trace", pprof.Trace)
		r.Get("/heap", pprof.Handler("heap").ServeHTTP)
		r.Get("/goroutine", pprof.Handler("goroutine").ServeHTTP)
		r.Get("/mutex", pprof.Handler("mutex").ServeHTTP)
		r.Get("/block", pprof.Handler("block").ServeHTTP)
	})
}

func (s *Server) setupRoutes() {
	r := s.router
	cfg := s.cfg

	// Global middleware
	if len(cfg.AllowedHosts) > 0 {
		r.Use(middleware.TrustedHost(cfg.AllowedHosts))
	}
	r.Use(middleware.RequestID(cfg.RequestIDHeader))
	r.Use(middleware.ErrorHandler())
	r.Use(middleware.SecurityHeaders(cfg))
	r.Use(s.shutdownGuard.Middleware)
	r.Use(middleware.BodyLimit(1 << 20)) // 1MB
	r.Use(observability.MetricsMiddleware(cfg.AppName, cfg.AppVersion))

	// CORS
	if len(cfg.AllowOrigins) > 0 {
		r.Use(cors.Handler(cors.Options{
			AllowedOrigins:   cfg.AllowOrigins,
			AllowedMethods:   cfg.CORSAllowMethods,
			AllowedHeaders:   cfg.CORSAllowHeaders,
			AllowCredentials: cfg.CORSAllowCredentials,
		}))
	}

	// Rate limiter
	rateLimiter := middleware.NewRateLimiter(s.redis, middleware.RateLimitConfig{
		PerMinute: cfg.RateLimitAPIPerMinute,
	}, middleware.WithTrustedProxies(cfg.TrustProxyHeaders, cfg.TrustedProxyCIDRs))
	rateLimiter.SetOverride("/login", middleware.RateLimitConfig{PerMinute: 5, Window: 15 * time.Minute})
	rateLimiter.SetOverride("/signup", middleware.RateLimitConfig{PerMinute: 5, Window: 15 * time.Minute})
	rateLimiter.SetOverride("/webhooks/verify", middleware.RateLimitConfig{PerMinute: 10})

	// Handlers
	var healthOpts []handler.HealthOption
	if cfg.DBMigrationCheckEnabled {
		healthOpts = append(healthOpts, handler.WithMigrationCheck(cfg.DBExpectedMigration))
	}
	if cfg.RedisURL != "" || cfg.RedisRequired {
		healthOpts = append(healthOpts, handler.WithRedisCheck(s.redisHealthCheck, cfg.RedisRequired))
	}
	healthH := handler.NewHealthHandler(s.db, healthOpts...)
	authH := handler.NewAuthHandler(s.authService)
	adminH := handler.NewAdminHandler(healthH, s.webhookSvc)
	metaH := handler.NewMetaHandler(cfg)
	botH := handler.NewBotHandler(s.queries, s.webhookSvc)
	webhookH := handler.NewWebhookHandler(s.queries, s.webhookSvc)
	taskH := handler.NewTaskHandler(s.queries)
	scheduledJobH := handler.NewScheduledJobHandler(s.queries)

	// Auth middleware
	authMW := middleware.Auth(cfg.JWTSigningKeys)
	requestValidator := middleware.NewRequestValidator()

	registerPprofRoutes(r, authMW)

	r.Route(cfg.APIV1Prefix, func(r chi.Router) {
		r.Use(rateLimiter.Middleware)
		r.Use(middleware.RequestTimeout(cfg.RequestTimeoutDefault))

		// Public health endpoints
		r.Group(func(r chi.Router) {
			r.Use(middleware.RequestTimeout(cfg.RequestTimeoutHealth))
			r.Get("/live", healthH.Live)
			r.Get("/health", healthH.Health)
			r.Get("/ready", healthH.Ready)
			r.Get("/healthz", healthH.Healthz)
		})

		// CSRF middleware for all mutating routes
		csrfMW := middleware.CSRF

		r.With(middleware.RequestTimeout(cfg.RequestTimeoutWebhook)).Post("/webhooks/verify", webhookH.Verify)

		// Auth routes (mostly public)
		r.Route("/auth", func(r chi.Router) {
			r.Use(middleware.RequestTimeout(cfg.RequestTimeoutAuth))
			r.With(middleware.ValidateBody[handler.LoginRequest](requestValidator)).Post("/login", authH.Login)
			r.With(middleware.ValidateBody[handler.SignupRequest](requestValidator)).Post("/signup", authH.Signup)
			r.Post("/refresh", authH.Refresh)

			r.Group(func(r chi.Router) {
				r.Use(authMW)
				r.Use(csrfMW)
				r.Post("/logout", authH.Logout)
				r.Get("/me", authH.Me)
				r.Get("/sessions", authH.Sessions)
				r.Delete("/sessions/{jti}", authH.RevokeSession)
				r.Post("/sessions/revoke-others", authH.RevokeOtherSessions)
			})
		})

		// Admin routes
		r.Route("/admin", func(r chi.Router) {
			r.Use(authMW)
			r.Use(csrfMW)
			r.Use(middleware.RequireAdmin)
			r.Post("/break", adminH.TriggerBreak)
			r.Post("/break/reset", adminH.ResetBreak)
			r.Get("/break/status", adminH.BreakStatus)
			r.Get("/circuit-breakers", adminH.CircuitBreakerStatus)

			// Scheduled jobs
			r.Route("/scheduled-jobs", func(r chi.Router) {
				r.Get("/", scheduledJobH.List)
				r.Post("/", scheduledJobH.Create)
				r.Get("/{id}", scheduledJobH.Get)
				r.Patch("/{id}", scheduledJobH.Update)
				r.Delete("/{id}", scheduledJobH.Delete)
				r.Post("/{id}/run-now", scheduledJobH.RunNow)
			})
		})

		// Bots - reads are public
		r.Route("/bots", func(r chi.Router) {
			r.Use(middleware.RequestTimeout(cfg.RequestTimeoutBotQuery))
			r.Get("/", botH.List)
			r.Get("/{id}", botH.Get)

			r.Group(func(r chi.Router) {
				r.Use(authMW)
				r.Use(csrfMW)
				if cfg.BotsWriteAdminOnly {
					r.Use(middleware.RequireAdmin)
				}
				r.Post("/", botH.Create)
				r.Patch("/{id}", botH.Update)
				r.Delete("/{id}", botH.Delete)
			})
		})

		// Authenticated routes
		r.Group(func(r chi.Router) {
			r.Use(authMW)
			r.Use(csrfMW)

			r.Route("/webhooks", func(r chi.Router) {
				r.Use(middleware.RequestTimeout(cfg.RequestTimeoutWebhook))
				r.Post("/", webhookH.Create)
				r.Get("/", webhookH.List)
				r.Patch("/{id}", webhookH.Update)
				r.Delete("/{id}", webhookH.Delete)
				r.Get("/{id}/deliveries", webhookH.Deliveries)
			})

			r.Route("/tasks", func(r chi.Router) {
				r.Post("/", taskH.Create)
				r.Get("/{id}", taskH.Get)
			})
		})
	})

	// Root-level health routes (legacy compat)
	r.Group(func(r chi.Router) {
		r.Use(middleware.RequestTimeout(cfg.RequestTimeoutHealth))
		r.Get("/live", healthH.Live)
		r.Get("/health", healthH.Health)
		r.Get("/ready", healthH.Ready)
		r.Get("/healthz", healthH.Healthz)
	})

	// Static admin dashboard
	staticFS, err := fs.Sub(static.Files, ".")
	if err != nil {
		slog.Error("failed to load static files", "error", err)
	} else {
		r.Handle("/admin/*", http.StripPrefix("/admin/", http.FileServer(http.FS(staticFS))))
	}
	r.Handle("/admin", http.RedirectHandler("/admin/", http.StatusMovedPermanently))

	// Outside v1 prefix
	tablesH := handler.NewTablesHandler()
	r.Group(func(r chi.Router) {
		r.Use(middleware.RequestTimeout(cfg.RequestTimeoutDefault))
		r.Get("/api/tables", tablesH.List)
		r.Get("/api/schema", tablesH.Schema)
		r.Get("/api/meta", metaH.Meta)
	})
	r.Handle(cfg.MetricsPath, promhttp.Handler())
}

func (s *Server) sessionCleanupLoop(intervalSec int) {
	ticker := time.NewTicker(time.Duration(intervalSec) * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-s.cleanupCancel:
			return
		case <-ticker.C:
			if err := s.authService.CleanupExpiredSessions(context.Background()); err != nil {
				slog.Error("session cleanup failed", "error", err)
			}
		}
	}
}
