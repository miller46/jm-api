package middleware

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/redis/go-redis/v9"
)

type RateLimitConfig struct {
	PerMinute int
	Window    time.Duration // custom window for PerMinute limit; defaults to time.Minute
}

type RateLimiter struct {
	redis             *redis.Client
	config            RateLimitConfig
	overrides         map[string]RateLimitConfig
	mu                sync.RWMutex
	trustProxyHeaders bool
	trustedProxyCIDRs []*net.IPNet
	// In-memory fallback for development
	memStore map[string][]time.Time
	memMu    sync.Mutex
}

type RateLimiterOption func(*RateLimiter)

func WithTrustedProxies(trust bool, cidrs []*net.IPNet) RateLimiterOption {
	return func(rl *RateLimiter) {
		rl.trustProxyHeaders = trust
		rl.trustedProxyCIDRs = cidrs
	}
}

func NewRateLimiter(redisClient *redis.Client, cfg RateLimitConfig, opts ...RateLimiterOption) *RateLimiter {
	rl := &RateLimiter{
		redis:     redisClient,
		config:    cfg,
		overrides: make(map[string]RateLimitConfig),
		memStore:  make(map[string][]time.Time),
	}
	for _, opt := range opts {
		opt(rl)
	}
	if redisClient == nil {
		go rl.cleanupLoop()
	}
	return rl
}

func (rl *RateLimiter) cleanupLoop() {
	ticker := time.NewTicker(5 * time.Minute)
	defer ticker.Stop()
	for range ticker.C {
		rl.memMu.Lock()
		now := time.Now()
		for key, entries := range rl.memStore {
			valid := entries[:0]
			for _, t := range entries {
				if now.Sub(t) < time.Hour {
					valid = append(valid, t)
				}
			}
			if len(valid) == 0 {
				delete(rl.memStore, key)
			} else {
				rl.memStore[key] = valid
			}
		}
		rl.memMu.Unlock()
	}
}

func (rl *RateLimiter) SetOverride(pattern string, cfg RateLimitConfig) {
	rl.mu.Lock()
	defer rl.mu.Unlock()
	rl.overrides[pattern] = cfg
}

func (rl *RateLimiter) Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		key := rl.extractKey(r)
		cfg := rl.getConfig(r.URL.Path)

		window := cfg.Window
		if window == 0 {
			window = time.Minute
		}
		allowed, remaining, resetAt := rl.check(r.Context(), key, cfg.PerMinute, window)
		if !allowed {
			w.Header().Set("X-RateLimit-Limit", strconv.Itoa(cfg.PerMinute))
			w.Header().Set("X-RateLimit-Remaining", "0")
			w.Header().Set("X-RateLimit-Reset", strconv.FormatInt(resetAt.Unix(), 10))
			w.Header().Set("Retry-After", strconv.Itoa(int(time.Until(resetAt).Seconds())+1))
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusTooManyRequests)
			json.NewEncoder(w).Encode(map[string]string{"error": "rate limit exceeded"})
			return
		}

		w.Header().Set("X-RateLimit-Limit", strconv.Itoa(cfg.PerMinute))
		w.Header().Set("X-RateLimit-Remaining", strconv.Itoa(remaining))
		w.Header().Set("X-RateLimit-Reset", strconv.FormatInt(resetAt.Unix(), 10))

		next.ServeHTTP(w, r)
	})
}

func (rl *RateLimiter) extractKey(r *http.Request) string {
	if user := GetUser(r.Context()); user != nil {
		return fmt.Sprintf("user:%s", user.ID)
	}
	ip := r.RemoteAddr
	if rl.trustProxyHeaders && r.Header.Get("X-Forwarded-For") != "" {
		if rl.isFromTrustedProxy(r.RemoteAddr) {
			forwarded := r.Header.Get("X-Forwarded-For")
			ip = strings.TrimSpace(strings.Split(forwarded, ",")[0])
		}
	}
	if idx := strings.LastIndex(ip, ":"); idx != -1 {
		if parsed := ip[:idx]; parsed != "" {
			ip = parsed
		}
	}
	return fmt.Sprintf("ip:%s", ip)
}

func (rl *RateLimiter) isFromTrustedProxy(remoteAddr string) bool {
	host, _, err := net.SplitHostPort(remoteAddr)
	if err != nil {
		host = remoteAddr
	}
	ip := net.ParseIP(host)
	if ip == nil {
		return false
	}
	for _, cidr := range rl.trustedProxyCIDRs {
		if cidr.Contains(ip) {
			return true
		}
	}
	return false
}

func (rl *RateLimiter) getConfig(path string) RateLimitConfig {
	rl.mu.RLock()
	defer rl.mu.RUnlock()
	for pattern, cfg := range rl.overrides {
		if strings.HasSuffix(path, pattern) || strings.Contains(path, pattern) {
			return cfg
		}
	}
	return rl.config
}

func (rl *RateLimiter) check(ctx context.Context, key string, limit int, window time.Duration) (bool, int, time.Time) {
	now := time.Now()
	resetAt := now.Add(window)

	if rl.redis != nil {
		return rl.checkRedis(ctx, key, limit, window, now, resetAt)
	}
	return rl.checkMemory(key, limit, window, now, resetAt)
}

func (rl *RateLimiter) checkRedis(ctx context.Context, key string, limit int, window time.Duration, now time.Time, resetAt time.Time) (bool, int, time.Time) {
	redisKey := fmt.Sprintf("ratelimit:%s:%d", key, now.Unix()/int64(window.Seconds()))

	pipe := rl.redis.Pipeline()
	incrCmd := pipe.Incr(ctx, redisKey)
	pipe.Expire(ctx, redisKey, window)
	_, err := pipe.Exec(ctx)
	if err != nil {
		// On error, allow the request
		return true, limit - 1, resetAt
	}

	count := int(incrCmd.Val())
	if count > limit {
		return false, 0, resetAt
	}
	return true, limit - count, resetAt
}

func (rl *RateLimiter) checkMemory(key string, limit int, window time.Duration, now time.Time, resetAt time.Time) (bool, int, time.Time) {
	rl.memMu.Lock()
	defer rl.memMu.Unlock()

	windowStart := now.Add(-window)
	entries := rl.memStore[key]

	// Prune old entries
	valid := entries[:0]
	for _, t := range entries {
		if t.After(windowStart) {
			valid = append(valid, t)
		}
	}

	if len(valid) >= limit {
		rl.memStore[key] = valid
		return false, 0, resetAt
	}

	valid = append(valid, now)
	rl.memStore[key] = valid
	return true, limit - len(valid), resetAt
}
