//go:build integration

package handler

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5/pgtype"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/jack/jm-api-go/internal/db/sqlc"
	"github.com/jack/jm-api-go/internal/testutil"
)

func TestScheduledJobHandler_List(t *testing.T) {
	testutil.IntegrationTest(t)

	db := testutil.SetupTestDB(t)
	defer db.Close()

	queries := sqlc.New(sqlc.WithQueryTimeout(db, 5))
	handler := NewScheduledJobHandler(queries)

	// Create test jobs
	ctx := t.Context()
	nextRun := time.Now().Add(24 * time.Hour)

	_, err := queries.CreateScheduledJob(ctx, sqlc.CreateScheduledJobParams{
		Name:           "Test Job 1",
		JobType:        "test",
		CronExpression: "0 0 * * *",
		NextRunAt:      &nextRun,
		IsEnabled:      true,
		Payload:        []byte(`{}`),
	})
	require.NoError(t, err)

	_, err = queries.CreateScheduledJob(ctx, sqlc.CreateScheduledJobParams{
		Name:           "Disabled Job",
		JobType:        "test",
		CronExpression: "0 0 * * *",
		IsEnabled:      false,
		Payload:        []byte(`{}`),
	})
	require.NoError(t, err)

	t.Run("list all jobs", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/v1/admin/scheduled-jobs", nil)
		rec := httptest.NewRecorder()

		handler.List(rec, req)

		assert.Equal(t, http.StatusOK, rec.Code)

		var response ScheduledJobListResponse
		err := json.Unmarshal(rec.Body.Bytes(), &response)
		require.NoError(t, err)

		assert.GreaterOrEqual(t, len(response.Jobs), 2)
		assert.GreaterOrEqual(t, response.Pagination.Total, int64(2))
		assert.Equal(t, int32(1), response.Pagination.Page)
		assert.Equal(t, int32(20), response.Pagination.PerPage)
	})

	t.Run("filter by enabled", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/v1/admin/scheduled-jobs?enabled=true", nil)
		rec := httptest.NewRecorder()

		handler.List(rec, req)

		assert.Equal(t, http.StatusOK, rec.Code)

		var response ScheduledJobListResponse
		err := json.Unmarshal(rec.Body.Bytes(), &response)
		require.NoError(t, err)

		for _, job := range response.Jobs {
			assert.True(t, job.Enabled)
		}
	})

	t.Run("filter by search", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/v1/admin/scheduled-jobs?search=Disabled", nil)
		rec := httptest.NewRecorder()

		handler.List(rec, req)

		assert.Equal(t, http.StatusOK, rec.Code)

		var response ScheduledJobListResponse
		err := json.Unmarshal(rec.Body.Bytes(), &response)
		require.NoError(t, err)

		for _, job := range response.Jobs {
			assert.Contains(t, job.Name, "Disabled")
		}
	})

	t.Run("pagination works correctly", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/v1/admin/scheduled-jobs?page=1&per_page=1", nil)
		rec := httptest.NewRecorder()

		handler.List(rec, req)

		assert.Equal(t, http.StatusOK, rec.Code)

		var response ScheduledJobListResponse
		err := json.Unmarshal(rec.Body.Bytes(), &response)
		require.NoError(t, err)

		assert.Len(t, response.Jobs, 1)
		assert.Equal(t, int32(1), response.Pagination.PerPage)
	})
}

func TestScheduledJobHandler_Create(t *testing.T) {
	testutil.IntegrationTest(t)

	db := testutil.SetupTestDB(t)
	defer db.Close()

	queries := sqlc.New(sqlc.WithQueryTimeout(db, 5))
	handler := NewScheduledJobHandler(queries)

	t.Run("create job successfully", func(t *testing.T) {
		nextRun := time.Now().Add(24 * time.Hour)
		reqBody := CreateScheduledJobRequest{
			Name:           "New Test Job " + time.Now().Format("20060102150405"),
			JobType:        "test",
			CronExpression: "0 0 * * *",
			NextRunAt:      &nextRun,
			Enabled:        true,
		}

		body, _ := json.Marshal(reqBody)
		req := httptest.NewRequest(http.MethodPost, "/api/v1/admin/scheduled-jobs", bytes.NewReader(body))
		req.Header.Set("Content-Type", "application/json")
		rec := httptest.NewRecorder()

		handler.Create(rec, req)

		assert.Equal(t, http.StatusCreated, rec.Code)

		var response ScheduledJobResponse
		err := json.Unmarshal(rec.Body.Bytes(), &response)
		require.NoError(t, err)

		assert.Equal(t, reqBody.Name, response.Name)
		assert.Equal(t, reqBody.JobType, response.JobType)
		assert.Equal(t, reqBody.CronExpression, response.CronExpression)
		assert.Equal(t, reqBody.Enabled, response.Enabled)
		assert.NotEmpty(t, response.ID)
	})

	t.Run("create job with invalid cron expression", func(t *testing.T) {
		reqBody := CreateScheduledJobRequest{
			Name:           "Invalid Cron Job " + time.Now().Format("20060102150405"),
			JobType:        "test",
			CronExpression: "invalid-cron",
			Enabled:        true,
		}

		body, _ := json.Marshal(reqBody)
		req := httptest.NewRequest(http.MethodPost, "/api/v1/admin/scheduled-jobs", bytes.NewReader(body))
		req.Header.Set("Content-Type", "application/json")
		rec := httptest.NewRecorder()

		handler.Create(rec, req)

		assert.Equal(t, http.StatusBadRequest, rec.Code)

		var response map[string]interface{}
		err := json.Unmarshal(rec.Body.Bytes(), &response)
		require.NoError(t, err)

		assert.Equal(t, ErrInvalidCron, response["error"])
		assert.Contains(t, response["message"], "Invalid cron expression")
	})

	t.Run("create job with name too short", func(t *testing.T) {
		reqBody := CreateScheduledJobRequest{
			Name:           "AB",
			JobType:        "test",
			CronExpression: "0 0 * * *",
			Enabled:        true,
		}

		body, _ := json.Marshal(reqBody)
		req := httptest.NewRequest(http.MethodPost, "/api/v1/admin/scheduled-jobs", bytes.NewReader(body))
		req.Header.Set("Content-Type", "application/json")
		rec := httptest.NewRecorder()

		handler.Create(rec, req)

		assert.Equal(t, http.StatusBadRequest, rec.Code)

		var response map[string]interface{}
		err := json.Unmarshal(rec.Body.Bytes(), &response)
		require.NoError(t, err)

		assert.Equal(t, ErrInvalidRequest, response["error"])
	})

	t.Run("create job with duplicate name", func(t *testing.T) {
		ctx := t.Context()
		jobName := "Duplicate Job " + time.Now().Format("20060102150405")

		// Create first job
		_, err := queries.CreateScheduledJob(ctx, sqlc.CreateScheduledJobParams{
			Name:           jobName,
			JobType:        "test",
			CronExpression: "0 0 * * *",
			IsEnabled:      true,
			Payload:        []byte(`{}`),
		})
		require.NoError(t, err)

		// Try to create second job with same name
		reqBody := CreateScheduledJobRequest{
			Name:           jobName,
			JobType:        "test",
			CronExpression: "0 0 * * *",
			Enabled:        true,
		}

		body, _ := json.Marshal(reqBody)
		req := httptest.NewRequest(http.MethodPost, "/api/v1/admin/scheduled-jobs", bytes.NewReader(body))
		req.Header.Set("Content-Type", "application/json")
		rec := httptest.NewRecorder()

		handler.Create(rec, req)

		assert.Equal(t, http.StatusBadRequest, rec.Code)

		var response map[string]interface{}
		err = json.Unmarshal(rec.Body.Bytes(), &response)
		require.NoError(t, err)

		assert.Equal(t, ErrDuplicateName, response["error"])
	})

	t.Run("create job calculates next_run_at automatically", func(t *testing.T) {
		reqBody := CreateScheduledJobRequest{
			Name:           "Auto Next Run Job " + time.Now().Format("20060102150405"),
			JobType:        "test",
			CronExpression: "0 0 * * *",
			Enabled:        true,
		}

		body, _ := json.Marshal(reqBody)
		req := httptest.NewRequest(http.MethodPost, "/api/v1/admin/scheduled-jobs", bytes.NewReader(body))
		req.Header.Set("Content-Type", "application/json")
		rec := httptest.NewRecorder()

		handler.Create(rec, req)

		assert.Equal(t, http.StatusCreated, rec.Code)

		var response ScheduledJobResponse
		err := json.Unmarshal(rec.Body.Bytes(), &response)
		require.NoError(t, err)

		assert.NotNil(t, response.NextRunAt)
	})

	t.Run("create job with invalid body", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodPost, "/api/v1/admin/scheduled-jobs", bytes.NewReader([]byte("invalid")))
		req.Header.Set("Content-Type", "application/json")
		rec := httptest.NewRecorder()

		handler.Create(rec, req)

		assert.Equal(t, http.StatusBadRequest, rec.Code)
	})
}

func TestScheduledJobHandler_Get(t *testing.T) {
	testutil.IntegrationTest(t)

	db := testutil.SetupTestDB(t)
	defer db.Close()

	queries := sqlc.New(sqlc.WithQueryTimeout(db, 5))
	handler := NewScheduledJobHandler(queries)

	// Create a test job
	ctx := t.Context()
	nextRun := time.Now().Add(24 * time.Hour)

	job, err := queries.CreateScheduledJob(ctx, sqlc.CreateScheduledJobParams{
		Name:           "Get Test Job",
		JobType:        "test",
		CronExpression: "0 0 * * *",
		NextRunAt:      &nextRun,
		IsEnabled:      true,
		Payload:        []byte(`{}`),
	})
	require.NoError(t, err)

	t.Run("get existing job", func(t *testing.T) {
		router := chi.NewRouter()
		router.Get("/api/v1/admin/scheduled-jobs/{id}", handler.Get)

		req := httptest.NewRequest(http.MethodGet, "/api/v1/admin/scheduled-jobs/"+job.ID.String(), nil)
		rec := httptest.NewRecorder()

		router.ServeHTTP(rec, req)

		assert.Equal(t, http.StatusOK, rec.Code)

		var response ScheduledJobResponse
		err := json.Unmarshal(rec.Body.Bytes(), &response)
		require.NoError(t, err)

		assert.Equal(t, job.Name, response.Name)
		assert.Equal(t, job.ID.String(), response.ID)
	})

	t.Run("get non-existent job", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/v1/admin/scheduled-jobs/00000000-0000-0000-0000-000000000000", nil)
		rec := httptest.NewRecorder()

		handler.Get(rec, req)

		assert.Equal(t, http.StatusNotFound, rec.Code)
	})

	t.Run("get job with invalid id", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/v1/admin/scheduled-jobs/invalid-id", nil)
		rec := httptest.NewRecorder()

		handler.Get(rec, req)

		assert.Equal(t, http.StatusBadRequest, rec.Code)
	})
}

func TestScheduledJobHandler_Update(t *testing.T) {
	testutil.IntegrationTest(t)

	db := testutil.SetupTestDB(t)
	defer db.Close()

	queries := sqlc.New(sqlc.WithQueryTimeout(db, 5))
	handler := NewScheduledJobHandler(queries)

	// Create a test job
	ctx := t.Context()
	nextRun := time.Now().Add(24 * time.Hour)

	job, err := queries.CreateScheduledJob(ctx, sqlc.CreateScheduledJobParams{
		Name:           "Update Test Job " + time.Now().Format("20060102150405"),
		JobType:        "test",
		CronExpression: "0 0 * * *",
		NextRunAt:      &nextRun,
		IsEnabled:      true,
		Payload:        []byte(`{}`),
	})
	require.NoError(t, err)

	t.Run("update job successfully", func(t *testing.T) {
		newName := "Updated Job Name"
		reqBody := UpdateScheduledJobRequest{
			Name: &newName,
		}

		body, _ := json.Marshal(reqBody)
		req := httptest.NewRequest(http.MethodPatch, "/api/v1/admin/scheduled-jobs/"+job.ID.String(), bytes.NewReader(body))
		req.Header.Set("Content-Type", "application/json")
		rec := httptest.NewRecorder()

		handler.Update(rec, req)

		assert.Equal(t, http.StatusOK, rec.Code)

		var response ScheduledJobResponse
		err := json.Unmarshal(rec.Body.Bytes(), &response)
		require.NoError(t, err)

		assert.Equal(t, newName, response.Name)
		assert.Equal(t, job.ID.String(), response.ID)
	})

	t.Run("update cron expression recalculates next_run_at", func(t *testing.T) {
		newCron := "30 1 * * *"
		reqBody := UpdateScheduledJobRequest{
			CronExpression: &newCron,
		}

		body, _ := json.Marshal(reqBody)
		req := httptest.NewRequest(http.MethodPatch, "/api/v1/admin/scheduled-jobs/"+job.ID.String(), bytes.NewReader(body))
		req.Header.Set("Content-Type", "application/json")
		rec := httptest.NewRecorder()

		handler.Update(rec, req)

		assert.Equal(t, http.StatusOK, rec.Code)

		var response ScheduledJobResponse
		err := json.Unmarshal(rec.Body.Bytes(), &response)
		require.NoError(t, err)

		assert.Equal(t, newCron, response.CronExpression)
		assert.NotNil(t, response.NextRunAt)
	})

	t.Run("update with invalid cron expression", func(t *testing.T) {
		invalidCron := "invalid"
		reqBody := UpdateScheduledJobRequest{
			CronExpression: &invalidCron,
		}

		body, _ := json.Marshal(reqBody)
		req := httptest.NewRequest(http.MethodPatch, "/api/v1/admin/scheduled-jobs/"+job.ID.String(), bytes.NewReader(body))
		req.Header.Set("Content-Type", "application/json")
		rec := httptest.NewRecorder()

		handler.Update(rec, req)

		assert.Equal(t, http.StatusBadRequest, rec.Code)

		var response map[string]interface{}
		err := json.Unmarshal(rec.Body.Bytes(), &response)
		require.NoError(t, err)

		assert.Equal(t, ErrInvalidCron, response["error"])
	})

	t.Run("update non-existent job", func(t *testing.T) {
		newName := "Updated Name"
		reqBody := UpdateScheduledJobRequest{
			Name: &newName,
		}

		body, _ := json.Marshal(reqBody)
		req := httptest.NewRequest(http.MethodPatch, "/api/v1/admin/scheduled-jobs/00000000-0000-0000-0000-000000000000", bytes.NewReader(body))
		req.Header.Set("Content-Type", "application/json")
		rec := httptest.NewRecorder()

		handler.Update(rec, req)

		assert.Equal(t, http.StatusNotFound, rec.Code)
	})
}

func TestScheduledJobHandler_Delete(t *testing.T) {
	testutil.IntegrationTest(t)

	db := testutil.SetupTestDB(t)
	defer db.Close()

	queries := sqlc.New(sqlc.WithQueryTimeout(db, 5))
	handler := NewScheduledJobHandler(queries)

	t.Run("soft delete job successfully", func(t *testing.T) {
		ctx := t.Context()

		// Create a test job
		job, err := queries.CreateScheduledJob(ctx, sqlc.CreateScheduledJobParams{
			Name:           "Delete Test Job " + time.Now().Format("20060102150405"),
			JobType:        "test",
			CronExpression: "0 0 * * *",
			IsEnabled:      true,
			Payload:        []byte(`{}`),
		})
		require.NoError(t, err)

		req := httptest.NewRequest(http.MethodDelete, "/api/v1/admin/scheduled-jobs/"+job.ID.String(), nil)
		rec := httptest.NewRecorder()

		handler.Delete(rec, req)

		assert.Equal(t, http.StatusNoContent, rec.Code)

		// Verify job is soft deleted (not found via Get)
		_, err = queries.GetScheduledJob(ctx, job.ID)
		assert.Error(t, err)

		// Verify job still exists in database with deleted_at set
		var deletedJob sqlc.ScheduledJob
		err = db.QueryRow(ctx, "SELECT * FROM scheduled_jobs WHERE id = $1 AND deleted_at IS NOT NULL", job.ID).Scan(
			&deletedJob.ID, &deletedJob.Name, &deletedJob.Description, &deletedJob.JobType,
			&deletedJob.CronExpression, &deletedJob.NextRunAt, &deletedJob.Payload, &deletedJob.IsEnabled,
			&deletedJob.LastRunAt, &deletedJob.LastError, &deletedJob.CreatedAt, &deletedJob.UpdatedAt, &deletedJob.DeletedAt,
		)
		require.NoError(t, err)
		assert.NotNil(t, deletedJob.DeletedAt)
	})

	t.Run("delete non-existent job", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodDelete, "/api/v1/admin/scheduled-jobs/00000000-0000-0000-0000-000000000000", nil)
		rec := httptest.NewRecorder()

		handler.Delete(rec, req)

		assert.Equal(t, http.StatusNotFound, rec.Code)
	})
}

func TestScheduledJobHandler_RunNow(t *testing.T) {
	testutil.IntegrationTest(t)

	db := testutil.SetupTestDB(t)
	defer db.Close()

	queries := sqlc.New(sqlc.WithQueryTimeout(db, 5))
	handler := NewScheduledJobHandler(queries)

	// Create a test job
	ctx := t.Context()
	nextRun := time.Now().Add(24 * time.Hour)

	job, err := queries.CreateScheduledJob(ctx, sqlc.CreateScheduledJobParams{
		Name:           "Run Now Test Job",
		JobType:        "test-job-type",
		CronExpression: "0 0 * * *",
		NextRunAt:      &nextRun,
		IsEnabled:      true,
		Payload:        []byte(`{"test": "data"}`),
	})
	require.NoError(t, err)

	t.Run("run now creates execution and task", func(t *testing.T) {
		router := chi.NewRouter()
		router.Post("/api/v1/admin/scheduled-jobs/{id}/run-now", handler.RunNow)

		req := httptest.NewRequest(http.MethodPost, "/api/v1/admin/scheduled-jobs/"+job.ID.String()+"/run-now", nil)
		rec := httptest.NewRecorder()

		router.ServeHTTP(rec, req)

		assert.Equal(t, http.StatusAccepted, rec.Code)

		var response RunNowResponse
		err := json.Unmarshal(rec.Body.Bytes(), &response)
		require.NoError(t, err)

		assert.NotEmpty(t, response.ExecutionID)
		assert.NotEmpty(t, response.TaskID)
		assert.Equal(t, "Job execution queued successfully", response.Message)
	})

	t.Run("run now for non-existent job", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodPost, "/api/v1/admin/scheduled-jobs/00000000-0000-0000-0000-000000000000/run-now", nil)
		rec := httptest.NewRecorder()

		handler.RunNow(rec, req)

		assert.Equal(t, http.StatusNotFound, rec.Code)
	})

	t.Run("run now with invalid id", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodPost, "/api/v1/admin/scheduled-jobs/invalid-id/run-now", nil)
		rec := httptest.NewRecorder()

		handler.RunNow(rec, req)

		assert.Equal(t, http.StatusBadRequest, rec.Code)
	})
}

func TestScheduledJobResponse_Mapping(t *testing.T) {
	t.Run("maps scheduled job to response correctly", func(t *testing.T) {
		now := time.Now()
		nextRun := now.Add(24 * time.Hour)

		job := sqlc.ScheduledJob{
			ID:             pgtype.UUID{Bytes: [16]byte{1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16}},
			Name:           "Test Job",
			Description:    pgtype.Text{String: "A test job", Valid: true},
			JobType:        "test",
			Payload:        []byte(`{"key": "value"}`),
			CronExpression: "0 0 * * *",
			NextRunAt:      &nextRun,
			IsEnabled:      true,
			LastError:      pgtype.Text{String: "Some error", Valid: true},
			CreatedAt:      now,
			UpdatedAt:      now,
		}

		resp := scheduledJobToResponse(job)

		assert.Equal(t, job.Name, resp.Name)
		assert.Equal(t, job.Description.String, resp.Description)
		assert.Equal(t, job.JobType, resp.JobType)
		assert.Equal(t, job.CronExpression, resp.CronExpression)
		assert.Equal(t, job.IsEnabled, resp.Enabled)
		assert.Equal(t, job.LastError.String, resp.LastError)
		assert.Equal(t, job.NextRunAt, resp.NextRunAt)
	})

	t.Run("handles null values correctly", func(t *testing.T) {
		now := time.Now()

		job := sqlc.ScheduledJob{
			ID:             pgtype.UUID{Bytes: [16]byte{1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16}},
			Name:           "Test Job",
			JobType:        "test",
			CronExpression: "0 0 * * *",
			IsEnabled:      false,
			Payload:        []byte(`{}`),
			CreatedAt:      now,
			UpdatedAt:      now,
		}

		resp := scheduledJobToResponse(job)

		assert.Equal(t, "", resp.Description)
		assert.Equal(t, "", resp.LastError)
		assert.Nil(t, resp.Payload)
	})
}

func TestCronValidation(t *testing.T) {
	tests := []struct {
		name       string
		expression string
		wantErr    bool
	}{
		{"valid standard cron", "0 0 * * *", false},
		{"valid with day of week", "0 0 * * 0", false},
		{"valid with month", "0 0 1 * *", false},
		{"valid with step", "*/5 * * * *", false},
		{"valid with range", "0 9-17 * * 1-5", false},
		{"valid with list", "0 0,12 * * *", false},
		{"empty expression", "", true},
		{"invalid expression", "invalid", true},
		{"too few fields", "0 0 * *", true},
		{"too many fields", "0 0 * * * *", true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validateCronExpression(tt.expression)
			if tt.wantErr {
				assert.Error(t, err)
			} else {
				assert.NoError(t, err)
			}
		})
	}
}

func TestCalculateNextRunAt(t *testing.T) {
	now := time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)

	tests := []struct {
		name       string
		expression string
		from       time.Time
		wantAfter  time.Time
	}{
		{
			name:       "daily at midnight",
			expression: "0 0 * * *",
			from:       now,
			wantAfter:  time.Date(2024, 1, 2, 0, 0, 0, 0, time.UTC),
		},
		{
			name:       "every hour",
			expression: "0 * * * *",
			from:       now,
			wantAfter:  time.Date(2024, 1, 1, 1, 0, 0, 0, time.UTC),
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			next, err := calculateNextRunAt(tt.expression, tt.from)
			require.NoError(t, err)
			assert.True(t, next.After(tt.from))
			assert.Equal(t, tt.wantAfter, next)
		})
	}
}