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
		Enabled:        true,
		Payload:        []byte(`{}`),
	})
	require.NoError(t, err)

	_, err = queries.CreateScheduledJob(ctx, sqlc.CreateScheduledJobParams{
		Name:           "Disabled Job",
		JobType:        "test",
		CronExpression: "0 0 * * *",
		Enabled:        false,
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

		assert.GreaterOrEqual(t, len(response.Items), 2)
		assert.GreaterOrEqual(t, response.TotalCount, int64(2))
	})

	t.Run("filter by enabled", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/v1/admin/scheduled-jobs?enabled=true", nil)
		rec := httptest.NewRecorder()

		handler.List(rec, req)

		assert.Equal(t, http.StatusOK, rec.Code)

		var response ScheduledJobListResponse
		err := json.Unmarshal(rec.Body.Bytes(), &response)
		require.NoError(t, err)

		for _, job := range response.Items {
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

		for _, job := range response.Items {
			assert.Contains(t, job.Name, "Disabled")
		}
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
			Name:           "New Test Job",
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
		Enabled:        true,
		Payload:        []byte(`{}`),
	})
	require.NoError(t, err)

	t.Run("get existing job", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/v1/admin/scheduled-jobs/"+job.ID.String(), nil)
		rec := httptest.NewRecorder()

		// Add chi URL parameter
		rctx := chi.NewRouteContext()
		rctx.URLParams.Add("id", job.ID.String())
		req = req.WithContext(req.Context())

		handler.Get(rec, req)

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
		Name:           "Update Test Job",
		JobType:        "test",
		CronExpression: "0 0 * * *",
		NextRunAt:      &nextRun,
		Enabled:        true,
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

	// Create a test job
	ctx := t.Context()

	job, err := queries.CreateScheduledJob(ctx, sqlc.CreateScheduledJobParams{
		Name:           "Delete Test Job",
		JobType:        "test",
		CronExpression: "0 0 * * *",
		Enabled:        true,
		Payload:        []byte(`{}`),
	})
	require.NoError(t, err)

	t.Run("delete job successfully", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodDelete, "/api/v1/admin/scheduled-jobs/"+job.ID.String(), nil)
		rec := httptest.NewRecorder()

		handler.Delete(rec, req)

		assert.Equal(t, http.StatusNoContent, rec.Code)

		// Verify job is deleted
		_, err := queries.GetScheduledJob(ctx, job.ID)
		assert.Error(t, err)
	})

	t.Run("delete non-existent job", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodDelete, "/api/v1/admin/scheduled-jobs/00000000-0000-0000-0000-000000000000", nil)
		rec := httptest.NewRecorder()

		handler.Delete(rec, req)

		assert.Equal(t, http.StatusNotFound, rec.Code)
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
			Enabled:        true,
			LastError:      pgtype.Text{String: "Some error", Valid: true},
			CreatedAt:      now,
			UpdatedAt:      now,
		}

		resp := scheduledJobToResponse(job)

		assert.Equal(t, job.Name, resp.Name)
		assert.Equal(t, job.Description.String, resp.Description)
		assert.Equal(t, job.JobType, resp.JobType)
		assert.Equal(t, job.CronExpression, resp.CronExpression)
		assert.Equal(t, job.Enabled, resp.Enabled)
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
			Enabled:        false,
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
