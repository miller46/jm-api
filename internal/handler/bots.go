package handler

import (
	"context"
	"encoding/json"
	"math"
	"net/http"
	"strconv"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5/pgtype"
	"github.com/jack/jm-api-go/internal/db/sqlc"
	"github.com/jack/jm-api-go/internal/model"
	"github.com/jack/jm-api-go/internal/service"
)

type BotHandler struct {
	queries        *sqlc.Queries
	webhookService *service.WebhookService
}

func NewBotHandler(q *sqlc.Queries, ws *service.WebhookService) *BotHandler {
	return &BotHandler{queries: q, webhookService: ws}
}

type createBotRequest struct {
	RigID      string  `json:"rig_id"`
	KillSwitch bool    `json:"kill_switch"`
	LastRunLog *string `json:"last_run_log"`
}

type updateBotRequest struct {
	RigID      *string `json:"rig_id"`
	KillSwitch *bool   `json:"kill_switch"`
	LastRunLog *string `json:"last_run_log"`
}

func (h *BotHandler) List(w http.ResponseWriter, r *http.Request) {
	page, _ := strconv.Atoi(r.URL.Query().Get("page"))
	if page < 1 {
		page = 1
	}
	perPage, _ := strconv.Atoi(r.URL.Query().Get("per_page"))
	if perPage < 1 {
		perPage = 20
	}
	if perPage > 100 {
		perPage = 100
	}

	params := sqlc.ListBotsParams{
		Limit:  int32(perPage),
		Offset: int32((page - 1) * perPage),
	}
	countParams := sqlc.CountBotsParams{}

	if v := r.URL.Query().Get("rig_id"); v != "" {
		t := pgtype.Text{String: v, Valid: true}
		params.RigID = t
		countParams.RigID = t
	}
	if v := r.URL.Query().Get("kill_switch"); v != "" {
		b, _ := strconv.ParseBool(v)
		pb := pgtype.Bool{Bool: b, Valid: true}
		params.KillSwitch = pb
		countParams.KillSwitch = pb
	}
	if v := r.URL.Query().Get("log_search"); v != "" {
		t := pgtype.Text{String: v, Valid: true}
		params.LogSearch = t
		countParams.LogSearch = t
	}
	if v := r.URL.Query().Get("create_at_from"); v != "" {
		if ts, err := time.Parse(time.RFC3339, v); err == nil {
			params.CreateAtFrom = &ts
			countParams.CreateAtFrom = &ts
		}
	}
	if v := r.URL.Query().Get("create_at_to"); v != "" {
		if ts, err := time.Parse(time.RFC3339, v); err == nil {
			params.CreateAtTo = &ts
			countParams.CreateAtTo = &ts
		}
	}
	if v := r.URL.Query().Get("last_update_at_from"); v != "" {
		if ts, err := time.Parse(time.RFC3339, v); err == nil {
			params.LastUpdateAtFrom = &ts
			countParams.LastUpdateAtFrom = &ts
		}
	}
	if v := r.URL.Query().Get("last_update_at_to"); v != "" {
		if ts, err := time.Parse(time.RFC3339, v); err == nil {
			params.LastUpdateAtTo = &ts
			countParams.LastUpdateAtTo = &ts
		}
	}
	if v := r.URL.Query().Get("last_run_at_from"); v != "" {
		if ts, err := time.Parse(time.RFC3339, v); err == nil {
			params.LastRunAtFrom = &ts
			countParams.LastRunAtFrom = &ts
		}
	}
	if v := r.URL.Query().Get("last_run_at_to"); v != "" {
		if ts, err := time.Parse(time.RFC3339, v); err == nil {
			params.LastRunAtTo = &ts
			countParams.LastRunAtTo = &ts
		}
	}

	bots, err := h.queries.ListBots(r.Context(), params)
	if err != nil {
		writeInternalError(w, r, "list bots", err)
		return
	}

	total, err := h.queries.CountBots(r.Context(), countParams)
	if err != nil {
		writeInternalError(w, r, "count bots", err)
		return
	}

	items := make([]model.BotResponse, 0, len(bots))
	for _, b := range bots {
		items = append(items, botToResponse(b))
	}

	pages := int(math.Ceil(float64(total) / float64(perPage)))

	writeJSON(w, http.StatusOK, model.BotListResponse{
		Items:   items,
		Total:   total,
		Page:    page,
		PerPage: perPage,
		Pages:   pages,
	})
}

func (h *BotHandler) Get(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	bot, err := h.queries.GetBotByID(r.Context(), id)
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "bot not found", "id": id})
		return
	}
	writeJSON(w, http.StatusOK, botToResponse(bot))
}

func (h *BotHandler) Create(w http.ResponseWriter, r *http.Request) {
	var req createBotRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid request body"})
		return
	}

	if req.RigID == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "rig_id is required"})
		return
	}

	lastRunLog := pgtype.Text{}
	if req.LastRunLog != nil {
		lastRunLog = pgtype.Text{String: *req.LastRunLog, Valid: true}
	}

	bot, err := h.queries.CreateBot(r.Context(), sqlc.CreateBotParams{
		ID:         model.GenerateID(),
		RigID:      req.RigID,
		KillSwitch: req.KillSwitch,
		LastRunLog: lastRunLog,
	})
	if err != nil {
		writeInternalError(w, r, "create bot", err)
		return
	}

	resp := botToResponse(bot)
	if h.webhookService != nil {
		go h.webhookService.DispatchEvent(context.Background(), "bot.created", resp)
	}

	writeJSON(w, http.StatusCreated, resp)
}

func (h *BotHandler) Update(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")

	if _, err := h.queries.GetBotByID(r.Context(), id); err != nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "bot not found", "id": id})
		return
	}

	var req updateBotRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid request body"})
		return
	}

	updateParams := sqlc.UpdateBotParams{ID: id}
	if req.RigID != nil {
		updateParams.RigID = pgtype.Text{String: *req.RigID, Valid: true}
	}
	if req.KillSwitch != nil {
		updateParams.KillSwitch = pgtype.Bool{Bool: *req.KillSwitch, Valid: true}
	}
	if req.LastRunLog != nil {
		updateParams.LastRunLog = pgtype.Text{String: *req.LastRunLog, Valid: true}
	}

	bot, err := h.queries.UpdateBot(r.Context(), updateParams)
	if err != nil {
		writeInternalError(w, r, "update bot", err)
		return
	}

	resp := botToResponse(bot)
	if h.webhookService != nil {
		go h.webhookService.DispatchEvent(context.Background(), "bot.updated", resp)
	}

	writeJSON(w, http.StatusOK, resp)
}

func (h *BotHandler) Delete(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")

	bot, err := h.queries.GetBotByID(r.Context(), id)
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "bot not found", "id": id})
		return
	}

	if err := h.queries.DeleteBot(r.Context(), id); err != nil {
		writeInternalError(w, r, "delete bot", err)
		return
	}

	if h.webhookService != nil {
		resp := botToResponse(bot)
		go h.webhookService.DispatchEvent(context.Background(), "bot.deleted", resp)
	}

	w.WriteHeader(http.StatusNoContent)
}

func botToResponse(b sqlc.Bot) model.BotResponse {
	var lastRunLog *string
	if b.LastRunLog.Valid {
		lastRunLog = &b.LastRunLog.String
	}
	return model.BotResponse{
		ID:           b.ID,
		RigID:        b.RigID,
		LastRunAt:    b.LastRunAt,
		KillSwitch:   b.KillSwitch,
		LastRunLog:   lastRunLog,
		CreateAt:     b.CreateAt,
		LastUpdateAt: b.LastUpdateAt,
	}
}
