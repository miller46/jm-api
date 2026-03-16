package middleware

import (
	"context"
	"net/http"

	"github.com/google/uuid"
)

type contextKey string

const RequestIDKey contextKey = "request_id"

func RequestID(headerName string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			id := r.Header.Get(headerName)
			if id == "" {
				id = uuid.New().String()
			}

			ctx := context.WithValue(r.Context(), RequestIDKey, id)
			rw := &requestIDResponseWriter{
				ResponseWriter: w,
				headerName:     headerName,
				requestID:      id,
			}
			rw.Header().Set(headerName, id)

			next.ServeHTTP(rw, r.WithContext(ctx))
		})
	}
}

// requestIDResponseWriter guarantees request ID header propagation even if
// downstream handlers replace/clear headers before writing an error response.
type requestIDResponseWriter struct {
	http.ResponseWriter
	headerName string
	requestID  string
	wrote      bool
}

func (w *requestIDResponseWriter) WriteHeader(statusCode int) {
	if !w.wrote {
		if w.Header().Get(w.headerName) == "" {
			w.Header().Set(w.headerName, w.requestID)
		}
		w.wrote = true
	}
	w.ResponseWriter.WriteHeader(statusCode)
}

func (w *requestIDResponseWriter) Write(b []byte) (int, error) {
	if !w.wrote {
		w.WriteHeader(http.StatusOK)
	}
	return w.ResponseWriter.Write(b)
}

func GetRequestID(ctx context.Context) string {
	if id, ok := ctx.Value(RequestIDKey).(string); ok {
		return id
	}
	return ""
}
