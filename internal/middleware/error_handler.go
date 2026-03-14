package middleware

import (
	"encoding/json"
	"log/slog"
	"net/http"
	"runtime/debug"

	"github.com/jack/jm-api-go/internal/model"
)

// ErrorHandler is a middleware that recovers from panics and handles errors consistently
type ErrorHandler struct {
	environment string
	isProd      bool
}

// NewErrorHandler creates a new error handling middleware
func NewErrorHandler(environment string, isProd bool) *ErrorHandler {
	return &ErrorHandler{
		environment: environment,
		isProd:      isProd,
	}
}

// Middleware recovers from panics and provides consistent error responses
func (eh *ErrorHandler) Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Create a response writer wrapper to capture status code
		rw := &responseWriter{ResponseWriter: w, statusCode: http.StatusOK}
		
		// Defer panic recovery
		defer func() {
			if rec := recover(); rec != nil {
				// Log the panic with full stack trace
				slog.Error("panic recovered",
					"error", rec,
					"stack", string(debug.Stack()),
					"method", r.Method,
					"path", r.URL.Path,
					"request_id", GetRequestID(r.Context()),
				)

				// Return generic 500 error without internal details
				eh.writeErrorResponse(rw, r, http.StatusInternalServerError, "internal server error", nil)
			}
		}()

		next.ServeHTTP(rw, r)
	})
}

// writeErrorResponse writes a standardized error response
func (eh *ErrorHandler) writeErrorResponse(w http.ResponseWriter, r *http.Request, status int, message string, details map[string]interface{}) {
	requestID := GetRequestID(r.Context())
	
	response := model.ErrorResponse{
		Status:    status,
		Error:     http.StatusText(status),
		Message:   message,
		RequestID: requestID,
	}
	
	// Only include details in non-production environments
	if !eh.isProd && details != nil && len(details) > 0 {
		response.Details = details
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(response)
}

// responseWriter wraps http.ResponseWriter to capture status code
type responseWriter struct {
	http.ResponseWriter
	statusCode int
	written    bool
}

func (rw *responseWriter) WriteHeader(code int) {
	if !rw.written {
		rw.statusCode = code
		rw.written = true
		rw.ResponseWriter.WriteHeader(code)
	}
}

func (rw *responseWriter) Write(b []byte) (int, error) {
	if !rw.written {
		rw.WriteHeader(http.StatusOK)
	}
	return rw.ResponseWriter.Write(b)
}
