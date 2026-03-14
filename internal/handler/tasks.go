package handler

import (
	"encoding/json"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/jack/jm-api-go/internal/db/sqlc"
	"github.com/jack/jm-api-go/internal/model"
)

type TaskHandler struct {
	queries *sqlc.Queries
}

func NewTaskHandler(q *sqlc.Queries) *TaskHandler {
	return &TaskHandler{queries: q}
}

type createTaskRequest struct {
	Type    string          `json:"type"`
	Payload json.RawMessage `json:"payload,omitempty"`
}

func (h *TaskHandler) Create(w http.ResponseWriter, r *http.Request) {
	var req createTaskRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid request body"})
		return
	}

	if req.Type == "" || len(req.Type) > 128 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "type is required (max 128 chars)"})
		return
	}

	task, err := h.queries.CreateTask(r.Context(), sqlc.CreateTaskParams{
		ID:      model.GenerateID(),
		Type:    req.Type,
		Payload: req.Payload,
	})
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "failed to create task"})
		return
	}

	writeJSON(w, http.StatusCreated, taskToResponse(task))
}

func (h *TaskHandler) Get(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	task, err := h.queries.GetTaskByID(r.Context(), id)
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "task not found", "id": id})
		return
	}
	writeJSON(w, http.StatusOK, taskToResponse(task))
}

func taskToResponse(t sqlc.Task) model.TaskResponse {
	resp := model.TaskResponse{
		ID:         t.ID,
		Type:       t.Type,
		Status:     t.Status,
		RetryCount: int(t.RetryCount),
		CreatedAt:  t.CreateAt,
	}

	if len(t.Payload) > 0 {
		var p interface{}
		json.Unmarshal(t.Payload, &p)
		resp.Payload = p
	}
	if len(t.Result) > 0 {
		var r interface{}
		json.Unmarshal(t.Result, &r)
		resp.Result = r
	}
	if t.Error.Valid {
		resp.Error = &t.Error.String
	}
	resp.CompletedAt = t.CompletedAt

	return resp
}
