package observability

import (
	"net/http"
	"strconv"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	httpRequestsTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "http_requests_total",
			Help: "Total number of HTTP requests",
		},
		[]string{"service", "version", "method", "endpoint", "status"},
	)

	httpRequestDuration = promauto.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "http_request_duration_seconds",
			Help:    "HTTP request duration in seconds",
			Buckets: []float64{0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10},
		},
		[]string{"service", "version", "method", "endpoint", "status"},
	)

	httpRequestErrors = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "http_request_errors_total",
			Help: "Total number of HTTP request errors",
		},
		[]string{"service", "version", "method", "endpoint", "status"},
	)

	httpRequestTimeouts = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "http_request_timeouts_total",
			Help: "Total number of HTTP request timeouts",
		},
		[]string{"method", "endpoint"},
	)

	redisConnectionFailures = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "redis_connection_failures_total",
			Help: "Total number of Redis connection failures",
		},
		[]string{"stage"},
	)
)

func RecordRequestTimeout(method, endpoint string) {
	httpRequestTimeouts.WithLabelValues(method, endpoint).Inc()
}

func MetricsMiddleware(service, version string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			start := time.Now()

			ww := &responseWriter{ResponseWriter: w, statusCode: http.StatusOK}
			next.ServeHTTP(ww, r)

			duration := time.Since(start).Seconds()

			// Use chi route pattern to avoid cardinality explosion
			routePattern := chi.RouteContext(r.Context()).RoutePattern()
			if routePattern == "" {
				routePattern = "unknown"
			}
			status := strconv.Itoa(ww.statusCode)

			httpRequestsTotal.WithLabelValues(service, version, r.Method, routePattern, status).Inc()
			httpRequestDuration.WithLabelValues(service, version, r.Method, routePattern, status).Observe(duration)

			if ww.statusCode >= 400 {
				httpRequestErrors.WithLabelValues(service, version, r.Method, routePattern, status).Inc()
			}
		})
	}
}

type responseWriter struct {
	http.ResponseWriter
	statusCode int
	written    bool
}

func (rw *responseWriter) WriteHeader(code int) {
	if !rw.written {
		rw.statusCode = code
		rw.written = true
	}
	rw.ResponseWriter.WriteHeader(code)
}

func (rw *responseWriter) Write(b []byte) (int, error) {
	if !rw.written {
		rw.written = true
	}
	return rw.ResponseWriter.Write(b)
}

func RecordRedisConnectionFailure(stage string) {
	redisConnectionFailures.WithLabelValues(stage).Inc()
}
