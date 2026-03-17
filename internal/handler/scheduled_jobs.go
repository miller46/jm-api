package handler

import (
	"encoding/json"
	"net/http"
	"strconv"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5/pgtype"

	"github.com/jack/jm-api-go/internal/db/sqlc"
)

type ScheduledJobHandler struct {
	queries *sqlc.Queries
}

func NewScheduledJobHandler(queries *sqlc.Queries) *ScheduledJobHandler {
	return &ScheduledJobHandler{queries: queries}
}

type ScheduledJobResponse struct {
	ID             string          `json:"id"`
	Name           string          `json:"name"`
	Description    string          `json:"description,omitempty"`
	JobType        string          `json:"job_type"`
	Payload        json.RawMessage `json:"payload,omitempty"`
	CronExpression string          `json:"cron_expression"`
	NextRunAt      *time.Time      `json:"next_run_at"`
	LastRunAt      *time.Time      `json:"last_run_at,omitempty"`
	Enabled        bool            `json:"enabled"`
	LastError      string          `json:"last_error,omitempty"`
	CreatedAt      time.Time       `json:"created_at"`
	UpdatedAt      time.Time       `json:"updated_at"`
}

type ScheduledJobListResponse struct {
	Items      []ScheduledJobResponse `json:"items"`
	TotalCount int64                  `json:"total_count"`
	Page       int32                  `json:"page"`
	PerPage    int32                  `json:"per_page"`
}

type CreateScheduledJobRequest struct {
	Name           string          `json:"name" validate:"required,max=255"`
	Description    string          `json:"description"`
	JobType        string          `json:"job_type" validate:"required,max=100"`
	Payload        json.RawMessage `json:"payload"`
	CronExpression string          `json:"cron_expression" validate:"required,max=100"`
	NextRunAt      *time.Time      `json:"next_run_at"`
	Enabled        bool            `json:"enabled"`
}

type UpdateScheduledJobRequest struct {
	Name           *string         `json:"name,omitempty" validate:"omitempty,max=255"`
	Description    *string         `json:"description,omitempty"`
	JobType        *string         `json:"job_type,omitempty" validate:"omitempty,max=100"`
	Payload        json.RawMessage `json:"payload,omitempty"`
	CronExpression *string         `json:"cron_expression,omitempty" validate:"omitempty,max=100"`
	NextRunAt      *time.Time      `json:"next_run_at,omitempty"`
	Enabled        *bool           `json:"enabled,omitempty"`
}

func (h *ScheduledJobHandler) List(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	// Parse query parameters
	page, _ := strconv.Atoi(r.URL.Query().Get("page"))
	if page < 1 {
		page = 1
	}
	perPage, _ := strconv.Atoi(r.URL.Query().Get("per_page"))
	if perPage < 1 || perPage > 1000 {
		perPage = 20
	}
	offset := (page - 1) * perPage

	// Parse filter parameters
	enabledParam := r.URL.Query().Get("enabled")
	searchParam := r.URL.Query().Get("search")

	var enabled pgtype.Bool
	if enabledParam == "true" {
		enabled = pgtype.Bool{Bool: true, Valid: true}
	} else if enabledParam == "false" {
		enabled = pgtype.Bool{Bool: false, Valid: true}
	}

	var search pgtype.Text
	if searchParam != "" {
		search = pgtype.Text{String: searchParam, Valid: true}
	}

	// Fetch jobs
	jobs, err := h.queries.ListScheduledJobs(ctx, sqlc.ListScheduledJobsParams{
		Enabled: enabled,
		Search:  search,
		Offset:  pgtype.Int4{Int32: int32(offset), Valid: true},
		PerPage: pgtype.Int4{Int32: int32(perPage), Valid: true},
	})
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "failed to fetch scheduled jobs"})
		return
	}

	// Get total count for pagination
	totalCount, err := h.queries.CountScheduledJobs(ctx, sqlc.CountScheduledJobsParams{
		Enabled: enabled,
		Search:  search,
	})
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "failed to count scheduled jobs"})
		return
	}

	// Convert to response format
	items := make([]ScheduledJobResponse, len(jobs))
	for i, job := range jobs {
		items[i] = scheduledJobToResponse(job)
	}

	writeJSON(w, http.StatusOK, ScheduledJobListResponse{
		Items:      items,
		TotalCount: totalCount,
		Page:       int32(page),
		PerPage:    int32(perPage),
	})
}

func (h *ScheduledJobHandler) Get(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	id := chi.URLParam(r, "id")

	var uuid pgtype.UUID
	if err := uuid.Scan(id); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid job id"})
		return
	}

	job, err := h.queries.GetScheduledJob(ctx, uuid)
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "scheduled job not found"})
		return
	}

	writeJSON(w, http.StatusOK, scheduledJobToResponse(job))
}

func (h *ScheduledJobHandler) Create(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	var req CreateScheduledJobRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid request body"})
		return
	}

	var payload []byte
	if req.Payload != nil {
		payload = req.Payload
	} else {
		payload = []byte("{}")
	}

	job, err := h.queries.CreateScheduledJob(ctx, sqlc.CreateScheduledJobParams{
		Name:           req.Name,
		Description:    pgtype.Text{String: req.Description, Valid: req.Description != ""},
		JobType:        req.JobType,
		Payload:        payload,
		CronExpression: req.CronExpression,
		NextRunAt:      req.NextRunAt,
		Enabled:        req.Enabled,
	})
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "failed to create scheduled job"})
		return
	}

	writeJSON(w, http.StatusCreated, scheduledJobToResponse(job))
}

func (h *ScheduledJobHandler) Update(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	id := chi.URLParam(r, "id")

	var uuid pgtype.UUID
	if err := uuid.Scan(id); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid job id"})
		return
	}

	// Check if job exists
	existing, err := h.queries.GetScheduledJob(ctx, uuid)
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "scheduled job not found"})
		return
	}

	var req UpdateScheduledJobRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid request body"})
		return
	}

	// Build update params using existing values as defaults
	params := sqlc.UpdateScheduledJobParams{
		ID:             uuid,
		Name:           existing.Name,
		Description:    existing.Description,
		JobType:        existing.JobType,
		Payload:        existing.Payload,
		CronExpression: existing.CronExpression,
		NextRunAt:      existing.NextRunAt,
		Enabled:        existing.Enabled,
	}

	if req.Name != nil {
		params.Name = *req.Name
	}
	if req.Description != nil {
		params.Description = pgtype.Text{String: *req.Description, Valid: *req.Description != ""}
	}
	if req.JobType != nil {
		params.JobType = *req.JobType
	}
	if req.Payload != nil {
		params.Payload = req.Payload
	}
	if req.CronExpression != nil {
		params.CronExpression = *req.CronExpression
	}
	if req.NextRunAt != nil {
		params.NextRunAt = req.NextRunAt
	}
	if req.Enabled != nil {
		params.Enabled = *req.Enabled
	}

	job, err := h.queries.UpdateScheduledJob(ctx, params)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "failed to update scheduled job"})
		return
	}

	writeJSON(w, http.StatusOK, scheduledJobToResponse(job))
}

func (h *ScheduledJobHandler) Delete(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	id := chi.URLParam(r, "id")

	var uuid pgtype.UUID
	if err := uuid.Scan(id); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid job id"})
		return
	}

	// Check if job exists
	_, err := h.queries.GetScheduledJob(ctx, uuid)
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "scheduled job not found"})
		return
	}

	if err := h.queries.DeleteScheduledJob(ctx, uuid); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "failed to delete scheduled job"})
		return
	}

	w.WriteHeader(http.StatusNoContent)
}

func scheduledJobToResponse(job sqlc.ScheduledJob) ScheduledJobResponse {
	resp := ScheduledJobResponse{
		ID:             job.ID.String(),
		Name:           job.Name,
		JobType:        job.JobType,
		CronExpression: job.CronExpression,
		NextRunAt:      job.NextRunAt,
		LastRunAt:      job.LastRunAt,
		Enabled:        job.Enabled,
		CreatedAt:      job.CreatedAt,
		UpdatedAt:      job.UpdatedAt,
	}

	if job.Description.Valid {
		resp.Description = job.Description.String
	}
	if len(job.Payload) > 0 && string(job.Payload) != "{}" {
		resp.Payload = job.Payload
	}
	if job.LastError.Valid {
		resp.LastError = job.LastError.String
	}

	return resp
}
