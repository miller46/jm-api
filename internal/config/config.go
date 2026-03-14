package config

import (
	"fmt"
	"net"
	"os"
	"strconv"
	"strings"
	"time"
)

type Config struct {
	AppName     string
	AppVersion  string
	Environment string
	Debug       bool

	DatabaseURL             string
	DBMigrationCheckEnabled bool
	DBExpectedMigration     int

	APIV1Prefix string

	// Request/Security
	RequestIDHeader                     string
	SecurityHeadersEnabled              bool
	SecurityHeaderXContentTypeOptions   string
	SecurityHeaderXFrameOptions         string
	SecurityHeaderHSTSMaxAge            int
	SecurityHeaderHSTSIncludeSubdomains bool
	SecurityHeaderHSTSPreload           bool
	SecurityHeaderAdminCSP              string

	// CORS
	AllowOrigins         []string
	CORSAllowCredentials bool
	CORSAllowMethods     []string
	CORSAllowHeaders     []string

	// Proxy
	AllowedHosts      []string
	TrustProxyHeaders bool
	TrustedProxyCIDRs []*net.IPNet

	// Logging
	LogLevel             string
	LogJSON              bool
	LogSampleRate        float64
	SlowQueryThresholdMS int

	// Tracing
	TracingEnabled        bool
	TracingServiceName    string
	TracingServiceVersion string
	TracingJaegerHost     string
	TracingJaegerPort     int

	// Metrics
	MetricsEnabled bool
	MetricsPath    string

	// Deployment
	GitSHA     string
	DeployedAt string

	// JWT
	JWTSecretKey              string
	JWTSigningKeys            []string
	JWTAlgorithm              string
	JWTAccessTokenExpireMin   int
	JWTRefreshTokenExpireDays int
	SessionCleanupIntervalSec int

	// Bots
	BotsWriteAdminOnly bool
	IUnderstandRisk    bool

	// Rate Limiting
	RateLimitStorageURI   string
	RateLimitAPIPerMinute int

	// Redis
	RedisURL                 string
	RedisPort                int
	RedisPassword            string
	RedisDB                  int
	RedisConnPoolSize        int
	RedisConnPoolMax         int
	RedisSocketTimeout       int
	RedisConnectTimeout      int
	RedisRetryOnTimeout      bool
	RedisHealthCheckInterval int

	// Server
	ServerPort int
	ServerHost string

	// Request timeouts
	RequestTimeoutDefault  time.Duration
	RequestTimeoutBotQuery time.Duration
	RequestTimeoutWebhook  time.Duration
	RequestTimeoutAuth     time.Duration
	RequestTimeoutHealth   time.Duration

	// Graceful shutdown
	ShutdownTimeout time.Duration
}

func Load() (*Config, error) {
	c := &Config{
		AppName:     envOrDefault("JM_API_APP_NAME", "jm-api"),
		AppVersion:  envOrDefault("JM_API_APP_VERSION", "0.1.0"),
		Environment: envOrDefault("JM_API_ENVIRONMENT", "development"),
		Debug:       envBool("JM_API_DEBUG", false),

		DatabaseURL:             os.Getenv("JM_API_DATABASE_URL"),
		DBMigrationCheckEnabled: envBool("JM_API_DB_MIGRATION_CHECK_ENABLED", true),
		DBExpectedMigration:     envInt("JM_API_DB_EXPECTED_MIGRATION", 1),

		APIV1Prefix: envOrDefault("JM_API_API_V1_PREFIX", "/api/v1"),

		RequestIDHeader:                     envOrDefault("JM_API_REQUEST_ID_HEADER", "X-Request-ID"),
		SecurityHeadersEnabled:              envBool("JM_API_SECURITY_HEADERS_ENABLED", true),
		SecurityHeaderXContentTypeOptions:   envOrDefault("JM_API_SECURITY_HEADER_X_CONTENT_TYPE_OPTIONS", "nosniff"),
		SecurityHeaderXFrameOptions:         envOrDefault("JM_API_SECURITY_HEADER_X_FRAME_OPTIONS", "DENY"),
		SecurityHeaderHSTSMaxAge:            envInt("JM_API_SECURITY_HEADER_HSTS_MAX_AGE", 31536000),
		SecurityHeaderHSTSIncludeSubdomains: envBool("JM_API_SECURITY_HEADER_HSTS_INCLUDE_SUBDOMAINS", true),
		SecurityHeaderHSTSPreload:           envBool("JM_API_SECURITY_HEADER_HSTS_PRELOAD", false),
		SecurityHeaderAdminCSP:              envOrDefault("JM_API_SECURITY_HEADER_ADMIN_CSP", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self'; frame-ancestors 'none'"),

		AllowOrigins:         envSlice("JM_API_ALLOW_ORIGINS", nil),
		CORSAllowCredentials: envBool("JM_API_CORS_ALLOW_CREDENTIALS", true),
		CORSAllowMethods:     envSlice("JM_API_CORS_ALLOW_METHODS", []string{"*"}),
		CORSAllowHeaders:     envSlice("JM_API_CORS_ALLOW_HEADERS", []string{"*"}),

		AllowedHosts:      envSlice("JM_API_ALLOWED_HOSTS", nil),
		TrustProxyHeaders: envBool("JM_API_TRUST_PROXY_HEADERS", false),

		LogLevel:             strings.ToUpper(envOrDefault("JM_API_LOG_LEVEL", "INFO")),
		LogJSON:              envBool("JM_API_LOG_JSON", true),
		LogSampleRate:        envFloat("JM_API_LOG_SAMPLE_RATE", 1.0),
		SlowQueryThresholdMS: envInt("JM_API_SLOW_QUERY_THRESHOLD_MS", 500),

		TracingEnabled:        envBool("JM_API_TRACING_ENABLED", false),
		TracingServiceName:    envOrDefault("JM_API_TRACING_SERVICE_NAME", "jm-api"),
		TracingServiceVersion: envOrDefault("JM_API_TRACING_SERVICE_VERSION", "0.1.0"),
		TracingJaegerHost:     envOrDefault("JM_API_TRACING_JAEGER_HOST", "localhost"),
		TracingJaegerPort:     envInt("JM_API_TRACING_JAEGER_PORT", 6831),

		MetricsEnabled: envBool("JM_API_METRICS_ENABLED", true),
		MetricsPath:    envOrDefault("JM_API_METRICS_PATH", "/metrics"),

		GitSHA:     os.Getenv("JM_API_GIT_SHA"),
		DeployedAt: os.Getenv("JM_API_DEPLOYED_AT"),

		JWTSecretKey:              envOrDefault("JM_API_JWT_SECRET_KEY", "change-me-in-production-use-a-long-random-string"),
		JWTAlgorithm:              envOrDefault("JM_API_JWT_ALGORITHM", "HS256"),
		JWTAccessTokenExpireMin:   envInt("JM_API_JWT_ACCESS_TOKEN_EXPIRE_MINUTES", 15),
		JWTRefreshTokenExpireDays: envInt("JM_API_JWT_REFRESH_TOKEN_EXPIRE_DAYS", 7),
		SessionCleanupIntervalSec: envInt("JM_API_SESSION_CLEANUP_INTERVAL_SECONDS", 300),

		BotsWriteAdminOnly: envBool("JM_API_BOTS_WRITE_ADMIN_ONLY", true),
		IUnderstandRisk:    envBool("JM_API_I_UNDERSTAND_RISK", false),

		RateLimitStorageURI:   envOrDefault("JM_API_RATE_LIMIT_STORAGE_URI", "memory://"),
		RateLimitAPIPerMinute: envInt("JM_API_RATE_LIMIT_API_PER_MINUTE", 120),

		RedisURL:                 os.Getenv("JM_API_REDIS_URL"),
		RedisPort:                envInt("JM_API_REDIS_PORT", 6379),
		RedisPassword:            os.Getenv("JM_API_REDIS_PASSWORD"),
		RedisDB:                  envInt("JM_API_REDIS_DB", 0),
		RedisConnPoolSize:        envInt("JM_API_REDIS_CONNECTION_POOL_SIZE", 10),
		RedisConnPoolMax:         envInt("JM_API_REDIS_CONNECTION_POOL_MAX", 20),
		RedisSocketTimeout:       envInt("JM_API_REDIS_SOCKET_TIMEOUT", 5),
		RedisConnectTimeout:      envInt("JM_API_REDIS_SOCKET_CONNECT_TIMEOUT", 5),
		RedisRetryOnTimeout:      envBool("JM_API_REDIS_RETRY_ON_TIMEOUT", true),
		RedisHealthCheckInterval: envInt("JM_API_REDIS_HEALTH_CHECK_INTERVAL", 30),

		ServerPort: envInt("JM_API_SERVER_PORT", envInt("PORT", 8000)),
		ServerHost: envOrDefault("JM_API_SERVER_HOST", "0.0.0.0"),

		RequestTimeoutDefault:  envDuration("JM_API_REQUEST_TIMEOUT_DEFAULT", 30*time.Second),
		RequestTimeoutBotQuery: envDuration("JM_API_REQUEST_TIMEOUT_BOT_QUERY", 10*time.Second),
		RequestTimeoutWebhook:  envDuration("JM_API_REQUEST_TIMEOUT_WEBHOOK", 60*time.Second),
		RequestTimeoutAuth:     envDuration("JM_API_REQUEST_TIMEOUT_AUTH", 5*time.Second),
		RequestTimeoutHealth:   envDuration("JM_API_REQUEST_TIMEOUT_HEALTH", 2*time.Second),

		ShutdownTimeout: time.Duration(envInt("JM_API_SHUTDOWN_TIMEOUT", 30)) * time.Second,
	}

	// Parse JWT signing keys (supports rotation)
	if keys := os.Getenv("JM_API_JWT_SIGNING_KEYS"); keys != "" {
		c.JWTSigningKeys = strings.Split(keys, ",")
	} else {
		c.JWTSigningKeys = []string{c.JWTSecretKey}
	}

	// Parse trusted proxy CIDRs
	if cidrs := os.Getenv("JM_API_TRUSTED_PROXY_CIDRS"); cidrs != "" {
		for _, cidr := range strings.Split(cidrs, ",") {
			cidr = strings.TrimSpace(cidr)
			_, ipNet, err := net.ParseCIDR(cidr)
			if err != nil {
				return nil, fmt.Errorf("invalid trusted proxy CIDR %q: %w", cidr, err)
			}
			c.TrustedProxyCIDRs = append(c.TrustedProxyCIDRs, ipNet)
		}
	}

	if err := c.validate(); err != nil {
		return nil, err
	}

	return c, nil
}

func (c *Config) validate() error {
	if c.DatabaseURL == "" {
		return fmt.Errorf("JM_API_DATABASE_URL is required")
	}

	if c.LogSampleRate <= 0 || c.LogSampleRate > 1 {
		return fmt.Errorf("JM_API_LOG_SAMPLE_RATE must be > 0 and <= 1")
	}

	if c.RequestTimeoutDefault <= 0 || c.RequestTimeoutBotQuery <= 0 || c.RequestTimeoutWebhook <= 0 || c.RequestTimeoutAuth <= 0 || c.RequestTimeoutHealth <= 0 {
		return fmt.Errorf("request timeouts must be > 0")
	}

	isProd := c.Environment == "production" || c.Environment == "staging"
	if isProd {
		if strings.Contains(c.DatabaseURL, "sqlite") {
			return fmt.Errorf("SQLite not allowed in %s; use PostgreSQL", c.Environment)
		}
		if len(c.JWTSecretKey) < 32 {
			return fmt.Errorf("JWT secret key must be >= 32 bytes in %s", c.Environment)
		}
		if c.RateLimitStorageURI == "memory://" {
			return fmt.Errorf("rate limit storage must use Redis in %s", c.Environment)
		}
		if !c.BotsWriteAdminOnly && !c.IUnderstandRisk {
			return fmt.Errorf("bots write must be admin-only in %s (or set JM_API_I_UNDERSTAND_RISK=true)", c.Environment)
		}
		if c.TrustProxyHeaders && len(c.TrustedProxyCIDRs) == 0 {
			return fmt.Errorf("trusted proxy headers requires trusted CIDR list in %s", c.Environment)
		}
	}

	return nil
}

func (c *Config) IsProd() bool {
	return c.Environment == "production" || c.Environment == "staging"
}

func envOrDefault(key, defaultVal string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return defaultVal
}

func envBool(key string, defaultVal bool) bool {
	v := os.Getenv(key)
	if v == "" {
		return defaultVal
	}
	b, err := strconv.ParseBool(v)
	if err != nil {
		return defaultVal
	}
	return b
}

func envInt(key string, defaultVal int) int {
	v := os.Getenv(key)
	if v == "" {
		return defaultVal
	}
	i, err := strconv.Atoi(v)
	if err != nil {
		return defaultVal
	}
	return i
}

func envFloat(key string, defaultVal float64) float64 {
	v := os.Getenv(key)
	if v == "" {
		return defaultVal
	}
	f, err := strconv.ParseFloat(v, 64)
	if err != nil {
		return defaultVal
	}
	return f
}

func envDuration(key string, defaultVal time.Duration) time.Duration {
	v := os.Getenv(key)
	if v == "" {
		return defaultVal
	}
	d, err := time.ParseDuration(v)
	if err != nil {
		return defaultVal
	}
	return d
}

func envSlice(key string, defaultVal []string) []string {
	v := os.Getenv(key)
	if v == "" {
		return defaultVal
	}
	parts := strings.Split(v, ",")
	result := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p != "" {
			result = append(result, p)
		}
	}
	return result
}
