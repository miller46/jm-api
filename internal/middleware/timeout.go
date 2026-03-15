package middleware

import (
	"bytes"
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"strconv"
	"sync"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/jack/jm-api-go/internal/observability"
)

const requestTimeoutHeader = "X-Request-Timeout"

// RequestTimeout applies a per-request context timeout and returns a 504 JSON
// response when the deadline is exceeded.
func RequestTimeout(timeout time.Duration) func(http.Handler) http.Handler {
	if timeout <= 0 {
		return func(next http.Handler) http.Handler { return next }
	}

	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set(requestTimeoutHeader, timeout.String())

			ctx, cancel := context.WithTimeout(r.Context(), timeout)
			defer cancel()

			tw := newTimeoutWriter(w)
			done := make(chan struct{})

			go func() {
				next.ServeHTTP(tw, r.WithContext(ctx))
				close(done)
			}()

			select {
			case <-done:
				tw.writeTo(w)
			case <-ctx.Done():
				endpoint := routePattern(r)
				slog.Warn("request timed out",
					"request_id", GetRequestID(r.Context()),
					"method", r.Method,
					"path", r.URL.Path,
					"endpoint", endpoint,
					"timeout", timeout.String(),
				)
				observability.RecordRequestTimeout(r.Method, endpoint)

				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusGatewayTimeout)
				_ = json.NewEncoder(w).Encode(map[string]string{"error": "Request timed out"})
			}
		})
	}
}

func routePattern(r *http.Request) string {
	rctx := chi.RouteContext(r.Context())
	if rctx == nil {
		return r.URL.Path
	}
	if p := rctx.RoutePattern(); p != "" {
		return p
	}
	return r.URL.Path
}

type timeoutWriter struct {
	base   http.ResponseWriter
	header http.Header
	buf    bytes.Buffer
	status int
	wrote  bool
	mu     sync.Mutex
}

func newTimeoutWriter(base http.ResponseWriter) *timeoutWriter {
	return &timeoutWriter{
		base:   base,
		header: make(http.Header),
		status: http.StatusOK,
	}
}

func (w *timeoutWriter) Header() http.Header {
	return w.header
}

func (w *timeoutWriter) WriteHeader(code int) {
	w.mu.Lock()
	defer w.mu.Unlock()
	if w.wrote {
		return
	}
	w.status = code
	w.wrote = true
}

func (w *timeoutWriter) Write(b []byte) (int, error) {
	w.mu.Lock()
	defer w.mu.Unlock()
	if !w.wrote {
		w.wrote = true
	}
	return w.buf.Write(b)
}

func (w *timeoutWriter) writeTo(dst http.ResponseWriter) {
	w.mu.Lock()
	defer w.mu.Unlock()

	for k, vv := range w.header {
		for _, v := range vv {
			dst.Header().Add(k, v)
		}
	}

	dst.Header().Set("Content-Length", strconv.Itoa(w.buf.Len()))
	dst.WriteHeader(w.status)
	_, _ = dst.Write(w.buf.Bytes())
}
