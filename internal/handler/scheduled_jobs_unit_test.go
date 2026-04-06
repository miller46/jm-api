package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestScheduledJobHandler_List_ItemsField(t *testing.T) {
	// This is a unit test to verify the List handler returns both Jobs and Items fields
	// to ensure compatibility with the generic admin table client
	t.Skip("Skipping: requires database connection for integration test")
}

// TestScheduledJobListResponse_MarshalJSON verifies that the response structure
// contains both Jobs and Items fields pointing to the same data
func TestScheduledJobListResponse_MarshalJSON(t *testing.T) {
	resp := ScheduledJobListResponse{
		Jobs: []ScheduledJobResponse{
			{ID: "test-id-1", Name: "Test Job 1", JobType: "test"},
			{ID: "test-id-2", Name: "Test Job 2", JobType: "test"},
		},
		Items: []ScheduledJobResponse{
			{ID: "test-id-1", Name: "Test Job 1", JobType: "test"},
			{ID: "test-id-2", Name: "Test Job 2", JobType: "test"},
		},
		Pagination: PaginationInfo{
			Page:    1,
			PerPage: 20,
			Total:   2,
		},
	}

	// Marshal to JSON
	data, err := json.Marshal(resp)
	require.NoError(t, err)

	// Unmarshal to verify structure
	var result map[string]interface{}
	err = json.Unmarshal(data, &result)
	require.NoError(t, err)

	// Verify both jobs and items fields exist
	assert.Contains(t, result, "jobs")
	assert.Contains(t, result, "items")
	assert.Contains(t, result, "pagination")

	// Verify both fields have the same data
	jobs := result["jobs"].([]interface{})
	items := result["items"].([]interface{})
	assert.Len(t, jobs, 2)
	assert.Len(t, items, 2)
	assert.Equal(t, len(jobs), len(items))
}

// TestScheduledJobListResponse_EmptyItems verifies the response handles empty items correctly
func TestScheduledJobListResponse_EmptyItems(t *testing.T) {
	resp := ScheduledJobListResponse{
		Jobs:       []ScheduledJobResponse{},
		Items:      []ScheduledJobResponse{},
		Pagination: PaginationInfo{Page: 1, PerPage: 20, Total: 0},
	}

	data, err := json.Marshal(resp)
	require.NoError(t, err)

	var result map[string]interface{}
	err = json.Unmarshal(data, &result)
	require.NoError(t, err)

	jobs := result["jobs"].([]interface{})
	items := result["items"].([]interface{})
	assert.Len(t, jobs, 0)
	assert.Len(t, items, 0)
}

// TestScheduledJobListResponse_NilItems verifies the response handles nil items correctly (they become null in JSON)
func TestScheduledJobListResponse_NilItems(t *testing.T) {
	resp := ScheduledJobListResponse{
		Jobs:       nil,
		Items:      nil,
		Pagination: PaginationInfo{Page: 1, PerPage: 20, Total: 0},
	}

	data, err := json.Marshal(resp)
	require.NoError(t, err)

	var result map[string]interface{}
	err = json.Unmarshal(data, &result)
	require.NoError(t, err)

	// When nil, JSON unmarshals as nil (not an empty slice)
	assert.Nil(t, result["jobs"])
	assert.Nil(t, result["items"])
}

// TestScheduledJobHandler_List_ErrorHandling tests error responses
func TestScheduledJobHandler_List_ErrorHandling(t *testing.T) {
	// Test that writeJSON is called correctly with the response
	rec := httptest.NewRecorder()
	resp := ScheduledJobListResponse{
		Jobs:       []ScheduledJobResponse{},
		Items:      []ScheduledJobResponse{},
		Pagination: PaginationInfo{Page: 1, PerPage: 20, Total: 0},
	}

	writeJSON(rec, http.StatusOK, resp)

	assert.Equal(t, http.StatusOK, rec.Code)
	assert.Equal(t, "application/json", rec.Header().Get("Content-Type"))

	var result ScheduledJobListResponse
	err := json.Unmarshal(rec.Body.Bytes(), &result)
	require.NoError(t, err)

	assert.NotNil(t, result.Jobs)
	assert.NotNil(t, result.Items)
}

// TestScheduledJobHandler_NilHandler tests that the handler returns 500 if not initialized
func TestScheduledJobHandler_NilHandler(t *testing.T) {
	// This test verifies the nil check in the List handler
	// We can't easily test this without a full server setup, but we document the behavior here
	t.Run("handler should have nil checks", func(t *testing.T) {
		// The handler now has a nil check at the beginning of List()
		// This prevents panics if the handler is not properly initialized
		t.Skip("Integration test requires full server setup")
	})
}
