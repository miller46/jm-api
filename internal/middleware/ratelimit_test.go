package middleware

import (
	"net/http"
	"net/http/httptest"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/assert"
)

func TestRateLimiter_AllowsUnderLimit(t *testing.T) {
	rl := NewRateLimiter(nil, RateLimitConfig{PerMinute: 10})

	handler := rl.Middleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest("GET", "/", nil)
	req.RemoteAddr = "1.2.3.4:1234"
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)

	assert.Equal(t, http.StatusOK, rr.Code)
	assert.NotEmpty(t, rr.Header().Get("X-RateLimit-Limit"))
	assert.NotEmpty(t, rr.Header().Get("X-RateLimit-Remaining"))
	assert.NotEmpty(t, rr.Header().Get("X-RateLimit-Reset"))
}

func TestRateLimiter_BlocksOverLimit(t *testing.T) {
	rl := NewRateLimiter(nil, RateLimitConfig{PerMinute: 3})

	handler := rl.Middleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	for i := 0; i < 3; i++ {
		req := httptest.NewRequest("GET", "/", nil)
		req.RemoteAddr = "1.2.3.4:1234"
		rr := httptest.NewRecorder()
		handler.ServeHTTP(rr, req)
		assert.Equal(t, http.StatusOK, rr.Code)
	}

	// 4th request should be blocked
	req := httptest.NewRequest("GET", "/", nil)
	req.RemoteAddr = "1.2.3.4:1234"
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)

	assert.Equal(t, http.StatusTooManyRequests, rr.Code)
	assert.NotEmpty(t, rr.Header().Get("Retry-After"))
}

func TestRateLimiter_OverrideConfig(t *testing.T) {
	rl := NewRateLimiter(nil, RateLimitConfig{PerMinute: 100})
	rl.SetOverride("/login", RateLimitConfig{PerMinute: 2})

	handler := rl.Middleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	// 2 requests should pass
	for i := 0; i < 2; i++ {
		req := httptest.NewRequest("POST", "/auth/login", nil)
		req.RemoteAddr = "5.6.7.8:1234"
		rr := httptest.NewRecorder()
		handler.ServeHTTP(rr, req)
		assert.Equal(t, http.StatusOK, rr.Code)
	}

	// 3rd should be blocked
	req := httptest.NewRequest("POST", "/auth/login", nil)
	req.RemoteAddr = "5.6.7.8:1234"
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)

	assert.Equal(t, http.StatusTooManyRequests, rr.Code)
}

func TestRateLimiter_ConcurrentBurst_EnforcesLimit(t *testing.T) {
	rl := NewRateLimiter(nil, RateLimitConfig{PerMinute: 10})
	handler := rl.Middleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	var allowed int32
	var throttled int32

	const totalRequests = 50
	start := make(chan struct{})
	var wg sync.WaitGroup

	for i := 0; i < totalRequests; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start

			req := httptest.NewRequest("GET", "/v1/resource", nil)
			req.RemoteAddr = "9.9.9.9:1234"
			rr := httptest.NewRecorder()
			handler.ServeHTTP(rr, req)

			switch rr.Code {
			case http.StatusOK:
				atomic.AddInt32(&allowed, 1)
			case http.StatusTooManyRequests:
				atomic.AddInt32(&throttled, 1)
			}
		}()
	}

	close(start)
	wg.Wait()

	assert.Equal(t, int32(10), allowed)
	assert.Equal(t, int32(totalRequests)-allowed, throttled)
}

func TestRateLimiter_WindowRefill_AllowsAfterReset(t *testing.T) {
	rl := NewRateLimiter(nil, RateLimitConfig{PerMinute: 2, Window: 200 * time.Millisecond})
	handler := rl.Middleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	for i := 0; i < 2; i++ {
		req := httptest.NewRequest("GET", "/", nil)
		req.RemoteAddr = "7.7.7.7:1234"
		rr := httptest.NewRecorder()
		handler.ServeHTTP(rr, req)
		assert.Equal(t, http.StatusOK, rr.Code)
	}

	blockedReq := httptest.NewRequest("GET", "/", nil)
	blockedReq.RemoteAddr = "7.7.7.7:1234"
	blockedRR := httptest.NewRecorder()
	handler.ServeHTTP(blockedRR, blockedReq)
	assert.Equal(t, http.StatusTooManyRequests, blockedRR.Code)

	time.Sleep(250 * time.Millisecond)

	refillReq := httptest.NewRequest("GET", "/", nil)
	refillReq.RemoteAddr = "7.7.7.7:1234"
	refillRR := httptest.NewRecorder()
	handler.ServeHTTP(refillRR, refillReq)
	assert.Equal(t, http.StatusOK, refillRR.Code)
}

func TestRateLimiter_RedisUnavailable_FailsOpen(t *testing.T) {
	redisClient := redis.NewClient(&redis.Options{
		Addr:         "127.0.0.1:0",
		DialTimeout:  5 * time.Millisecond,
		ReadTimeout:  5 * time.Millisecond,
		WriteTimeout: 5 * time.Millisecond,
		MaxRetries:   0,
	})
	t.Cleanup(func() { _ = redisClient.Close() })

	rl := NewRateLimiter(redisClient, RateLimitConfig{PerMinute: 1})
	handler := rl.Middleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	for i := 0; i < 3; i++ {
		req := httptest.NewRequest("GET", "/", nil)
		req.RemoteAddr = "8.8.8.8:1234"
		rr := httptest.NewRecorder()
		handler.ServeHTTP(rr, req)
		assert.Equal(t, http.StatusOK, rr.Code)
	}
}
