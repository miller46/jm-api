package service

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"math/rand"
	"runtime/debug"
	"sync"
	"time"
)

type ScheduledJobPayload struct {
	JobID   string          `json:"job_id"`
	Name    string          `json:"name"`
	Payload json.RawMessage `json:"payload"`
}

type scheduledJobStore interface {
	CreateExecution(ctx context.Context, scheduledJobID string) (string, error)
	MarkExecutionSuccess(ctx context.Context, executionID string, output string) error
	MarkExecutionFailure(ctx context.Context, executionID string, errMsg string) error
	UpdateScheduledJobRun(ctx context.Context, scheduledJobID string, lastErr *string) error
}

type JobExecutor interface {
	Execute(ctx context.Context, payload json.RawMessage) error
}

var jobRegistry = map[string]JobExecutor{}

var (
	scheduledJobStoreMu sync.RWMutex
	scheduledStore      scheduledJobStore
	randIntn            = rand.Intn
	sleepFn             = time.Sleep
)

func SetScheduledJobStore(store scheduledJobStore) {
	scheduledJobStoreMu.Lock()
	defer scheduledJobStoreMu.Unlock()
	scheduledStore = store
}

func ExecuteScheduledJob(ctx context.Context, payload ScheduledJobPayload) (err error) {
	started := time.Now()

	if payload.JobID == "" {
		return errors.New("scheduled job payload missing job_id")
	}
	if payload.Name == "" {
		return errors.New("scheduled job payload missing name")
	}

	store := getScheduledJobStore()
	if store == nil {
		return errors.New("scheduled job store is not configured")
	}

	slog.Info("Executing scheduled job", "name", payload.Name, "job_id", payload.JobID)
	slog.Info("Job payload", "payload", string(payload.Payload))

	executionID, err := store.CreateExecution(ctx, payload.JobID)
	if err != nil {
		return fmt.Errorf("creating execution record: %w", err)
	}

	defer func() {
		if r := recover(); r != nil {
			err = fmt.Errorf("job panicked: %v\n%s", r, debug.Stack())
		}

		if err == nil {
			if updateErr := store.MarkExecutionSuccess(ctx, executionID, "Job completed successfully"); updateErr != nil {
				err = fmt.Errorf("updating execution success: %w", updateErr)
				slog.Error("Failed to update scheduled job execution success", "name", payload.Name, "job_id", payload.JobID, "execution_id", executionID, "error", updateErr)
				return
			}
			if updateErr := store.UpdateScheduledJobRun(ctx, payload.JobID, nil); updateErr != nil {
				err = fmt.Errorf("updating scheduled job run metadata: %w", updateErr)
				slog.Error("Failed to update scheduled_jobs run metadata", "name", payload.Name, "job_id", payload.JobID, "execution_id", executionID, "error", updateErr)
				return
			}
			slog.Info("Job completed", "name", payload.Name, "job_id", payload.JobID, "duration", time.Since(started))
			return
		}

		errMsg := err.Error()
		if updateErr := store.MarkExecutionFailure(ctx, executionID, errMsg); updateErr != nil {
			slog.Error("Failed to update scheduled job execution failure", "name", payload.Name, "job_id", payload.JobID, "execution_id", executionID, "error", updateErr)
		}
		if updateErr := store.UpdateScheduledJobRun(ctx, payload.JobID, &errMsg); updateErr != nil {
			slog.Error("Failed to update scheduled_jobs error metadata", "name", payload.Name, "job_id", payload.JobID, "execution_id", executionID, "error", updateErr)
		}
		slog.Error("Job failed", "name", payload.Name, "job_id", payload.JobID, "error", err)
	}()

	if executor, ok := jobRegistry[payload.Name]; ok {
		if execErr := executor.Execute(ctx, payload.Payload); execErr != nil {
			return fmt.Errorf("executing job %s: %w", payload.Name, execErr)
		}
		return nil
	}

	sleepDuration := time.Duration(1+randIntn(2)) * time.Second
	sleepFn(sleepDuration)
	return nil
}

func getScheduledJobStore() scheduledJobStore {
	scheduledJobStoreMu.RLock()
	defer scheduledJobStoreMu.RUnlock()
	return scheduledStore
}
