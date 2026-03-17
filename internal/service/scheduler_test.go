package service

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"

	"github.com/jack/jm-api-go/internal/db/sqlc"
	"github.com/jackc/pgx/v5/pgtype"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type schedulerQueriesStub struct {
	dueJobs              []sqlc.ScheduledJob
	pickDueErr           error
	lockedJob            sqlc.ScheduledJob
	lockErr              error
	updateNextRunErr     error
	createTaskErr        error
	createTaskCalls      int
	updateNextRunCalls   int
	createTaskLastParams *sqlc.CreateTaskParams
}

func (s *schedulerQueriesStub) PickDueScheduledJobs(context.Context, int32) ([]sqlc.ScheduledJob, error) {
	return s.dueJobs, s.pickDueErr
}

func (s *schedulerQueriesStub) GetScheduledJobForUpdate(context.Context, pgtype.UUID) (sqlc.ScheduledJob, error) {
	if s.lockErr != nil {
		return sqlc.ScheduledJob{}, s.lockErr
	}
	return s.lockedJob, nil
}

func (s *schedulerQueriesStub) UpdateScheduledJobNextRunAt(_ context.Context, _ sqlc.UpdateScheduledJobNextRunAtParams) (sqlc.ScheduledJob, error) {
	s.updateNextRunCalls++
	if s.updateNextRunErr != nil {
		return sqlc.ScheduledJob{}, s.updateNextRunErr
	}
	return s.lockedJob, nil
}

func (s *schedulerQueriesStub) CreateTask(_ context.Context, arg sqlc.CreateTaskParams) (sqlc.Task, error) {
	s.createTaskCalls++
	s.createTaskLastParams = &arg
	if s.createTaskErr != nil {
		return sqlc.Task{}, s.createTaskErr
	}
	return sqlc.Task{}, nil
}

type schedulerTransactorStub struct {
	queries      schedulerQueries
	inTxErr      error
	commitCalled bool
}

func (s *schedulerTransactorStub) InTx(ctx context.Context, fn func(q schedulerQueries) error) error {
	if s.inTxErr != nil {
		return s.inTxErr
	}
	if err := fn(s.queries); err != nil {
		return err
	}
	s.commitCalled = true
	return nil
}

func TestSchedulerProcessJob_EnqueuesTaskAndUpdatesNextRun(t *testing.T) {
	payload := json.RawMessage(`{"source":"scheduler"}`)
	nextRun := time.Now().UTC()
	job := sqlc.ScheduledJob{
		ID:             mustUUID(t, "11111111-1111-1111-1111-111111111111"),
		Name:           "nightly",
		JobType:        "echo",
		Payload:        payload,
		CronExpression: "*/5 * * * *",
		NextRunAt:      &nextRun,
	}
	queries := &schedulerQueriesStub{lockedJob: job}
	transactor := &schedulerTransactorStub{queries: queries}
	svc := NewSchedulerService(queries, transactor, SchedulerConfig{})

	err := svc.processJob(context.Background(), job)
	require.NoError(t, err)
	assert.True(t, transactor.commitCalled)
	assert.Equal(t, 1, queries.updateNextRunCalls)
	assert.Equal(t, 1, queries.createTaskCalls)
	require.NotNil(t, queries.createTaskLastParams)
	assert.Equal(t, "echo", queries.createTaskLastParams.Type)
	assert.Equal(t, []byte(payload), queries.createTaskLastParams.Payload)
	assert.NotEmpty(t, queries.createTaskLastParams.ID)
}

func TestSchedulerProcessJob_InvalidCronSkipsEnqueue(t *testing.T) {
	nextRun := time.Now().UTC()
	job := sqlc.ScheduledJob{ID: mustUUID(t, "22222222-2222-2222-2222-222222222222"), Name: "invalid", CronExpression: "not-a-cron", NextRunAt: &nextRun}
	queries := &schedulerQueriesStub{lockedJob: job}
	transactor := &schedulerTransactorStub{queries: queries}
	svc := NewSchedulerService(queries, transactor, SchedulerConfig{})

	err := svc.processJob(context.Background(), job)
	require.NoError(t, err)
	assert.Equal(t, 0, queries.updateNextRunCalls)
	assert.Equal(t, 0, queries.createTaskCalls)
	assert.False(t, transactor.commitCalled)
}

func TestSchedulerProcessJob_EnqueueFailureReturnsError(t *testing.T) {
	nextRun := time.Now().UTC()
	job := sqlc.ScheduledJob{ID: mustUUID(t, "33333333-3333-3333-3333-333333333333"), Name: "nightly", CronExpression: "*/10 * * * *", JobType: "echo", NextRunAt: &nextRun}
	queries := &schedulerQueriesStub{lockedJob: job, createTaskErr: errors.New("queue down")}
	transactor := &schedulerTransactorStub{queries: queries}
	svc := NewSchedulerService(queries, transactor, SchedulerConfig{})

	err := svc.processJob(context.Background(), job)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "enqueue task")
}

func TestSchedulerStartStop(t *testing.T) {
	queries := &schedulerQueriesStub{dueJobs: []sqlc.ScheduledJob{}}
	transactor := &schedulerTransactorStub{queries: queries}
	svc := NewSchedulerService(queries, transactor, SchedulerConfig{PollIntervalSeconds: 1, QueryLimit: 1, WorkerPoolSize: 1})

	err := svc.Start(context.Background())
	require.NoError(t, err)

	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	err = svc.Stop(ctx)
	require.NoError(t, err)
}

func mustUUID(t *testing.T, s string) pgtype.UUID {
	t.Helper()
	var id pgtype.UUID
	require.NoError(t, id.Scan(s))
	return id
}
