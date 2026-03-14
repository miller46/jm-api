package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestTablesHandler_List(t *testing.T) {
	h := NewTablesHandler()

	req := httptest.NewRequest(http.MethodGet, "/api/tables", nil)
	w := httptest.NewRecorder()

	h.List(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", w.Code)
	}

	ct := w.Header().Get("Content-Type")
	if ct != "application/json" {
		t.Fatalf("expected Content-Type application/json, got %s", ct)
	}

	var resp struct {
		Tables []string `json:"tables"`
	}
	if err := json.NewDecoder(w.Body).Decode(&resp); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	if len(resp.Tables) == 0 {
		t.Fatal("expected at least one table")
	}

	// Should contain known tables
	expected := map[string]bool{"bots": false, "webhooks": false, "tasks": false}
	for _, table := range resp.Tables {
		if _, ok := expected[table]; ok {
			expected[table] = true
		}
	}
	for name, found := range expected {
		if !found {
			t.Errorf("expected table %q not found in response", name)
		}
	}

	// Should be sorted
	for i := 1; i < len(resp.Tables); i++ {
		if resp.Tables[i] < resp.Tables[i-1] {
			t.Errorf("tables not sorted: %v", resp.Tables)
			break
		}
	}
}

func TestTablesHandler_Schema(t *testing.T) {
	h := NewTablesHandler()

	req := httptest.NewRequest(http.MethodGet, "/api/schema", nil)
	w := httptest.NewRecorder()

	h.Schema(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", w.Code)
	}

	var resp map[string]TableSchema
	if err := json.NewDecoder(w.Body).Decode(&resp); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	// Should have entries for all known tables
	for _, name := range []string{"bots", "webhooks", "tasks"} {
		schema, ok := resp[name]
		if !ok {
			t.Errorf("missing schema for table %q", name)
			continue
		}
		if schema.CreateFields == nil {
			t.Errorf("table %q has nil create_fields", name)
		}
		if schema.Filters == nil {
			t.Errorf("table %q has nil filters", name)
		}
	}

	// Bots should have specific create fields
	botsFields := resp["bots"].CreateFields
	expectedFields := map[string]bool{"rig_id": false, "kill_switch": false, "last_run_log": false}
	for _, f := range botsFields {
		if _, ok := expectedFields[f]; ok {
			expectedFields[f] = true
		}
	}
	for name, found := range expectedFields {
		if !found {
			t.Errorf("bots missing create field %q", name)
		}
	}

	// Bots should have filter definitions
	botsFilters := resp["bots"].Filters
	if len(botsFilters) == 0 {
		t.Error("bots should have filters")
	}

	// Check a known filter exists
	foundRigID := false
	for _, f := range botsFilters {
		if f.Name == "rig_id" {
			foundRigID = true
			if f.Type != "string" {
				t.Errorf("rig_id filter type should be string, got %s", f.Type)
			}
			if f.Kind != "single" {
				t.Errorf("rig_id filter kind should be single, got %s", f.Kind)
			}
		}
	}
	if !foundRigID {
		t.Error("bots filters should include rig_id")
	}
}
