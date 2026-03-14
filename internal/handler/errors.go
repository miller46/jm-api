package handler

import (
	"log/slog"
	"net/http"

	"github.com/jack/jm-api-go/internal/middleware"
)

func writeInternalError(w http.ResponseWriter, r *http.Request, operation string, err error) {
	slog.Error("request failed",
		"request_id", middleware.GetRequestID(r.Context()),
		"method", r.Method,
		"path", r.URL.Path,
		"operation", operation,
		"error", err,
	)
	writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Internal Server Error"})
}
