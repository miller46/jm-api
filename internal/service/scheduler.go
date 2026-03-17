package service

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"github.com/jack/jm-api-go/internal/db/sqlc"
	"github.com/jack/jm-api-go/internal/model"
	"github.com/jackc/pgx/v5/pgtype"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/robfig/cron/v3"
)

const (
	defaultSchedulerPollIntervalSeconds = 30
	defaultSchedulerQueryLimit          = 10
	defaultSchedulerWorkerPoolSize      = 5
)

var errInvalidCronExpression = errors.New("invalid cron expression")

type SchedulerConfig struct {
	PollIntervalSeconds int
	QueryLimit          int
	WorkerPoolSize      int
}

type schedulerQueries interface {
	PickDueScheduledJobs(ctx context.Context, limit int32) ([]sqlc.ScheduledJob, error)
	GetScheduledJobForUpdate(ctx context.Context, id pgtype.UUID) (sqlc.ScheduledJob, error)
	UpdateScheduledJobNextRunAt(ctx context.Context, arg sqlc.UpdateScheduledJobNextRunAtParams) (sqlc.ScheduledJob, error)
	CreateTask(ctx context.Context, arg sqlc.CreateTaskParams) (sqlc.Task, error)
}

type schedulerTransactor interface {
	InTx(ctx context.Context, fn func(q schedulerQueries) error) error
}

type sqlcSchedulerTransactor struct {
	pool    *pgxpool.Pool
	queries *sqlc.Queries
}

func (t *sqlcSchedulerTransactor) InTx(ctx context.Context, fn func(q schedulerQueries) error) error {
	tx, err := t.pool.Begin(ctx)
	if err != nil {
		return err
	}

	committed := false
	defer func() {
		if !committed {
			_ = tx.Rollback(ctx)
		}
	}()

	if err := fn(t.queries.WithTx(tx)); err != nil {
		return err
	}

	if err := tx.Commit(ctx); err != nil {
		return err
	}
	committed = true
	return nil
}

type SchedulerService struct {
	queries    schedulerQueries
	transactor schedulerTransactor
	cfg        SchedulerConfig

	mu      sync.Mutex
	running bool
	cancel  context.CancelFunc
	doneCh  chan struct{}
}

func NewSchedulerService(q schedulerQueries, transactor schedulerTransactor, cfg SchedulerConfig) *SchedulerService {
	if cfg.PollIntervalSeconds <= 0 {
		cfg.PollIntervalSeconds = defaultSchedulerPollIntervalSeconds
	}
	if cfg.QueryLimit <= 0 {
		cfg.QueryLimit = defaultSchedulerQueryLimit
	}
	if cfg.WorkerPoolSize <= 0 {
		cfg.WorkerPoolSize = defaultSchedulerWorkerPoolSize
	}

	return &SchedulerService{queries: q, transactor: transactor, cfg: cfg}
}

func NewSchedulerServiceFromSQLC(pool *pgxpool.Pool, queries *sqlc.Queries, cfg SchedulerConfig) *SchedulerService {
	return NewSchedulerService(queries, &sqlcSchedulerTransactor{pool: pool, queries: queries}, cfg)
}

func (s *SchedulerService) Start(ctx context.Context) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.running {
		return fmt.Errorf("scheduler already running")
	}

	runCtx, cancel := context.WithCancel(ctx)
	s.cancel = cancel
	s.doneCh = make(chan struct{})
	s.running = true

	go s.run(runCtx)
	slog.Info("scheduler started",
		"poll_interval_seconds", s.cfg.PollIntervalSeconds,
		"query_limit", s.cfg.QueryLimit,
		"worker_pool_size", s.cfg.WorkerPoolSize,
	)
	return nil
}

func (s *SchedulerService) Stop(ctx context.Context) error {
	s.mu.Lock()
	if !s.running {
		s.mu.Unlock()
		return nil
	}
	cancel := s.cancel
	doneCh := s.doneCh
	s.mu.Unlock()

	cancel()

	select {
	case <-doneCh:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

func (s *SchedulerService) run(ctx context.Context) {
	defer func() {
		s.mu.Lock()
		s.running = false
		close(s.doneCh)
		s.mu.Unlock()
		slog.Info("scheduler stopped")
	}()

	ticker := time.NewTicker(time.Duration(s.cfg.PollIntervalSeconds) * time.Second)
	defer ticker.Stop()

	for {
		s.pollOnce(ctx)

		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (s *SchedulerService) pollOnce(ctx context.Context) {
	jobs, err := s.queries.PickDueScheduledJobs(ctx, int32(s.cfg.QueryLimit))
	if err != nil {
		slog.Error("failed to query due scheduled jobs", "error", err)
		return
	}
	if len(jobs) == 0 {
		return
	}

	sem := make(chan struct{}, s.cfg.WorkerPoolSize)
	var wg sync.WaitGroup

	for _, job := range jobs {
		job := job
		wg.Add(1)
		sem <- struct{}{}
		go func() {
			defer wg.Done()
			defer func() { <-sem }()

			if err := s.processJob(ctx, job); err != nil {
				slog.Error("failed processing scheduled job", "job_id", job.ID, "job_name", job.Name, "error", err)
			}
		}()
	}

	wg.Wait()
}

func (s *SchedulerService) processJob(ctx context.Context, job sqlc.ScheduledJob) error {
	err := s.transactor.InTx(ctx, func(q schedulerQueries) error {
		lockedJob, err := q.GetScheduledJobForUpdate(ctx, job.ID)
		if err != nil {
			return fmt.Errorf("locking scheduled job %s: %w", job.ID, err)
		}

		if lockedJob.NextRunAt == nil {
			return fmt.Errorf("scheduled job %s has nil next_run_at", lockedJob.ID)
		}

		nextRunAt, err := calculateNextRunAt(lockedJob.CronExpression, lockedJob.NextRunAt.UTC())
		if err != nil {
			slog.Warn("failed to calculate next run time", "job_id", lockedJob.ID, "job_name", lockedJob.Name, "error", err)
			return errInvalidCronExpression
		}

		if _, err := q.UpdateScheduledJobNextRunAt(ctx, sqlc.UpdateScheduledJobNextRunAtParams{
			ID:        lockedJob.ID,
			NextRunAt: &nextRunAt,
		}); err != nil {
			return fmt.Errorf("updating next_run_at for scheduled job %s: %w", lockedJob.ID, err)
		}

		if _, err := q.CreateTask(ctx, sqlc.CreateTaskParams{
			ID:      model.GenerateID(),
			Type:    lockedJob.JobType,
			Payload: lockedJob.Payload,
		}); err != nil {
			slog.Error("failed to enqueue job to task queue", "job_id", lockedJob.ID, "job_name", lockedJob.Name, "error", err)
			return fmt.Errorf("enqueue task for scheduled job %s: %w", lockedJob.ID, err)
		}

		slog.Info("Scheduled job discovered",
			"job_name", lockedJob.Name,
			"job_id", lockedJob.ID,
			"next_run_at", nextRunAt,
		)
		return nil
	})

	if errors.Is(err, errInvalidCronExpression) {
		return nil
	}

	return err
}

func calculateNextRunAt(cronExpression string, from time.Time) (time.Time, error) {
	schedule, err := cron.ParseStandard(cronExpression)
	if err != nil {
		return time.Time{}, err
	}
	return schedule.Next(from), nil
}
