package handler

import (
	"net/http"
)

type AdminHandler struct {
	health *HealthHandler
}

func NewAdminHandler(health *HealthHandler) *AdminHandler {
	return &AdminHandler{health: health}
}

func (h *AdminHandler) TriggerBreak(w http.ResponseWriter, r *http.Request) {
	h.health.TriggerBreak()
	writeJSON(w, http.StatusOK, map[string]string{"status": "health break triggered"})
}

func (h *AdminHandler) ResetBreak(w http.ResponseWriter, r *http.Request) {
	h.health.ResetBreak()
	writeJSON(w, http.StatusOK, map[string]string{"status": "health break reset"})
}

func (h *AdminHandler) BreakStatus(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]bool{"triggered": h.health.IsBreakTriggered()})
}
