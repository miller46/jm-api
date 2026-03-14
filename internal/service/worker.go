package service

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgtype"
	"github.com/jack/jm-api-go/internal/db/sqlc"
)

type TaskHandler func(ctx context.Context, payload json.RawMessage) (json.RawMessage, error)

type WorkerService struct {
	queries      *sqlc.Queries
	handlers     map[string]TaskHandler
	pollInterval time.Duration
	maxPerPoll   int
}

func NewWorkerService(q *sqlc.Queries) *WorkerService {
	return &WorkerService{
		queries:      q,
		handlers:     make(map[string]TaskHandler),
		pollInterval: 5 * time.Second,
		maxPerPoll:   10,
	}
}

func (ws *WorkerService) RegisterHandler(taskType string, handler TaskHandler) {
	ws.handlers[taskType] = handler
}

func (ws *WorkerService) ProcessTask(ctx context.Context) (bool, error) {
	task, err := ws.queries.PickQueuedTask(ctx)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return false, nil // No tasks available
		}
		return false, fmt.Errorf("picking queued task: %w", err)
	}

	handler, ok := ws.handlers[task.Type]
	if !ok {
		errMsg := fmt.Sprintf("no handler registered for task type: %s", task.Type)
		if _, failErr := ws.queries.FailTask(ctx, sqlc.FailTaskParams{
			ID:    task.ID,
			Error: pgtype.Text{String: errMsg, Valid: true},
		}); failErr != nil {
			slog.Error("failed to mark task as failed", "task_id", task.ID, "error", failErr)
		}
		return true, fmt.Errorf("%s", errMsg)
	}

	result, err := handler(ctx, task.Payload)
	if err != nil {
		errMsg := err.Error()
		if _, failErr := ws.queries.FailTask(ctx, sqlc.FailTaskParams{
			ID:    task.ID,
			Error: pgtype.Text{String: errMsg, Valid: true},
		}); failErr != nil {
			slog.Error("failed to mark task as failed", "task_id", task.ID, "error", failErr)
		}
		slog.Error("task failed", "task_id", task.ID, "type", task.Type, "error", err)
		return true, nil
	}

	if _, completeErr := ws.queries.CompleteTask(ctx, sqlc.CompleteTaskParams{
		ID:     task.ID,
		Result: result,
	}); completeErr != nil {
		slog.Error("failed to mark task as completed", "task_id", task.ID, "error", completeErr)
	}
	slog.Info("task completed", "task_id", task.ID, "type", task.Type)
	return true, nil
}

func (ws *WorkerService) RunForever(ctx context.Context) error {
	slog.Info("worker started", "poll_interval", ws.pollInterval)

	// Reset stale tasks on startup
	if err := ws.queries.ResetStaleTasks(ctx); err != nil {
		slog.Error("failed to reset stale tasks", "error", err)
	}

	for {
		select {
		case <-ctx.Done():
			slog.Info("worker shutting down")
			return nil
		default:
			processed := 0
			for i := 0; i < ws.maxPerPoll; i++ {
				found, err := ws.ProcessTask(ctx)
				if err != nil {
					slog.Error("task processing error", "error", err)
				}
				if !found {
					break
				}
				processed++
			}

			if processed == 0 {
				select {
				case <-ctx.Done():
					return nil
				case <-time.After(ws.pollInterval):
				}
			}
		}
	}
}
