package handler

import (
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgtype"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/robfig/cron/v3"

	"github.com/jack/jm-api-go/internal/db/sqlc"
	"github.com/jack/jm-api-go/internal/model"
)

// Cron validation error types
const (
	ErrInvalidCron    = "invalid_cron"
	ErrDuplicateName  = "duplicate_name"
	ErrJobNotFound    = "job_not_found"
	ErrInvalidRequest = "invalid_request"
)

type ScheduledJobHandler struct {
	queries *sqlc.Queries
	pool    *pgxpool.Pool
}

func NewScheduledJobHandler(queries *sqlc.Queries, pool *pgxpool.Pool) *ScheduledJobHandler {
	return &ScheduledJobHandler{queries: queries, pool: pool}
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

// List response format as per issue requirements
type ScheduledJobListResponse struct {
	// Jobs is kept for existing scheduled-jobs admin calendar clients.
	Jobs []ScheduledJobResponse `json:"jobs"`
	// Items provides compatibility with the generic admin table client which expects {items: [...]}.
	Items      []ScheduledJobResponse `json:"items"`
	Pagination PaginationInfo         `json:"pagination"`
}

type PaginationInfo struct {
	Page    int32 `json:"page"`
	PerPage int32 `json:"per_page"`
	Total   int64 `json:"total"`
}

type CreateScheduledJobRequest struct {
	Name           string          `json:"name" validate:"required,min=3,max=255"`
	Description    string          `json:"description"`
	JobType        string          `json:"job_type" validate:"required,max=100"`
	Payload        json.RawMessage `json:"payload"`
	CronExpression string          `json:"cron_expression" validate:"required,max=100"`
	NextRunAt      *time.Time      `json:"next_run_at"`
	Enabled        bool            `json:"enabled"`
}

type UpdateScheduledJobRequest struct {
	Name           *string         `json:"name,omitempty" validate:"omitempty,min=3,max=255"`
	Description    *string         `json:"description,omitempty"`
	JobType        *string         `json:"job_type,omitempty" validate:"omitempty,max=100"`
	Payload        json.RawMessage `json:"payload,omitempty"`
	CronExpression *string         `json:"cron_expression,omitempty" validate:"omitempty,max=100"`
	NextRunAt      *time.Time      `json:"next_run_at,omitempty"`
	Enabled        *bool           `json:"enabled,omitempty"`
}

type RunNowResponse struct {
	ExecutionID string `json:"execution_id"`
	TaskID      string `json:"task_id"`
	Message     string `json:"message"`
}

// validateCronExpression validates a cron expression and returns a meaningful error
func validateCronExpression(expression string) error {
	if expression == "" {
		return errors.New("cron expression is required")
	}
	_, err := cron.ParseStandard(expression)
	if err != nil {
		return err
	}
	return nil
}

// calculateNextRunAt calculates the next run time from a cron expression
func calculateNextRunAt(cronExpression string, from time.Time) (time.Time, error) {
	schedule, err := cron.ParseStandard(cronExpression)
	if err != nil {
		return time.Time{}, err
	}
	return schedule.Next(from), nil
}

func (h *ScheduledJobHandler) List(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	// Parse query parameters
	page, _ := strconv.Atoi(r.URL.Query().Get("page"))
	if page < 1 {
		page = 1
	}
	perPage, _ := strconv.Atoi(r.URL.Query().Get("per_page"))
	if perPage < 1 || perPage > 100 {
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
		Jobs:  items,
		Items: items,
		Pagination: PaginationInfo{
			Page:    int32(page),
			PerPage: int32(perPage),
			Total:   totalCount,
		},
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
		if errors.Is(err, pgx.ErrNoRows) {
			writeJSON(w, http.StatusNotFound, map[string]string{"error": "scheduled job not found"})
			return
		}
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "failed to fetch scheduled job"})
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

	// Validate name length
	if len(req.Name) < 3 {
		writeJSON(w, http.StatusBadRequest, map[string]interface{}{
			"error":   ErrInvalidRequest,
			"message": "Name must be at least 3 characters",
		})
		return
	}

	// Validate cron expression
	if err := validateCronExpression(req.CronExpression); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]interface{}{
			"error":   ErrInvalidCron,
			"message": "Invalid cron expression: " + err.Error(),
		})
		return
	}

	// Calculate next_run_at if not provided
	nextRunAt := req.NextRunAt
	if nextRunAt == nil {
		nextRun, err := calculateNextRunAt(req.CronExpression, time.Now().UTC())
		if err == nil {
			nextRunAt = &nextRun
		}
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
		NextRunAt:      nextRunAt,
		IsEnabled:      req.Enabled,
	})
	if err != nil {
		// Check for unique constraint violation
		if isUniqueViolation(err) {
			writeJSON(w, http.StatusBadRequest, map[string]interface{}{
				"error":   ErrDuplicateName,
				"message": "A job with this name already exists",
			})
			return
		}
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
		if errors.Is(err, pgx.ErrNoRows) {
			writeJSON(w, http.StatusNotFound, map[string]string{"error": "scheduled job not found"})
			return
		}
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "failed to fetch scheduled job"})
		return
	}

	var req UpdateScheduledJobRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid request body"})
		return
	}

	// Validate name if provided
	if req.Name != nil {
		if len(*req.Name) < 3 {
			writeJSON(w, http.StatusBadRequest, map[string]interface{}{
				"error":   ErrInvalidRequest,
				"message": "Name must be at least 3 characters",
			})
			return
		}
	}

	// Validate cron expression if provided
	newCronExpression := existing.CronExpression
	if req.CronExpression != nil {
		if err := validateCronExpression(*req.CronExpression); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]interface{}{
				"error":   ErrInvalidCron,
				"message": "Invalid cron expression: " + err.Error(),
			})
			return
		}
		newCronExpression = *req.CronExpression
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
		IsEnabled:      existing.IsEnabled,
	}

	if req.Name != nil {
		params.Name = *req.Name
	}
	if req.Description != nil {
		params.Description = pgtype.Text{String: *req.Description, Valid: true}
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
	if req.Enabled != nil {
		params.IsEnabled = *req.Enabled
	}

	// Recalculate next_run_at if cron_expression changed
	if req.CronExpression != nil {
		nextRun, err := calculateNextRunAt(newCronExpression, time.Now().UTC())
		if err == nil {
			params.NextRunAt = &nextRun
		}
	}
	// Or if next_run_at was explicitly provided
	if req.NextRunAt != nil {
		params.NextRunAt = req.NextRunAt
	}

	job, err := h.queries.UpdateScheduledJob(ctx, params)
	if err != nil {
		if isUniqueViolation(err) {
			writeJSON(w, http.StatusBadRequest, map[string]interface{}{
				"error":   ErrDuplicateName,
				"message": "A job with this name already exists",
			})
			return
		}
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
		if errors.Is(err, pgx.ErrNoRows) {
			writeJSON(w, http.StatusNotFound, map[string]string{"error": "scheduled job not found"})
			return
		}
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "failed to fetch scheduled job"})
		return
	}

	if err := h.queries.DeleteScheduledJob(ctx, uuid); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "failed to delete scheduled job"})
		return
	}

	w.WriteHeader(http.StatusNoContent)
}

// RunNow manually triggers job execution for testing
func (h *ScheduledJobHandler) RunNow(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	id := chi.URLParam(r, "id")

	var uuid pgtype.UUID
	if err := uuid.Scan(id); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid job id"})
		return
	}

	// Fetch the job
	job, err := h.queries.GetScheduledJob(ctx, uuid)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeJSON(w, http.StatusNotFound, map[string]string{"error": "scheduled job not found"})
			return
		}
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "failed to fetch scheduled job"})
		return
	}

	tx, err := h.pool.Begin(ctx)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "failed to start transaction"})
		return
	}
	defer tx.Rollback(ctx)

	txQueries := h.queries.WithTx(tx)

	// Create an execution record
	execution, err := txQueries.CreateScheduledJobExecution(ctx, job.ID)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "failed to create execution record"})
		return
	}

	// Enqueue a task for immediate execution
	task, err := txQueries.CreateTask(ctx, sqlc.CreateTaskParams{
		ID:      model.GenerateID(),
		Type:    job.JobType,
		Payload: job.Payload,
	})
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "failed to enqueue task"})
		return
	}

	if err := tx.Commit(ctx); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "failed to commit transaction"})
		return
	}

	// Return 202 Accepted with execution details
	writeJSON(w, http.StatusAccepted, RunNowResponse{
		ExecutionID: execution.ID.String(),
		TaskID:      task.ID,
		Message:     "Job execution queued successfully",
	})
}

func scheduledJobToResponse(job sqlc.ScheduledJob) ScheduledJobResponse {
	resp := ScheduledJobResponse{
		ID:             job.ID.String(),
		Name:           job.Name,
		JobType:        job.JobType,
		CronExpression: job.CronExpression,
		NextRunAt:      job.NextRunAt,
		LastRunAt:      job.LastRunAt,
		Enabled:        job.IsEnabled,
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

// isUniqueViolation checks if an error is a PostgreSQL unique constraint violation
func isUniqueViolation(err error) bool {
	if err == nil {
		return false
	}
	// Check for PostgreSQL unique violation error code 23505
	var pgErr *pgconn.PgError
	if errors.As(err, &pgErr) {
		return pgErr.Code == "23505"
	}
	return false
}
