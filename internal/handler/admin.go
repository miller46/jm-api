package handler

import (
	"net/http"

	"github.com/jack/jm-api-go/internal/service"
)

type AdminHandler struct {
	health         *HealthHandler
	webhookService *service.WebhookService
}

func NewAdminHandler(health *HealthHandler, webhookSvc *service.WebhookService) *AdminHandler {
	return &AdminHandler{
		health:         health,
		webhookService: webhookSvc,
	}
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

// CircuitBreakerStatus returns the status of all circuit breakers
func (h *AdminHandler) CircuitBreakerStatus(w http.ResponseWriter, r *http.Request) {
	states := h.webhookService.GetAllCircuitBreakerStates()
	metrics := h.webhookService.GetCircuitBreakerMetrics()

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"states":  states,
		"metrics": metrics,
	})
}
