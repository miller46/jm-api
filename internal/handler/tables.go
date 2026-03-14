package handler

import "net/http"

// TablesHandler returns the list of available resource tables and their schemas.
type TablesHandler struct{}

func NewTablesHandler() *TablesHandler {
	return &TablesHandler{}
}

// tables is the sorted list of API resource tables exposed by the dashboard.
var tables = []string{"bots", "tasks", "webhooks"}

func (h *TablesHandler) List(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string][]string{"tables": tables})
}

// FilterField describes a query parameter filter for a table's list endpoint.
type FilterField struct {
	Name       string `json:"name"`
	Type       string `json:"type"`
	Kind       string `json:"kind"`
	AfterParam string `json:"afterParam,omitempty"`
	BeforeParam string `json:"beforeParam,omitempty"`
}

// TableSchema describes the filter and create metadata for a table.
type TableSchema struct {
	Filters      []FilterField `json:"filters"`
	CreateFields []string      `json:"create_fields"`
}

var tableSchemas = map[string]TableSchema{
	"bots": {
		Filters: []FilterField{
			{Name: "rig_id", Type: "string", Kind: "single"},
			{Name: "kill_switch", Type: "boolean", Kind: "single"},
			{Name: "log_search", Type: "string", Kind: "single"},
			{Name: "create_at", Type: "datetime", Kind: "date_range", AfterParam: "create_at_from", BeforeParam: "create_at_to"},
			{Name: "last_update_at", Type: "datetime", Kind: "date_range", AfterParam: "last_update_at_from", BeforeParam: "last_update_at_to"},
			{Name: "last_run_at", Type: "datetime", Kind: "date_range", AfterParam: "last_run_at_from", BeforeParam: "last_run_at_to"},
		},
		CreateFields: []string{"rig_id", "kill_switch", "last_run_log"},
	},
	"webhooks": {
		Filters:      []FilterField{},
		CreateFields: []string{"target_url", "event_types", "secret"},
	},
	"tasks": {
		Filters:      []FilterField{},
		CreateFields: []string{"type", "payload"},
	},
}

func (h *TablesHandler) Schema(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, tableSchemas)
}
