package handler

import (
	"encoding/json"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/jack/jm-api-go/internal/db/sqlc"
	"github.com/jack/jm-api-go/internal/middleware"
	"github.com/jack/jm-api-go/internal/model"
	"github.com/jack/jm-api-go/internal/service"
	"github.com/jackc/pgx/v5/pgtype"
)

type WebhookHandler struct {
	queries        *sqlc.Queries
	webhookService *service.WebhookService
}

func NewWebhookHandler(q *sqlc.Queries, ws *service.WebhookService) *WebhookHandler {
	return &WebhookHandler{queries: q, webhookService: ws}
}

type createWebhookRequest struct {
	TargetURL  string   `json:"target_url"`
	EventTypes []string `json:"event_types"`
	Secret     string   `json:"secret"`
}

type updateWebhookRequest struct {
	TargetURL  *string  `json:"target_url"`
	EventTypes []string `json:"event_types"`
	Secret     *string  `json:"secret"`
	IsActive   *bool    `json:"is_active"`
}

type verifyWebhookSignatureRequest struct {
	Payload   string `json:"payload"`
	Signature string `json:"signature"`
	Secret    string `json:"secret"`
}

type verifyWebhookSignatureResponse struct {
	Valid bool   `json:"valid"`
	Error string `json:"error,omitempty"`
}

func (h *WebhookHandler) Verify(w http.ResponseWriter, r *http.Request) {
	var req verifyWebhookSignatureRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid request body"})
		return
	}

	if req.Payload == "" {
		writeJSON(w, http.StatusBadRequest, verifyWebhookSignatureResponse{Valid: false, Error: "payload is required"})
		return
	}
	if req.Signature == "" {
		writeJSON(w, http.StatusBadRequest, verifyWebhookSignatureResponse{Valid: false, Error: "signature is required"})
		return
	}
	if req.Secret == "" {
		writeJSON(w, http.StatusBadRequest, verifyWebhookSignatureResponse{Valid: false, Error: "secret is required"})
		return
	}

	valid, errMsg := service.VerifyWebhookSignatureDetailed(req.Secret, []byte(req.Payload), req.Signature, time.Now().UTC(), 5*time.Minute)
	if !valid {
		writeJSON(w, http.StatusBadRequest, verifyWebhookSignatureResponse{Valid: false, Error: errMsg})
		return
	}

	writeJSON(w, http.StatusOK, verifyWebhookSignatureResponse{Valid: true})
}

func (h *WebhookHandler) Create(w http.ResponseWriter, r *http.Request) {
	user := middleware.GetUser(r.Context())
	if user == nil {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "not authenticated"})
		return
	}

	var req createWebhookRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid request body"})
		return
	}

	if req.TargetURL == "" || len(req.TargetURL) > 1024 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "target_url is required (max 1024 chars)"})
		return
	}

	if len(req.EventTypes) == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "at least one event_type is required"})
		return
	}

	for _, et := range req.EventTypes {
		if !model.IsValidEventType(et) {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid event_type: " + et})
			return
		}
	}

	if len(req.Secret) < 8 || len(req.Secret) > 255 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "secret must be between 8 and 255 characters"})
		return
	}

	if err := service.ValidateWebhookURL(req.TargetURL); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
		return
	}

	eventTypesJSON, _ := json.Marshal(req.EventTypes)

	webhook, err := h.queries.CreateWebhook(r.Context(), sqlc.CreateWebhookParams{
		ID:         model.GenerateID(),
		UserID:     user.ID,
		TargetUrl:  req.TargetURL,
		Secret:     req.Secret,
		EventTypes: eventTypesJSON,
		IsActive:   true,
	})
	if err != nil {
		writeInternalError(w, r, "create webhook", err)
		return
	}

	writeJSON(w, http.StatusCreated, webhookToResponse(webhook))
}

func (h *WebhookHandler) List(w http.ResponseWriter, r *http.Request) {
	user := middleware.GetUser(r.Context())
	if user == nil {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "not authenticated"})
		return
	}

	webhooks, err := h.queries.ListWebhooksByUserID(r.Context(), user.ID)
	if err != nil {
		writeInternalError(w, r, "list webhooks", err)
		return
	}

	items := make([]model.WebhookResponse, 0, len(webhooks))
	for _, wh := range webhooks {
		items = append(items, webhookToResponse(wh))
	}

	writeJSON(w, http.StatusOK, items)
}

func (h *WebhookHandler) Update(w http.ResponseWriter, r *http.Request) {
	user := middleware.GetUser(r.Context())
	if user == nil {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "not authenticated"})
		return
	}

	id := chi.URLParam(r, "id")
	existing, err := h.queries.GetWebhookByID(r.Context(), id)
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "webhook not found"})
		return
	}

	if existing.UserID != user.ID {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "webhook not found"})
		return
	}

	var req updateWebhookRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid request body"})
		return
	}

	if req.TargetURL != nil {
		if err := service.ValidateWebhookURL(*req.TargetURL); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
			return
		}
	}

	if req.Secret != nil && (len(*req.Secret) < 8 || len(*req.Secret) > 255) {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "secret must be between 8 and 255 characters"})
		return
	}

	if len(req.EventTypes) > 0 {
		for _, et := range req.EventTypes {
			if !model.IsValidEventType(et) {
				writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid event_type: " + et})
				return
			}
		}
	}

	params := sqlc.UpdateWebhookParams{ID: id}
	if req.TargetURL != nil {
		params.TargetUrl = pgtype.Text{String: *req.TargetURL, Valid: true}
	}
	if req.Secret != nil {
		params.Secret = pgtype.Text{String: *req.Secret, Valid: true}
	}
	if req.IsActive != nil {
		params.IsActive = pgtype.Bool{Bool: *req.IsActive, Valid: true}
	}
	if len(req.EventTypes) > 0 {
		etJSON, _ := json.Marshal(req.EventTypes)
		params.EventTypes = etJSON
	}

	webhook, err := h.queries.UpdateWebhook(r.Context(), params)
	if err != nil {
		writeInternalError(w, r, "update webhook", err)
		return
	}

	writeJSON(w, http.StatusOK, webhookToResponse(webhook))
}

func (h *WebhookHandler) Delete(w http.ResponseWriter, r *http.Request) {
	user := middleware.GetUser(r.Context())
	if user == nil {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "not authenticated"})
		return
	}

	id := chi.URLParam(r, "id")
	existing, err := h.queries.GetWebhookByID(r.Context(), id)
	if err != nil || existing.UserID != user.ID {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "webhook not found"})
		return
	}

	if err := h.queries.DeleteWebhook(r.Context(), id); err != nil {
		writeInternalError(w, r, "delete webhook", err)
		return
	}

	w.WriteHeader(http.StatusNoContent)
}

func (h *WebhookHandler) Deliveries(w http.ResponseWriter, r *http.Request) {
	user := middleware.GetUser(r.Context())
	if user == nil {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "not authenticated"})
		return
	}

	id := chi.URLParam(r, "id")
	existing, err := h.queries.GetWebhookByID(r.Context(), id)
	if err != nil || existing.UserID != user.ID {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "webhook not found"})
		return
	}

	logs, err := h.queries.ListDeliveryLogsByWebhookID(r.Context(), id)
	if err != nil {
		writeInternalError(w, r, "list webhook deliveries", err)
		return
	}

	items := make([]model.WebhookDeliveryLogResponse, 0, len(logs))
	for _, l := range logs {
		item := model.WebhookDeliveryLogResponse{
			ID:        l.ID,
			WebhookID: l.WebhookID,
			EventID:   l.EventID,
			EventType: l.EventType,
			Success:   l.Success,
			Attempts:  int(l.Attempts),
			CreateAt:  l.CreateAt,
		}
		if l.StatusCode.Valid {
			item.StatusCode = &l.StatusCode.Int32
		}
		if l.ResponseBody.Valid {
			item.ResponseBody = &l.ResponseBody.String
		}
		if l.ErrorMessage.Valid {
			item.ErrorMessage = &l.ErrorMessage.String
		}
		items = append(items, item)
	}

	writeJSON(w, http.StatusOK, items)
}

func webhookToResponse(wh sqlc.Webhook) model.WebhookResponse {
	var eventTypes []string
	json.Unmarshal(wh.EventTypes, &eventTypes)

	return model.WebhookResponse{
		ID:           wh.ID,
		UserID:       wh.UserID,
		TargetURL:    wh.TargetUrl,
		EventTypes:   eventTypes,
		IsActive:     wh.IsActive,
		CreateAt:     wh.CreateAt,
		LastUpdateAt: wh.LastUpdateAt,
	}
}
