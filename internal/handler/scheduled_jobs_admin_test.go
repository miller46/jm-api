//go:build integration

package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgtype"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/jack/jm-api-go/internal/db/sqlc"
	"github.com/jack/jm-api-go/internal/testutil"
)

// TestScheduledJobHandler_List_AdminEndpoint tests the scheduled_jobs endpoint
// that is used by the admin table page. This test specifically verifies the fix
// for issue #224 where the admin page was returning HTTP 500.
func TestScheduledJobHandler_List_AdminEndpoint(t *testing.T) {
	testutil.IntegrationTest(t)

	db := testutil.SetupTestDB(t)
	defer db.Close()

	queries := sqlc.New(sqlc.WithQueryTimeout(db, 5))
	handler := NewScheduledJobHandler(queries, db)

	ctx := t.Context()

	// Create test jobs with various states
	nextRun := time.Now().Add(24 * time.Hour)

	_, err := queries.CreateScheduledJob(ctx, sqlc.CreateScheduledJobParams{
		Name:           "Admin Test Job 1",
		JobType:        "test",
		CronExpression: "0 0 * * *",
		NextRunAt:      &nextRun,
		IsEnabled:      true,
		Payload:        []byte(`{"key": "value"}`),
	})
	require.NoError(t, err)

	_, err = queries.CreateScheduledJob(ctx, sqlc.CreateScheduledJobParams{
		Name:           "Admin Test Job 2",
		JobType:        "test",
		CronExpression: "0 0 * * *",
		NextRunAt:      &nextRun,
		IsEnabled:      false,
		Payload:        []byte(`{}`),
	})
	require.NoError(t, err)

	// Test the endpoint that the admin table page uses: /api/v1/scheduled_jobs?per_page=20
	t.Run("admin table endpoint returns 200 with items", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/v1/scheduled_jobs?per_page=20", nil)
		rec := httptest.NewRecorder()

		handler.List(rec, req)

		// This was returning 500 before the fix
		assert.Equal(t, http.StatusOK, rec.Code, "Admin table endpoint should return 200, not 500")

		var response ScheduledJobListResponse
		err := json.Unmarshal(rec.Body.Bytes(), &response)
		require.NoError(t, err)

		// Verify the response has both Jobs and Items for compatibility
		assert.NotNil(t, response.Items, "Response should have items")
		assert.NotNil(t, response.Jobs, "Response should have jobs for backward compatibility")
		assert.GreaterOrEqual(t, len(response.Items), 2, "Should have at least 2 jobs")
		assert.Equal(t, len(response.Items), len(response.Jobs), "Items and Jobs should have same length")
	})

	t.Run("admin table endpoint with no filters", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/v1/scheduled_jobs", nil)
		rec := httptest.NewRecorder()

		handler.List(rec, req)

		assert.Equal(t, http.StatusOK, rec.Code)

		var response ScheduledJobListResponse
		err := json.Unmarshal(rec.Body.Bytes(), &response)
		require.NoError(t, err)

		// Should use default pagination
		assert.Equal(t, int32(1), response.Pagination.Page)
		assert.Equal(t, int32(20), response.Pagination.PerPage)
	})

	t.Run("admin table endpoint with pagination", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/v1/scheduled_jobs?page=1&per_page=1", nil)
		rec := httptest.NewRecorder()

		handler.List(rec, req)

		assert.Equal(t, http.StatusOK, rec.Code)

		var response ScheduledJobListResponse
		err := json.Unmarshal(rec.Body.Bytes(), &response)
		require.NoError(t, err)

		assert.Len(t, response.Items, 1)
		assert.Equal(t, int32(1), response.Pagination.PerPage)
	})

	t.Run("admin table endpoint with enabled filter", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/v1/scheduled_jobs?enabled=true", nil)
		rec := httptest.NewRecorder()

		handler.List(rec, req)

		assert.Equal(t, http.StatusOK, rec.Code)

		var response ScheduledJobListResponse
		err := json.Unmarshal(rec.Body.Bytes(), &response)
		require.NoError(t, err)

		for _, job := range response.Items {
			assert.True(t, job.Enabled, "All returned jobs should be enabled")
		}
	})

	t.Run("admin table endpoint with search filter", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/v1/scheduled_jobs?search=Admin+Test+Job+1", nil)
		rec := httptest.NewRecorder()

		handler.List(rec, req)

		assert.Equal(t, http.StatusOK, rec.Code)

		var response ScheduledJobListResponse
		err := json.Unmarshal(rec.Body.Bytes(), &response)
		require.NoError(t, err)

		for _, job := range response.Items {
			assert.Contains(t, job.Name, "Admin Test Job 1")
		}
	})
}

// TestScheduledJobHandler_ListResponseFormat verifies the response format
// matches what the admin table expects: {items: [...], pagination: {...}}
func TestScheduledJobHandler_ListResponseFormat(t *testing.T) {
	testutil.IntegrationTest(t)

	db := testutil.SetupTestDB(t)
	defer db.Close()

	queries := sqlc.New(sqlc.WithQueryTimeout(db, 5))
	handler := NewScheduledJobHandler(queries, db)

	ctx := t.Context()

	// Create a test job
	nextRun := time.Now().Add(24 * time.Hour)
	_, err := queries.CreateScheduledJob(ctx, sqlc.CreateScheduledJobParams{
		Name:           "Response Format Test",
		JobType:        "test",
		CronExpression: "0 0 * * *",
		NextRunAt:      &nextRun,
		IsEnabled:      true,
		Payload:        []byte(`{}`),
	})
	require.NoError(t, err)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/scheduled_jobs", nil)
	rec := httptest.NewRecorder()

	handler.List(rec, req)

	require.Equal(t, http.StatusOK, rec.Code)

	// Verify response structure matches expected format for admin table
	var response map[string]interface{}
	err = json.Unmarshal(rec.Body.Bytes(), &response)
	require.NoError(t, err)

	// Should have 'items' key for generic table client
	items, ok := response["items"]
	assert.True(t, ok, "Response should have 'items' key")
	assert.NotNil(t, items, "Items should not be nil")

	// Should have 'jobs' key for backward compatibility
	jobs, ok := response["jobs"]
	assert.True(t, ok, "Response should have 'jobs' key for backward compatibility")
	assert.NotNil(t, jobs, "Jobs should not be nil")

	// Should have 'pagination' key
	pagination, ok := response["pagination"]
	assert.True(t, ok, "Response should have 'pagination' key")
	assert.NotNil(t, pagination, "Pagination should not be nil")

	// Verify pagination structure
	paginationMap, ok := pagination.(map[string]interface{})
	assert.True(t, ok, "Pagination should be an object")
	assert.NotNil(t, paginationMap["page"], "Pagination should have 'page'")
	assert.NotNil(t, paginationMap["per_page"], "Pagination should have 'per_page'")
	assert.NotNil(t, paginationMap["total"], "Pagination should have 'total'")
}
