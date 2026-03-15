package service

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"time"

	"github.com/jack/jm-api-go/internal/db/sqlc"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgtype"
)

type TaskHandler func(ctx context.Context, payload json.RawMessage) (json.RawMessage, error)

const maxTaskRetries = 5

type workerQueries interface {
	PickQueuedTask(ctx context.Context) (sqlc.Task, error)
	FailTask(ctx context.Context, arg sqlc.FailTaskParams) (sqlc.Task, error)
	CreateFailedTask(ctx context.Context, arg sqlc.CreateFailedTaskParams) (sqlc.FailedTask, error)
	CompleteTask(ctx context.Context, arg sqlc.CompleteTaskParams) (sqlc.Task, error)
	ResetStaleTasks(ctx context.Context) error
}

type WorkerService struct {
	queries      workerQueries
	handlers     map[string]TaskHandler
	pollInterval time.Duration
	maxPerPoll   int
}

func NewWorkerService(q workerQueries) *WorkerService {
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
		if failErr := ws.markTaskFailed(ctx, task, errMsg); failErr != nil {
			slog.Error("failed to mark task as failed", "task_id", task.ID, "error", failErr)
		}
		return true, fmt.Errorf("%s", errMsg)
	}

	result, err := handler(ctx, task.Payload)
	if err != nil {
		errMsg := err.Error()
		if failErr := ws.markTaskFailed(ctx, task, errMsg); failErr != nil {
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

func (ws *WorkerService) markTaskFailed(ctx context.Context, task sqlc.Task, errMsg string) error {
	updatedTask, err := ws.queries.FailTask(ctx, sqlc.FailTaskParams{
		ID:    task.ID,
		Error: pgtype.Text{String: errMsg, Valid: true},
	})
	if err != nil {
		return fmt.Errorf("failing task: %w", err)
	}

	if updatedTask.RetryCount < maxTaskRetries {
		return nil
	}

	if _, err := ws.queries.CreateFailedTask(ctx, sqlc.CreateFailedTaskParams{
		OriginalTaskID: updatedTask.ID,
		TaskType:       updatedTask.Type,
		Payload:        updatedTask.Payload,
		ErrorMessage:   errMsg,
		ErrorStack:     pgtype.Text{},
		AttemptCount:   updatedTask.RetryCount,
	}); err != nil {
		return fmt.Errorf("adding task to dead letter queue: %w", err)
	}

	slog.Error("task moved to dead letter queue", "task_id", updatedTask.ID, "type", updatedTask.Type, "attempt_count", updatedTask.RetryCount)
	return nil
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
