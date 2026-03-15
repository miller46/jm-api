package service

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"sync"
	"sync/atomic"
	"time"

	"github.com/jack/jm-api-go/internal/db/sqlc"
	"github.com/jack/jm-api-go/internal/workerpool"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgtype"
)

type TaskHandler func(ctx context.Context, payload json.RawMessage) (json.RawMessage, error)

const (
	maxTaskRetries            = 5
	defaultWorkerPollInterval = 5 * time.Second
	defaultWorkerTaskTimeout  = 30 * time.Second
)

type workerQueries interface {
	PickQueuedTask(ctx context.Context) (sqlc.Task, error)
	FailTask(ctx context.Context, arg sqlc.FailTaskParams) (sqlc.Task, error)
	CreateFailedTask(ctx context.Context, arg sqlc.CreateFailedTaskParams) (sqlc.FailedTask, error)
	CompleteTask(ctx context.Context, arg sqlc.CompleteTaskParams) (sqlc.Task, error)
	ResetStaleTasks(ctx context.Context) error
}

type WorkerService struct {
	queries        workerQueries
	handlers       map[string]TaskHandler
	pollInterval   time.Duration
	maxPerPoll     int
	taskTimeout    time.Duration
	maxConcurrency int
	pool           *workerpool.Pool

	mu      sync.RWMutex
	running bool
}

func NewWorkerService(q workerQueries) *WorkerService {
	maxConcurrency := workerpool.DefaultMaxConcurrency
	return &WorkerService{
		queries:        q,
		handlers:       make(map[string]TaskHandler),
		pollInterval:   defaultWorkerPollInterval,
		maxPerPoll:     maxConcurrency,
		taskTimeout:    defaultWorkerTaskTimeout,
		maxConcurrency: maxConcurrency,
		pool:           workerpool.New(maxConcurrency),
	}
}

func (ws *WorkerService) Configure(concurrency int, pollInterval time.Duration, maxPerPoll int, taskTimeout time.Duration) {
	if concurrency <= 0 {
		concurrency = workerpool.DefaultMaxConcurrency
	}
	if pollInterval <= 0 {
		pollInterval = defaultWorkerPollInterval
	}
	if maxPerPoll <= 0 {
		maxPerPoll = concurrency
	}
	if taskTimeout <= 0 {
		taskTimeout = defaultWorkerTaskTimeout
	}

	ws.mu.Lock()
	defer ws.mu.Unlock()

	if ws.running {
		slog.Warn("worker configure ignored while running")
		return
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
	ws.mu.Lock()
	if ws.running {
		ws.mu.Unlock()
		return fmt.Errorf("worker already running")
	}
	ws.running = true
	ws.mu.Unlock()

	defer func() {
		ws.mu.Lock()
		ws.running = false
		ws.mu.Unlock()
	}()

	pollInterval, maxPerPoll, taskTimeout, maxConcurrency, pool := ws.settingsSnapshot()

	slog.Info("worker started",
		"poll_interval", pollInterval,
		"max_per_poll", maxPerPoll,
		"max_concurrency", maxConcurrency,
		"task_timeout", taskTimeout,
	)

	// Reset stale tasks on startup
	if err := ws.queries.ResetStaleTasks(ctx); err != nil {
		slog.Error("failed to reset stale tasks", "error", err)
	}

	for {
		if err := ctx.Err(); err != nil {
			slog.Info("worker shutting down: waiting for in-flight tasks")
			pool.Wait()
			slog.Info("worker shut down complete")
			return nil
		}

		var batchWG sync.WaitGroup
		var processed int32
		submitted := 0

		for i := 0; i < maxPerPoll; i++ {
			if ctx.Err() != nil {
				break
			}

			batchWG.Add(1)
			err := pool.Submit(func() {
				defer batchWG.Done()

				taskCtx, cancel := context.WithTimeout(context.Background(), taskTimeout)
				defer cancel()

				found, runErr := ws.ProcessTask(taskCtx)
				if runErr != nil {
					slog.Error("task processing error", "error", runErr)
				}
				if found {
					atomic.AddInt32(&processed, 1)
				}
			})
			if err != nil {
				batchWG.Done()
				slog.Error("failed to submit task to worker pool", "task_index", i, "error", err)
				break
			}
			submitted++
		}

		if submitted > 0 {
			batchWG.Wait()
		}

		if atomic.LoadInt32(&processed) == 0 {
			select {
			case <-ctx.Done():
				continue
			case <-time.After(pollInterval):
			}
		}
	}
}

func (ws *WorkerService) settingsSnapshot() (time.Duration, int, time.Duration, int, *workerpool.Pool) {
	ws.mu.RLock()
	defer ws.mu.RUnlock()
	return ws.pollInterval, ws.maxPerPoll, ws.taskTimeout, ws.maxConcurrency, ws.pool
}
