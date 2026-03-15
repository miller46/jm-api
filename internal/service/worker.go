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
	"github.com/jack/jm-api-go/internal/workerpool"
)

type TaskHandler func(ctx context.Context, payload json.RawMessage) (json.RawMessage, error)

type WorkerService struct {
	queries        *sqlc.Queries
	handlers       map[string]TaskHandler
	pollInterval   time.Duration
	maxPerPoll     int
	taskTimeout    time.Duration
	maxConcurrency int
	pool           *workerpool.Pool
}

func NewWorkerService(q *sqlc.Queries) *WorkerService {
	maxConcurrency := 10
	return &WorkerService{
		queries:        q,
		handlers:       make(map[string]TaskHandler),
		pollInterval:   5 * time.Second,
		maxPerPoll:     10,
		taskTimeout:    30 * time.Second,
		maxConcurrency: maxConcurrency,
		pool:           workerpool.New(maxConcurrency),
	}
}

func (ws *WorkerService) Configure(concurrency int, pollInterval time.Duration, maxPerPoll int, taskTimeout time.Duration) {
	if concurrency <= 0 {
		concurrency = 10
	}
	if pollInterval <= 0 {
		pollInterval = 5 * time.Second
	}
	if maxPerPoll <= 0 {
		maxPerPoll = concurrency
	}
	if taskTimeout <= 0 {
		taskTimeout = 30 * time.Second
	}

	ws.maxConcurrency = concurrency
	ws.pollInterval = pollInterval
	ws.maxPerPoll = maxPerPoll
	ws.taskTimeout = taskTimeout
	ws.pool = workerpool.New(concurrency)
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
	slog.Info("worker started",
		"poll_interval", ws.pollInterval,
		"max_per_poll", ws.maxPerPoll,
		"max_concurrency", ws.maxConcurrency,
		"task_timeout", ws.taskTimeout,
	)

	// Reset stale tasks on startup
	if err := ws.queries.ResetStaleTasks(ctx); err != nil {
		slog.Error("failed to reset stale tasks", "error", err)
	}

	for {
		if err := ctx.Err(); err != nil {
			slog.Info("worker shutting down: waiting for in-flight tasks")
			ws.pool.Wait()
			slog.Info("worker shut down complete")
			return nil
		}

		results := make(chan bool, ws.maxPerPoll)
		submitted := 0
		for i := 0; i < ws.maxPerPoll; i++ {
			if ctx.Err() != nil {
				break
			}

			err := ws.pool.Submit(func() {
				taskCtx, cancel := context.WithTimeout(context.Background(), ws.taskTimeout)
				defer cancel()

				found, runErr := ws.ProcessTask(taskCtx)
				if runErr != nil {
					slog.Error("task processing error", "error", runErr)
				}
				results <- found
			})
			if err != nil {
				slog.Error("failed to submit task to worker pool", "error", err)
				break
			}
			submitted++
		}

		processed := 0
		for i := 0; i < submitted; i++ {
			if <-results {
				processed++
			}
		}

		if processed == 0 {
			select {
			case <-ctx.Done():
				continue
			case <-time.After(ws.pollInterval):
			}
		}
	}
}
