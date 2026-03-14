// Package httperr provides standardized HTTP error handling utilities
package httperr

import (
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"

	"github.com/jack/jm-api-go/internal/middleware"
	"github.com/jack/jm-api-go/internal/model"
)

// Handler is the error handler utility that provides consistent error responses
type Handler struct {
	isProd bool
}

// NewHandler creates a new error handler
func NewHandler(isProd bool) *Handler {
	return &Handler{isProd: isProd}
}

// AppError represents an application error with HTTP status and logging context
type AppError struct {
	Status      int
	Message     string
	InternalErr error
	LogAttrs    []slog.Attr
}

func (e *AppError) Error() string {
	if e.InternalErr != nil {
		return e.InternalErr.Error()
	}
	return e.Message
}

// Unwrap returns the internal error for error chain inspection
func (e *AppError) Unwrap() error {
	return e.InternalErr
}

// NewAppError creates a new application error
func NewAppError(status int, message string) *AppError {
	return &AppError{
		Status:  status,
		Message: message,
	}
}

// WithInternal adds an internal error (for logging only, not exposed to client)
func (e *AppError) WithInternal(err error) *AppError {
	e.InternalErr = err
	return e
}

// WithLogAttrs adds structured logging attributes
func (e *AppError) WithLogAttrs(attrs ...slog.Attr) *AppError {
	e.LogAttrs = append(e.LogAttrs, attrs...)
	return e
}

// RespondError writes an error response based on an AppError
func (h *Handler) RespondError(w http.ResponseWriter, r *http.Request, appErr *AppError) {
	requestID := middleware.GetRequestID(r.Context())

	// Build log attributes
	logAttrs := []slog.Any{
		slog.String("request_id", requestID),
		slog.String("method", r.Method),
		slog.String("path", r.URL.Path),
		slog.Int("status", appErr.Status),
		slog.String("error_message", appErr.Message),
	}
	
	// Add any custom log attributes
	for _, attr := range appErr.LogAttrs {
		logAttrs = append(logAttrs, attr)
	}

	// Add internal error to logs (never to client response)
	if appErr.InternalErr != nil {
		logAttrs = append(logAttrs, slog.String("internal_error", appErr.InternalErr.Error()))
	}

	// Log at appropriate level based on status code
	switch {
	case appErr.Status >= 500:
		slog.Error("server error", logAttrs...)
	case appErr.Status >= 400:
		slog.Warn("client error", logAttrs...)
	default:
		slog.Info("error response", logAttrs...)
	}

	// Prepare response
	response := model.NewErrorResponse(appErr.Status, appErr.Message, requestID)

	// In non-production, include internal error details for debugging
	if !h.isProd && appErr.InternalErr != nil {
		response.Details = map[string]interface{}{
			"internal_error": appErr.InternalErr.Error(),
		}
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(appErr.Status)
	json.NewEncoder(w).Encode(response)
}

// Respond writes a successful JSON response
func Respond(w http.ResponseWriter, status int, data interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(data)
}

// Common error helpers for consistent error messages
var (
	// 400 Bad Request
	ErrInvalidRequestBody   = NewAppError(http.StatusBadRequest, "invalid request body")
	ErrMissingField         = func(field string) *AppError { return NewAppError(http.StatusBadRequest, field+" is required") }
	ErrInvalidField         = func(field string) *AppError { return NewAppError(http.StatusBadRequest, "invalid "+field) }
	ErrValidationFailed     = func(msg string) *AppError { return NewAppError(http.StatusBadRequest, msg) }
	
	// 401 Unauthorized
	ErrUnauthorized         = NewAppError(http.StatusUnauthorized, "authentication required")
	ErrInvalidCredentials   = NewAppError(http.StatusUnauthorized, "invalid credentials")
	ErrTokenExpired         = NewAppError(http.StatusUnauthorized, "token expired")
	ErrInvalidToken         = NewAppError(http.StatusUnauthorized, "invalid token")
	
	// 403 Forbidden
	ErrForbidden            = NewAppError(http.StatusForbidden, "access denied")
	ErrAdminRequired        = NewAppError(http.StatusForbidden, "admin access required")
	ErrCSRFInvalid          = NewAppError(http.StatusForbidden, "invalid CSRF token")
	
	// 404 Not Found
	ErrNotFound             = func(resource string) *AppError { return NewAppError(http.StatusNotFound, resource+" not found") }
	
	// 409 Conflict
	ErrConflict             = func(msg string) *AppError { return NewAppError(http.StatusConflict, msg) }
	ErrDuplicate            = func(field string) *AppError { return NewAppError(http.StatusConflict, field+" already exists") }
	
	// 429 Too Many Requests
	ErrRateLimited          = NewAppError(http.StatusTooManyRequests, "rate limit exceeded")
	
	// 500 Internal Server Error
	ErrInternalServer       = NewAppError(http.StatusInternalServerError, "internal server error")
	ErrDatabase             = NewAppError(http.StatusInternalServerError, "database error")
	ErrServiceUnavailable   = NewAppError(http.StatusServiceUnavailable, "service temporarily unavailable")
)

// WrapDBError wraps database errors with appropriate HTTP status codes
func WrapDBError(err error, resource string) *AppError {
	if err == nil {
		return nil
	}
	
	// Check for common database error patterns
	errStr := err.Error()
	
	// Duplicate key violation (PostgreSQL: 23505)
	if contains(errStr, "23505") || contains(errStr, "unique constraint") || contains(errStr, "duplicate key") {
		return ErrDuplicate(resource).WithInternal(err)
	}
	
	// Foreign key violation (PostgreSQL: 23503)
	if contains(errStr, "23503") || contains(errStr, "foreign key constraint") {
		return NewAppError(http.StatusBadRequest, "referenced "+resource+" does not exist").WithInternal(err)
	}
	
	// Not found
	if contains(errStr, "no rows") {
		return ErrNotFound(resource).WithInternal(err)
	}
	
	// Default to internal server error for DB errors (don't leak details)
	return ErrInternalServer.WithInternal(err).WithLogAttrs(slog.String("db_operation", resource))
}

func contains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || len(s) > 0 && containsIgnoreCase(s, substr))
}

func containsIgnoreCase(s, substr string) bool {
	if len(substr) > len(s) {
		return false
	}
	for i := 0; i <= len(s)-len(substr); i++ {
		match := true
		for j := 0; j < len(substr); j++ {
			if toLower(s[i+j]) != toLower(substr[j]) {
				match = false
				break
			}
		}
		if match {
			return true
		}
	}
	return false
}

func toLower(b byte) byte {
	if b >= 'A' && b <= 'Z' {
		return b + ('a' - 'A')
	}
	return b
}

// IsAppError checks if an error is an AppError
func IsAppError(err error) (*AppError, bool) {
	var appErr *AppError
	if errors.As(err, &appErr) {
		return appErr, true
	}
	return nil, false
}
