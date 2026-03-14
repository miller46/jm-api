package handler

import (
	"encoding/json"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5/pgtype"
	"github.com/jack/jm-api-go/internal/db/sqlc"
	"github.com/jack/jm-api-go/internal/httperr"
	"github.com/jack/jm-api-go/internal/middleware"
	"github.com/jack/jm-api-go/internal/model"
	"github.com/jack/jm-api-go/internal/service"
)

type WebhookHandler struct {
	queries        *sqlc.Queries
	webhookService *service.WebhookService
	errorHandler   *httperr.Handler
}

func NewWebhookHandler(q *sqlc.Queries, ws *service.WebhookService, eh *httperr.Handler) *WebhookHandler {
	return &WebhookHandler{
		queries:        q,
		webhookService: ws,
		errorHandler:   eh,
	}
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

func (h *WebhookHandler) Create(w http.ResponseWriter, r *http.Request) {
	user := middleware.GetUser(r.Context())
	if user == nil {
		h.errorHandler.RespondError(w, r, httperr.ErrUnauthorized)
		return
	}

	var req createWebhookRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		h.errorHandler.RespondError(w, r, httperr.ErrInvalidRequestBody.WithInternal(err))
		return
	}

	if req.TargetURL == "" || len(req.TargetURL) > 1024 {
		h.errorHandler.RespondError(w, r, httperr.ErrValidationFailed("target_url is required (max 1024 chars)"))
		return
	}

	if len(req.EventTypes) == 0 {
		h.errorHandler.RespondError(w, r, httperr.ErrMissingField("at least one event_type"))
		return
	}

	for _, et := range req.EventTypes {
		if !model.IsValidEventType(et) {
			h.errorHandler.RespondError(w, r, httperr.ErrValidationFailed("invalid event_type: "+et))
			return
		}
	}

	if len(req.Secret) < 8 || len(req.Secret) > 255 {
		h.errorHandler.RespondError(w, r, httperr.ErrValidationFailed("secret must be between 8 and 255 characters"))
		return
	}

	if err := service.ValidateWebhookURL(req.TargetURL); err != nil {
		h.errorHandler.RespondError(w, r, httperr.ErrValidationFailed(err.Error()))
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
		h.errorHandler.RespondError(w, r, httperr.WrapDBError(err, "create_webhook"))
		return
	}

	writeJSON(w, http.StatusCreated, webhookToResponse(webhook))
}

func (h *WebhookHandler) List(w http.ResponseWriter, r *http.Request) {
	user := middleware.GetUser(r.Context())
	if user == nil {
		h.errorHandler.RespondError(w, r, httperr.ErrUnauthorized)
		return
	}

	webhooks, err := h.queries.ListWebhooksByUserID(r.Context(), user.ID)
	if err != nil {
		h.errorHandler.RespondError(w, r, httperr.WrapDBError(err, "list_webhooks"))
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
		h.errorHandler.RespondError(w, r, httperr.ErrUnauthorized)
		return
	}

	id := chi.URLParam(r, "id")
	existing, err := h.queries.GetWebhookByID(r.Context(), id)
	if err != nil {
		h.errorHandler.RespondError(w, r, httperr.WrapDBError(err, "webhook"))
		return
	}

	if existing.UserID != user.ID {
		// Return not found to avoid leaking existence of other users' webhooks
		h.errorHandler.RespondError(w, r, httperr.ErrNotFound("webhook"))
		return
	}

	var req updateWebhookRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		h.errorHandler.RespondError(w, r, httperr.ErrInvalidRequestBody.WithInternal(err))
		return
	}

	if req.TargetURL != nil {
		if err := service.ValidateWebhookURL(*req.TargetURL); err != nil {
			h.errorHandler.RespondError(w, r, httperr.ErrValidationFailed(err.Error()))
			return
		}
	}

	if req.Secret != nil && (len(*req.Secret) < 8 || len(*req.Secret) > 255) {
		h.errorHandler.RespondError(w, r, httperr.ErrValidationFailed("secret must be between 8 and 255 characters"))
		return
	}

	if len(req.EventTypes) > 0 {
		for _, et := range req.EventTypes {
			if !model.IsValidEventType(et) {
				h.errorHandler.RespondError(w, r, httperr.ErrValidationFailed("invalid event_type: "+et))
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
		h.errorHandler.RespondError(w, r, httperr.WrapDBError(err, "update_webhook"))
		return
	}

	writeJSON(w, http.StatusOK, webhookToResponse(webhook))
}

func (h *WebhookHandler) Delete(w http.ResponseWriter, r *http.Request) {
	user := middleware.GetUser(r.Context())
	if user == nil {
		h.errorHandler.RespondError(w, r, httperr.ErrUnauthorized)
		return
	}

	id := chi.URLParam(r, "id")
	existing, err := h.queries.GetWebhookByID(r.Context(), id)
	if err != nil {
		h.errorHandler.RespondError(w, r, httperr.WrapDBError(err, "webhook"))
		return
	}

	if existing.UserID != user.ID {
		h.errorHandler.RespondError(w, r, httperr.ErrNotFound("webhook"))
		return
	}

	if err := h.queries.DeleteWebhook(r.Context(), id); err != nil {
		h.errorHandler.RespondError(w, r, httperr.WrapDBError(err, "delete_webhook"))
		return
	}

	w.WriteHeader(http.StatusNoContent)
}

func (h *WebhookHandler) Deliveries(w http.ResponseWriter, r *http.Request) {
	user := middleware.GetUser(r.Context())
	if user == nil {
		h.errorHandler.RespondError(w, r, httperr.ErrUnauthorized)
		return
	}

	id := chi.URLParam(r, "id")
	existing, err := h.queries.GetWebhookByID(r.Context(), id)
	if err != nil {
		h.errorHandler.RespondError(w, r, httperr.WrapDBError(err, "webhook"))
		return
	}

	if existing.UserID != user.ID {
		h.errorHandler.RespondError(w, r, httperr.ErrNotFound("webhook"))
		return
	}

	logs, err := h.queries.ListDeliveryLogsByWebhookID(r.Context(), id)
	if err != nil {
		h.errorHandler.RespondError(w, r, httperr.WrapDBError(err, "list_deliveries"))
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
