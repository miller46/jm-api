package handler

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"sync/atomic"

	"github.com/jackc/pgx/v5/pgxpool"
)

type RedisChecker func(ctx context.Context) error

type HealthHandler struct {
	db                    *pgxpool.Pool
	healthBreak           atomic.Bool
	migrationCheckEnabled bool
	expectedMigration     int
	redisCheck            RedisChecker
	redisRequired         bool
}

type HealthOption func(*HealthHandler)

func WithMigrationCheck(expectedVersion int) HealthOption {
	return func(h *HealthHandler) {
		h.migrationCheckEnabled = true
		h.expectedMigration = expectedVersion
	}
}

func WithRedisCheck(check RedisChecker, required bool) HealthOption {
	return func(h *HealthHandler) {
		h.redisCheck = check
		h.redisRequired = required
	}
}

func NewHealthHandler(db *pgxpool.Pool, opts ...HealthOption) *HealthHandler {
	h := &HealthHandler{db: db}
	for _, opt := range opts {
		opt(h)
	}
	return h
}

func (h *HealthHandler) Live(w http.ResponseWriter, r *http.Request) {
	if h.healthBreak.Load() {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"status": "fail", "reason": "health break triggered"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (h *HealthHandler) Health(w http.ResponseWriter, r *http.Request) {
	if h.healthBreak.Load() {
		writeJSON(w, http.StatusServiceUnavailable, map[string]interface{}{
			"status": "fail",
			"checks": map[string]interface{}{
				"health_break": map[string]string{"status": "fail", "reason": "health break triggered"},
			},
		})
		return
	}

	checks := map[string]interface{}{}
	status := http.StatusOK
	overallStatus := "ok"

	// Database check
	if h.db != nil {
		if err := h.db.Ping(context.Background()); err != nil {
			checks["database"] = map[string]string{"status": "fail", "error": err.Error()}
			status = http.StatusServiceUnavailable
			overallStatus = "fail"
		} else {
			checks["database"] = map[string]string{"status": "ok"}
		}
	}

	// Migration check
	if h.migrationCheckEnabled && h.db != nil {
		if err := h.checkMigration(r.Context()); err != nil {
			checks["migration"] = map[string]string{"status": "fail", "error": err.Error()}
			status = http.StatusServiceUnavailable
			overallStatus = "fail"
		} else {
			checks["migration"] = map[string]string{"status": "ok"}
		}
	}

	// Redis check
	if h.redisCheck == nil {
		checks["redis"] = map[string]string{"status": "not_configured"}
	} else {
		if err := h.redisCheck(r.Context()); err != nil {
			checks["redis"] = map[string]string{"status": "fail", "error": err.Error()}
			if h.redisRequired {
				status = http.StatusServiceUnavailable
				overallStatus = "fail"
			}
		} else {
			checks["redis"] = map[string]string{"status": "ok"}
		}
	}

	writeJSON(w, status, map[string]interface{}{
		"status": overallStatus,
		"checks": checks,
	})
}

func (h *HealthHandler) checkMigration(ctx context.Context) error {
	var version int
	var dirty bool
	err := h.db.QueryRow(ctx, "SELECT version, dirty FROM schema_migrations LIMIT 1").Scan(&version, &dirty)
	if err != nil {
		return fmt.Errorf("could not read migration version: %w", err)
	}
	if dirty {
		return fmt.Errorf("migration is dirty at version %d", version)
	}
	if version != h.expectedMigration {
		return fmt.Errorf("migration version %d does not match expected %d", version, h.expectedMigration)
	}
	return nil
}

func (h *HealthHandler) Ready(w http.ResponseWriter, r *http.Request) {
	h.Health(w, r)
}

func (h *HealthHandler) Healthz(w http.ResponseWriter, r *http.Request) {
	if h.healthBreak.Load() {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"status": "fail"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (h *HealthHandler) TriggerBreak() {
	h.healthBreak.Store(true)
}

func (h *HealthHandler) ResetBreak() {
	h.healthBreak.Store(false)
}

func (h *HealthHandler) IsBreakTriggered() bool {
	return h.healthBreak.Load()
}

func writeJSON(w http.ResponseWriter, status int, v interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}
