package middleware

import (
	"encoding/json"
	"log/slog"
	"net/http"
)

// ErrorHandler catches unhandled panics and returns a standardized JSON error.
func ErrorHandler() func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			defer func() {
				if rec := recover(); rec != nil {
					slog.Error("unhandled panic in request",
						"request_id", GetRequestID(r.Context()),
						"method", r.Method,
						"path", r.URL.Path,
						"error", rec,
					)

					w.Header().Set("Content-Type", "application/json")
					w.WriteHeader(http.StatusInternalServerError)
					_ = json.NewEncoder(w).Encode(map[string]string{"error": "Internal Server Error"})
				}
			}()

			next.ServeHTTP(w, r)
		})
	}
}
