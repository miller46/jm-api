package service

import (
	"context"
	"encoding/json"
	"errors"
	"testing"

	"github.com/jack/jm-api-go/internal/db/sqlc"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgtype"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type workerQueriesStub struct {
	pickedTask      sqlc.Task
	pickErr         error
	failedTask      sqlc.Task
	failErr         error
	createFailedErr error

	failCalls       int
	createFailedArg *sqlc.CreateFailedTaskParams
}

func (s *workerQueriesStub) PickQueuedTask(context.Context) (sqlc.Task, error) {
	return s.pickedTask, s.pickErr
}

func (s *workerQueriesStub) FailTask(context.Context, sqlc.FailTaskParams) (sqlc.Task, error) {
	s.failCalls++
	return s.failedTask, s.failErr
}

func (s *workerQueriesStub) CreateFailedTask(_ context.Context, arg sqlc.CreateFailedTaskParams) (sqlc.FailedTask, error) {
	s.createFailedArg = &arg
	return sqlc.FailedTask{}, s.createFailedErr
}

func (s *workerQueriesStub) CompleteTask(context.Context, sqlc.CompleteTaskParams) (sqlc.Task, error) {
	return sqlc.Task{}, nil
}

func (s *workerQueriesStub) ResetStaleTasks(context.Context) error {
	return nil
}

func TestProcessTask_NoTaskAvailable(t *testing.T) {
	stub := &workerQueriesStub{pickErr: pgx.ErrNoRows}
	ws := NewWorkerService(stub)

	found, err := ws.ProcessTask(context.Background())
	require.NoError(t, err)
	assert.False(t, found)
}

func TestProcessTask_DoesNotDLQBeforeMaxRetries(t *testing.T) {
	stub := &workerQueriesStub{
		pickedTask: sqlc.Task{ID: "task_1", Type: "echo", Payload: json.RawMessage(`{"x":1}`)},
		failedTask: sqlc.Task{ID: "task_1", Type: "echo", Payload: json.RawMessage(`{"x":1}`), RetryCount: maxTaskRetries - 1},
	}
	ws := NewWorkerService(stub)
	ws.RegisterHandler("echo", func(ctx context.Context, payload json.RawMessage) (json.RawMessage, error) {
		return nil, errors.New("boom")
	})

	found, err := ws.ProcessTask(context.Background())
	require.NoError(t, err)
	assert.True(t, found)
	assert.Nil(t, stub.createFailedArg)
}

func TestProcessTask_MovesTaskToDLQAtMaxRetries(t *testing.T) {
	payload := json.RawMessage(`{"x":1}`)
	stub := &workerQueriesStub{
		pickedTask: sqlc.Task{ID: "task_1", Type: "echo", Payload: payload},
		failedTask: sqlc.Task{ID: "task_1", Type: "echo", Payload: payload, RetryCount: maxTaskRetries},
	}
	ws := NewWorkerService(stub)
	ws.RegisterHandler("echo", func(ctx context.Context, payload json.RawMessage) (json.RawMessage, error) {
		return nil, errors.New("permanent failure")
	})

	found, err := ws.ProcessTask(context.Background())
	require.NoError(t, err)
	assert.True(t, found)
	require.NotNil(t, stub.createFailedArg)
	assert.Equal(t, "task_1", stub.createFailedArg.OriginalTaskID)
	assert.Equal(t, "echo", stub.createFailedArg.TaskType)
	assert.Equal(t, []byte(payload), stub.createFailedArg.Payload)
	assert.Equal(t, int32(maxTaskRetries), stub.createFailedArg.AttemptCount)
	assert.Equal(t, "permanent failure", stub.createFailedArg.ErrorMessage)
	assert.Equal(t, pgtype.Text{}, stub.createFailedArg.ErrorStack)
}
