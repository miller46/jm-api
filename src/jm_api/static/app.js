const TABLES = ["bots"];

// Encapsulated table page state — avoids fragile module-level mutable globals
var TableState = {
  sortColumn: null,
  sortDirection: null,
  headers: [],
  originalItems: [],
  items: [],
  table: "",
  hiddenColumns: {},
  filterFields: []
};

/**
 * Escape HTML special characters to prevent XSS when interpolating
 * user-controlled or API-sourced data into innerHTML strings.
 */
function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/**
 * Discover filterable fields from the OpenAPI spec for a given table.
 * Fetches /openapi.json, extracts GET query parameters, excludes pagination
 * params (page, per_page), and groups DATE_RANGE _after/_before pairs.
 */
function discoverFilterFields(spec, table) {
  var pathKey = "/api/v1/" + table;
  var pathObj = spec.paths && spec.paths[pathKey];
  if (!pathObj || !pathObj.get) return [];

  var parameters = pathObj.get.parameters || [];
  var paginationParams = ["page", "per_page"];
  var fields = [];
  var dateRangeGroups = {};

  for (var i = 0; i < parameters.length; i++) {
    var param = parameters[i];
    if (param.in !== "query") continue;
    var name = param.name;

    // Exclude pagination params
    if (paginationParams.indexOf(name) !== -1) continue;

    // Detect DATE_RANGE pairs by _after/_before suffixes
    if (name.match(/_after$/)) {
      var baseName = name.replace(/_after$/, "");
      if (!dateRangeGroups[baseName]) {
        dateRangeGroups[baseName] = { after: null, before: null };
      }
      dateRangeGroups[baseName].after = name;
      continue;
    }
    if (name.match(/_before$/)) {
      var baseName = name.replace(/_before$/, "");
      if (!dateRangeGroups[baseName]) {
        dateRangeGroups[baseName] = { after: null, before: null };
      }
      dateRangeGroups[baseName].before = name;
      continue;
    }

    // Determine type from schema
    var schema = param.schema || {};
    var paramType = schema.type || "string";

    // Check for boolean type (could be in anyOf for nullable booleans)
    if (schema.anyOf) {
      for (var k = 0; k < schema.anyOf.length; k++) {
        if (schema.anyOf[k].type === "boolean") {
          paramType = "boolean";
          break;
        }
      }
    }

    fields.push({
      name: name,
      type: paramType,
      kind: "single"
    });
  }

  // Add grouped DATE_RANGE fields
  for (var base in dateRangeGroups) {
    if (dateRangeGroups.hasOwnProperty(base)) {
      fields.push({
        name: base,
        type: "datetime",
        kind: "date_range",
        afterParam: dateRangeGroups[base].after || base + "_after",
        beforeParam: dateRangeGroups[base].before || base + "_before"
      });
    }
  }

  return fields;
}

/**
 * Render filter input controls into the filter panel based on discovered fields.
 */
function renderFilterPanel(filterFields) {
  var container = document.getElementById("filter-inputs");
  if (!container) return;

  container.innerHTML = "";

  for (var i = 0; i < filterFields.length; i++) {
    var field = filterFields[i];
    var group = document.createElement("div");
    group.className = "form-group";

    if (field.kind === "date_range") {
      // DATE_RANGE: two datetime-local inputs (After / Before)
      var legend = document.createElement("label");
      legend.textContent = field.name;
      group.appendChild(legend);

      var afterLabel = document.createElement("label");
      afterLabel.textContent = "After";
      afterLabel.style.fontWeight = "normal";
      afterLabel.style.fontSize = "0.85rem";
      var afterInput = document.createElement("input");
      afterInput.type = "datetime-local";
      afterInput.setAttribute("data-filter", field.afterParam);
      afterInput.setAttribute("data-filter-kind", "date_range");
      afterLabel.appendChild(afterInput);
      group.appendChild(afterLabel);

      var beforeLabel = document.createElement("label");
      beforeLabel.textContent = "Before";
      beforeLabel.style.fontWeight = "normal";
      beforeLabel.style.fontSize = "0.85rem";
      var beforeInput = document.createElement("input");
      beforeInput.type = "datetime-local";
      beforeInput.setAttribute("data-filter", field.beforeParam);
      beforeInput.setAttribute("data-filter-kind", "date_range");
      beforeLabel.appendChild(beforeInput);
      group.appendChild(beforeLabel);

    } else if (field.type === "boolean") {
      // Boolean: <select> with Any / true / false
      var label = document.createElement("label");
      label.textContent = field.name;
      group.appendChild(label);

      var select = document.createElement("select");
      select.setAttribute("data-filter", field.name);
      select.setAttribute("data-filter-kind", "boolean");

      var optAny = document.createElement("option");
      optAny.value = "";
      optAny.textContent = "Any";
      select.appendChild(optAny);

      var optTrue = document.createElement("option");
      optTrue.value = "true";
      optTrue.textContent = "true";
      select.appendChild(optTrue);

      var optFalse = document.createElement("option");
      optFalse.value = "false";
      optFalse.textContent = "false";
      select.appendChild(optFalse);

      group.appendChild(select);

    } else {
      // String/ILIKE: text input
      var label = document.createElement("label");
      label.textContent = field.name;
      group.appendChild(label);

      var input = document.createElement("input");
      input.type = "text";
      input.setAttribute("data-filter", field.name);
      input.setAttribute("data-filter-kind", "text");
      input.placeholder = "Filter by " + field.name;
      group.appendChild(input);
    }

    container.appendChild(group);
  }

  // Add Apply Filters and Clear buttons
  var btnGroup = document.createElement("div");
  btnGroup.className = "filter-buttons";

  var applyBtn = document.createElement("button");
  applyBtn.type = "button";
  applyBtn.className = "btn btn-primary";
  applyBtn.textContent = "Apply Filters";
  applyBtn.addEventListener("click", function () {
    applyFilters();
  });
  btnGroup.appendChild(applyBtn);

  var clearBtn = document.createElement("button");
  clearBtn.type = "button";
  clearBtn.className = "btn btn-secondary";
  clearBtn.textContent = "Clear";
  clearBtn.addEventListener("click", function () {
    clearFilters();
  });
  btnGroup.appendChild(clearBtn);

  container.appendChild(btnGroup);
}

/**
 * Shared helper: fetch data from the API with the given params, update
 * TableState, re-apply current sort (without toggling direction), and
 * re-render the table.  Used by both applyFilters() and clearFilters()
 * to avoid duplicating fetch → parse → sort → render logic.
 */
function fetchAndRender(params) {
  var url = "/api/v1/" + TableState.table + "?" + params.toString();
  var loadingEl = document.getElementById("loading");
  if (loadingEl) loadingEl.style.display = "block";

  fetch(url)
    .then(function (response) {
      if (!response.ok) {
        throw new Error("HTTP " + response.status);
      }
      return response.json();
    })
    .then(function (data) {
      if (loadingEl) loadingEl.style.display = "none";

      var items = data.items || [];
      var headers = items.length > 0 ? Object.keys(items[0]) : TableState.headers;
      TableState.headers = headers;
      TableState.originalItems = items.slice();
      TableState.items = items.slice();

      if (items.length === 0) {
        renderTable(TableState.headers, [], TableState.table);
        return;
      }

      // Re-apply current sort without toggling direction
      if (TableState.sortColumn) {
        reapplySort();
      } else {
        renderTable(headers, TableState.items, TableState.table);
      }
    })
    .catch(function (err) {
      if (loadingEl) loadingEl.style.display = "none";
      showError("Failed to load data: " + err.message);
    });
}

/**
 * Re-sort TableState.items using the current sortColumn and sortDirection
 * without toggling the direction.  This preserves sort state when
 * re-rendering after filter apply / clear.
 */
function reapplySort() {
  var column = TableState.sortColumn;
  var sorted = TableState.originalItems.slice().sort(function (a, b) {
    var valA = a[column] !== null && a[column] !== undefined ? a[column] : "";
    var valB = b[column] !== null && b[column] !== undefined ? b[column] : "";

    if (typeof valA === "string") valA = valA.toLowerCase();
    if (typeof valB === "string") valB = valB.toLowerCase();

    if (valA < valB) return TableState.sortDirection === "asc" ? -1 : 1;
    if (valA > valB) return TableState.sortDirection === "asc" ? 1 : -1;
    return 0;
  });

  TableState.items = sorted;
  renderTable(TableState.headers, sorted, TableState.table);
}

/**
 * Collect non-empty filter values and refetch data from the API.
 */
function applyFilters() {
  var container = document.getElementById("filter-inputs");
  if (!container) return;

  var params = new URLSearchParams();
  params.append("page", "1");
  params.append("per_page", "20");

  // Collect all filter inputs
  var inputs = container.querySelectorAll("[data-filter]");
  for (var i = 0; i < inputs.length; i++) {
    var el = inputs[i];
    var paramName = el.getAttribute("data-filter");
    var val = el.value;
    if (val !== "" && val !== null && val !== undefined) {
      params.append(paramName, val);
    }
  }

  fetchAndRender(params);
}

/**
 * Reset all filter inputs to empty/default and refetch unfiltered data.
 */
function clearFilters() {
  var container = document.getElementById("filter-inputs");
  if (!container) return;

  // Reset all filter inputs
  var inputs = container.querySelectorAll("[data-filter]");
  for (var i = 0; i < inputs.length; i++) {
    var el = inputs[i];
    if (el.tagName.toLowerCase() === "select") {
      el.selectedIndex = 0;
    } else {
      el.value = "";
    }
  }

  // Refetch unfiltered data
  var params = new URLSearchParams();
  params.append("page", "1");
  params.append("per_page", "20");
  fetchAndRender(params);
}

document.addEventListener("DOMContentLoaded", function () {
  // Detect which page we're on
  if (document.getElementById("data-table")) {
    initTablePage();
  } else if (document.getElementById("edit-form")) {
    initEditPage();
  } else if (document.getElementById("create-form")) {
    initCreatePage();
  }
});

function initTablePage() {
  const params = new URLSearchParams(location.search);
  const table = params.get("table");
  TableState.table = table || "";

  if (!table) {
    showError("No table specified in URL.");
    return;
  }

  const titleEl = document.getElementById("table-title");
  if (titleEl) {
    titleEl.textContent = table;
  }

  var addBtn = document.getElementById("add-record-btn");
  if (addBtn) {
    addBtn.href = "create.html?table=" + encodeURIComponent(table);
  }

  const loadingEl = document.getElementById("loading");
  const errorEl = document.getElementById("error");

  // Fetch data and OpenAPI spec in parallel
  Promise.all([
    fetch("/api/v1/" + table + "?per_page=20").then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }),
    fetch("/openapi.json").then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
  ])
    .then(function (results) {
      var data = results[0];
      var spec = results[1];

      if (loadingEl) loadingEl.style.display = "none";

      const items = data.items;
      if (!items || items.length === 0) {
        showError("No records found.");
        return;
      }

      var headers = Object.keys(items[0]);
      TableState.headers = headers;
      TableState.originalItems = items.slice();
      TableState.items = items.slice();
      renderColumnToggles(headers);
      renderTable(headers, TableState.items, table);

      // Discover and render filter panel
      var filterFields = discoverFilterFields(spec, table);
      TableState.filterFields = filterFields;
      renderFilterPanel(filterFields);
    })
    .catch(function (err) {
      if (loadingEl) loadingEl.style.display = "none";
      showError("Failed to load data: " + err.message);
    });
}

function renderTable(headers, items, table) {
  var thead = document.getElementById("table-head");
  var tbody = document.getElementById("table-body");

  // Build header row with sort indicators
  var headerRow = "<tr>";
  for (var i = 0; i < headers.length; i++) {
    var hiddenClass = TableState.hiddenColumns[headers[i]] ? " col-hidden" : "";
    var sortIndicator = "";
    if (TableState.sortColumn === headers[i]) {
      sortIndicator = TableState.sortDirection === "asc" ? " \u25B2" : " \u25BC";
    }
    headerRow += '<th class="sortable-header' + hiddenClass + '" data-col-index="' + i + '">' + escapeHtml(headers[i]) + sortIndicator + "</th>";
  }
  headerRow += "</tr>";
  thead.innerHTML = headerRow;

  // Attach click handlers to <th> for sorting
  var thElements = thead.querySelectorAll("th");
  for (var t = 0; t < thElements.length; t++) {
    thElements[t].addEventListener("click", function () {
      var colIndex = parseInt(this.getAttribute("data-col-index"), 10);
      sortByColumn(headers[colIndex]);
    });
  }

  // Build body rows — first column (id) links to edit page
  var bodyHtml = "";
  for (var r = 0; r < items.length; r++) {
    var rowId = items[r].id !== null && items[r].id !== undefined ? items[r].id : "";
    bodyHtml += '<tr data-row-id="' + escapeHtml(rowId) + '">';
    for (var c = 0; c < headers.length; c++) {
      var hiddenClass = TableState.hiddenColumns[headers[c]] ? " col-hidden" : "";
      var val = items[r][headers[c]];
      var display = val !== null && val !== undefined ? val : "";
      if (c === 0 && table) {
        // Make the id column a clickable link to the edit page
        var editHref = "edit.html?table=" + encodeURIComponent(table) + "&id=" + encodeURIComponent(display);
        bodyHtml += '<td class="' + hiddenClass.trim() + '"><a href="' + editHref + '">' + escapeHtml(display) + "</a></td>";
      } else {
        bodyHtml += '<td class="' + hiddenClass.trim() + '">' + escapeHtml(val) + "</td>";
      }
    }
    bodyHtml += "</tr>";
  }
  tbody.innerHTML = bodyHtml;

  // Attach row click handlers — guarded: edit.html does not exist yet,
  // so log intent to console instead of navigating to a 404
  var rows = tbody.querySelectorAll("tr");
  for (var rr = 0; rr < rows.length; rr++) {
    rows[rr].addEventListener("click", function () {
      var rowId = this.getAttribute("data-row-id");
      if (TableState.table && rowId !== "") {
        // TODO: navigate to edit.html once it exists
        console.log("Row clicked: table=" + TableState.table + ", id=" + rowId);
      }
    });
  }
}

function sortByColumn(column) {
  if (TableState.sortColumn === column) {
    // Toggle direction
    TableState.sortDirection = TableState.sortDirection === "asc" ? "desc" : "asc";
  } else {
    TableState.sortColumn = column;
    TableState.sortDirection = "asc";
  }

  // Sort a shallow copy — never mutate originalItems
  var sorted = TableState.originalItems.slice().sort(function (a, b) {
    var valA = a[column] !== null && a[column] !== undefined ? a[column] : "";
    var valB = b[column] !== null && b[column] !== undefined ? b[column] : "";

    if (typeof valA === "string") valA = valA.toLowerCase();
    if (typeof valB === "string") valB = valB.toLowerCase();

    if (valA < valB) return TableState.sortDirection === "asc" ? -1 : 1;
    if (valA > valB) return TableState.sortDirection === "asc" ? 1 : -1;
    return 0;
  });

  TableState.items = sorted;
  renderTable(TableState.headers, sorted, TableState.table);
}

function renderColumnToggles(headers) {
  var container = document.getElementById("column-checkboxes");
  if (!container) return;

  container.innerHTML = "";
  for (var i = 0; i < headers.length; i++) {
    var label = document.createElement("label");
    label.style.marginRight = "1rem";
    var checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = true;
    checkbox.setAttribute("data-column", headers[i]);
    checkbox.addEventListener("change", function () {
      var col = this.getAttribute("data-column");
      toggleColumnVisibility(col, this.checked);
    });
    label.appendChild(checkbox);
    label.appendChild(document.createTextNode(" " + headers[i]));
    container.appendChild(label);
  }
}

function toggleColumnVisibility(column, visible) {
  if (visible) {
    delete TableState.hiddenColumns[column];
  } else {
    TableState.hiddenColumns[column] = true;
  }
  renderTable(TableState.headers, TableState.items, TableState.table);
}

function showError(message) {
  var errorEl = document.getElementById("error");
  if (errorEl) {
    errorEl.textContent = message;
    errorEl.style.display = "block";
  }
  var loadingEl = document.getElementById("loading");
  if (loadingEl) {
    loadingEl.style.display = "none";
  }
}

function initEditPage() {
  var params = new URLSearchParams(location.search);
  var table = params.get("table");
  var id = params.get("id");

  if (!table || !id) {
    showError("Missing table or id in URL.");
    return;
  }

  var titleEl = document.getElementById("edit-title");
  if (titleEl) {
    titleEl.textContent = "Edit " + table + " Record";
  }

  // Update back link to point to the correct table
  var backLink = document.getElementById("back-link");
  if (backLink) {
    backLink.href = "table.html?table=" + encodeURIComponent(table);
  }

  // Fetch the existing record and field schema, then render form
  Promise.all([
    fetch("/api/v1/" + table + "/" + id).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }),
    fetch("/openapi.json").then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }),
  ])
    .then(function (results) {
      var record = results[0];
      var spec = results[1];
      var fields = discoverCreateFields(spec, table);
      if (!fields || fields.length === 0) {
        showError("Cannot determine fields for " + table + " from API schema.");
        return;
      }
      renderEditForm(table, id, fields, record);
    })
    .catch(function (err) {
      showError("Failed to load record: " + err.message);
    });
}

function renderEditForm(table, id, fields, record) {
  var form = document.getElementById("edit-form");
  if (!form) return;

  // Use DOM APIs instead of innerHTML to prevent XSS from record values
  for (var j = 0; j < fields.length; j++) {
    var field = fields[j];
    var currentVal = record[field];
    var displayVal = currentVal !== null && currentVal !== undefined ? String(currentVal) : "";

    var group = document.createElement("div");
    group.setAttribute("class", "form-group");

    var label = document.createElement("label");
    label.setAttribute("for", "field-" + field);
    label.textContent = field;
    group.appendChild(label);

    var input = document.createElement("input");
    input.setAttribute("type", "text");
    input.setAttribute("id", "field-" + field);
    input.setAttribute("name", field);
    input.setAttribute("value", displayVal);
    group.appendChild(input);

    form.appendChild(group);
  }

  var btn = document.createElement("button");
  btn.setAttribute("type", "submit");
  btn.setAttribute("class", "btn btn-primary");
  btn.textContent = "Save";
  form.appendChild(btn);

  var deleteBtn = document.createElement("button");
  deleteBtn.setAttribute("type", "button");
  deleteBtn.setAttribute("class", "btn btn-danger");
  deleteBtn.textContent = "Delete";
  deleteBtn.addEventListener("click", function () {
    if (confirm("Are you sure you want to delete this record?")) {
      fetch("/api/v1/" + table + "/" + id, { method: "DELETE" })
        .then(function (response) {
          if (!response.ok) {
            return response.json().then(function (err) {
              throw new Error(formatError(err));
            });
          }
          location.href = "table.html?table=" + encodeURIComponent(table);
        })
        .catch(function (err) {
          showError(err.message);
        });
    }
  });
  form.appendChild(deleteBtn);

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    submitEditForm(table, id, fields);
  });
}

function submitEditForm(table, id, fields) {
  var errorEl = document.getElementById("error");
  if (errorEl) {
    errorEl.style.display = "none";
  }

  var body = {};
  for (var i = 0; i < fields.length; i++) {
    var input = document.getElementById("field-" + fields[i]);
    if (input && input.value !== "") {
      // Try to parse booleans
      if (input.value === "true") {
        body[fields[i]] = true;
      } else if (input.value === "false") {
        body[fields[i]] = false;
      } else {
        body[fields[i]] = input.value;
      }
    }
  }

  fetch("/api/v1/" + table + "/" + id, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
    .then(function (response) {
      if (!response.ok) {
        return response.json().then(function (err) {
          throw new Error(formatError(err));
        });
      }
      // Success — redirect to table page
      location.href = "table.html?table=" + encodeURIComponent(table);
    })
    .catch(function (err) {
      showError(err.message);
    });
}

function initCreatePage() {
  var params = new URLSearchParams(location.search);
  var table = params.get("table");

  if (!table) {
    showError("No table specified in URL.");
    return;
  }

  var titleEl = document.getElementById("create-title");
  if (titleEl) {
    titleEl.textContent = "Create " + table + " Record";
  }

  // Discover create-schema fields from the OpenAPI spec.
  // This avoids hardcoding auto-fields and works even when the table is empty.
  fetch("/openapi.json")
    .then(function (response) {
      if (!response.ok) {
        throw new Error("HTTP " + response.status);
      }
      return response.json();
    })
    .then(function (spec) {
      var fields = discoverCreateFields(spec, table);
      if (!fields || fields.length === 0) {
        showError("Cannot determine fields for " + table + " from API schema.");
        return;
      }
      renderCreateForm(table, fields);
    })
    .catch(function (err) {
      showError("Failed to load field info: " + err.message);
    });
}

/**
 * Extract field names from the OpenAPI create schema for the given table.
 * Looks for a POST endpoint on /api/v1/{table} and reads its requestBody schema.
 */
function discoverCreateFields(spec, table) {
  var pathKey = "/api/v1/" + table;
  var pathObj = spec.paths && spec.paths[pathKey];
  if (!pathObj || !pathObj.post) return [];

  var requestBody = pathObj.post.requestBody;
  if (!requestBody) return [];

  var content = requestBody.content && requestBody.content["application/json"];
  if (!content || !content.schema) return [];

  var schema = content.schema;

  // Resolve $ref if present (e.g. "#/components/schemas/BotCreate")
  if (schema["$ref"]) {
    schema = resolveRef(spec, schema["$ref"]);
  }

  if (!schema || !schema.properties) return [];

  return Object.keys(schema.properties);
}

/**
 * Resolve a JSON $ref pointer within the OpenAPI spec.
 * Handles refs like "#/components/schemas/BotCreate".
 */
function resolveRef(spec, ref) {
  if (!ref || ref.charAt(0) !== "#") return null;
  var parts = ref.substring(2).split("/");
  var current = spec;
  for (var i = 0; i < parts.length; i++) {
    current = current[parts[i]];
    if (!current) return null;
  }
  return current;
}

function renderCreateForm(table, fields) {
  var form = document.getElementById("create-form");
  if (!form) return;

  var html = "";
  for (var j = 0; j < fields.length; j++) {
    var field = fields[j];
    html += '<div class="form-group">';
    html += '<label for="field-' + field + '">' + field + "</label>";
    html += '<input type="text" id="field-' + field + '" name="' + field + '">';
    html += "</div>";
  }
  html += '<button type="submit" class="btn btn-primary">Create</button>';
  form.innerHTML = html;

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    submitCreateForm(table, fields);
  });
}

function submitCreateForm(table, fields) {
  var errorEl = document.getElementById("error");
  if (errorEl) {
    errorEl.style.display = "none";
  }

  var body = {};
  for (var i = 0; i < fields.length; i++) {
    var input = document.getElementById("field-" + fields[i]);
    if (input && input.value !== "") {
      // Try to parse booleans
      if (input.value === "true") {
        body[fields[i]] = true;
      } else if (input.value === "false") {
        body[fields[i]] = false;
      } else {
        body[fields[i]] = input.value;
      }
    }
  }

  fetch("/api/v1/" + table, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
    .then(function (response) {
      if (!response.ok) {
        return response.json().then(function (err) {
          throw new Error(formatError(err));
        });
      }
      // Success — redirect to table page
      location.href = "table.html?table=" + encodeURIComponent(table);
    })
    .catch(function (err) {
      showError(err.message);
    });
}

function formatError(err) {
  if (err.detail) {
    if (Array.isArray(err.detail)) {
      return err.detail
        .map(function (e) {
          return (e.loc ? e.loc.join(".") + ": " : "") + e.msg;
        })
        .join("; ");
    }
    if (typeof err.detail === "string") {
      return err.detail;
    }
    return JSON.stringify(err.detail);
  }
  return JSON.stringify(err);
}
