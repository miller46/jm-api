package service

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type scheduledJobStoreStub struct {
	executionID string

	createExecutionErr error
	markSuccessErr     error
	markFailureErr     error
	updateRunErr       error

	createdForJobID string
	successExecID   string
	successOutput   string
	failureExecID   string
	failureErr      string
	updateJobID     string
	updateLastErr   *string
}

func (s *scheduledJobStoreStub) CreateExecution(_ context.Context, scheduledJobID string) (string, error) {
	s.createdForJobID = scheduledJobID
	if s.createExecutionErr != nil {
		return "", s.createExecutionErr
	}
	if s.executionID == "" {
		return "exec_1", nil
	}
	return s.executionID, nil
}

func (s *scheduledJobStoreStub) MarkExecutionSuccess(_ context.Context, executionID string, output string) error {
	s.successExecID = executionID
	s.successOutput = output
	return s.markSuccessErr
}

func (s *scheduledJobStoreStub) MarkExecutionFailure(_ context.Context, executionID string, errMsg string) error {
	s.failureExecID = executionID
	s.failureErr = errMsg
	return s.markFailureErr
}

func (s *scheduledJobStoreStub) UpdateScheduledJobRun(_ context.Context, scheduledJobID string, lastErr *string) error {
	s.updateJobID = scheduledJobID
	s.updateLastErr = lastErr
	return s.updateRunErr
}

func TestExecuteScheduledJob_Success(t *testing.T) {
	store := &scheduledJobStoreStub{executionID: "exec_123"}
	SetScheduledJobStore(store)
	t.Cleanup(func() {
		SetScheduledJobStore(nil)
	})

	origSleep := sleepFn
	origRand := randIntn
	randIntn = func(n int) int { return 0 }
	sleepFn = func(time.Duration) {}
	t.Cleanup(func() {
		sleepFn = origSleep
		randIntn = origRand
	})

	err := ExecuteScheduledJob(context.Background(), ScheduledJobPayload{
		JobID:   "job_1",
		Name:    "send_email",
		Payload: json.RawMessage(`{"recipient":"x@example.com"}`),
	})
	require.NoError(t, err)

	assert.Equal(t, "job_1", store.createdForJobID)
	assert.Equal(t, "exec_123", store.successExecID)
	assert.Equal(t, "Job completed successfully", store.successOutput)
	assert.Equal(t, "job_1", store.updateJobID)
	assert.Nil(t, store.updateLastErr)
	assert.Empty(t, store.failureExecID)
}

func TestExecuteScheduledJob_Failure(t *testing.T) {
	store := &scheduledJobStoreStub{executionID: "exec_123"}
	SetScheduledJobStore(store)
	t.Cleanup(func() {
		SetScheduledJobStore(nil)
	})

	RegisterJobExecutor("failing_job", jobExecutorFunc(func(context.Context, json.RawMessage) error {
		return errors.New("boom")
	}))
	t.Cleanup(clearJobRegistry)

	err := ExecuteScheduledJob(context.Background(), ScheduledJobPayload{
		JobID:   "job_1",
		Name:    "failing_job",
		Payload: json.RawMessage(`{"foo":"bar"}`),
	})
	require.Error(t, err)
	assert.Contains(t, err.Error(), "executing job failing_job")

	assert.Equal(t, "exec_123", store.failureExecID)
	assert.Contains(t, store.failureErr, "boom")
	require.NotNil(t, store.updateLastErr)
	assert.Contains(t, *store.updateLastErr, "boom")
}

func TestExecuteScheduledJob_PanicRecovery(t *testing.T) {
	store := &scheduledJobStoreStub{executionID: "exec_123"}
	SetScheduledJobStore(store)
	t.Cleanup(func() {
		SetScheduledJobStore(nil)
	})

	RegisterJobExecutor("panic_job", jobExecutorFunc(func(context.Context, json.RawMessage) error {
		panic("kaboom")
	}))
	t.Cleanup(clearJobRegistry)

	err := ExecuteScheduledJob(context.Background(), ScheduledJobPayload{JobID: "job_1", Name: "panic_job"})
	require.Error(t, err)
	assert.Contains(t, err.Error(), "job panicked")
	assert.Equal(t, "exec_123", store.failureExecID)
	require.NotNil(t, store.updateLastErr)
	assert.Contains(t, *store.updateLastErr, "job panicked")
}

func TestExecuteScheduledJob_ValidationAndStoreNotConfigured(t *testing.T) {
	SetScheduledJobStore(nil)

	err := ExecuteScheduledJob(context.Background(), ScheduledJobPayload{Name: "x"})
	require.Error(t, err)
	assert.Contains(t, err.Error(), "missing job_id")

	err = ExecuteScheduledJob(context.Background(), ScheduledJobPayload{JobID: "job_1"})
	require.Error(t, err)
	assert.Contains(t, err.Error(), "missing name")

	err = ExecuteScheduledJob(context.Background(), ScheduledJobPayload{JobID: "job_1", Name: "x"})
	require.Error(t, err)
	assert.Contains(t, err.Error(), "store is not configured")
}

type jobExecutorFunc func(ctx context.Context, payload json.RawMessage) error

func (f jobExecutorFunc) Execute(ctx context.Context, payload json.RawMessage) error {
	return f(ctx, payload)
}
