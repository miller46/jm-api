const TABLES = ["bots"];

// Sort state — no sort applied on initial load
var currentSortColumn = null;
var currentSortDirection = null;
var currentHeaders = [];
var currentItems = [];
var currentTable = "";
var hiddenColumns = {};

document.addEventListener("DOMContentLoaded", function () {
  // Detect which page we're on
  if (document.getElementById("data-table")) {
    initTablePage();
  } else if (document.getElementById("create-form")) {
    initCreatePage();
  } else if (document.getElementById("edit-form")) {
    initEditPage();
  }
});

function initTablePage() {
  const params = new URLSearchParams(location.search);
  const table = params.get("table");
  currentTable = table || "";

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

  fetch(`/api/v1/${table}?per_page=20`)
    .then(function (response) {
      if (!response.ok) {
        throw new Error("HTTP " + response.status);
      }
      return response.json();
    })
    .then(function (data) {
      if (loadingEl) loadingEl.style.display = "none";

      const items = data.items;
      if (!items || items.length === 0) {
        showError("No records found.");
        return;
      }

      var headers = Object.keys(items[0]);
      currentHeaders = headers;
      currentItems = items;
      renderColumnToggles(headers);
      renderTable(headers, items);
    })
    .catch(function (err) {
      if (loadingEl) loadingEl.style.display = "none";
      showError("Failed to load data: " + err.message);
    });
}

function renderTable(headers, items) {
  var thead = document.getElementById("table-head");
  var tbody = document.getElementById("table-body");

  // Build header row with sort indicators
  var headerRow = "<tr>";
  for (var i = 0; i < headers.length; i++) {
    var hiddenClass = hiddenColumns[headers[i]] ? " col-hidden" : "";
    var sortIndicator = "";
    if (currentSortColumn === headers[i]) {
      sortIndicator = currentSortDirection === "asc" ? " \u25B2" : " \u25BC";
    }
    headerRow += '<th class="sortable-header' + hiddenClass + '" data-col-index="' + i + '">' + headers[i] + sortIndicator + "</th>";
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

  // Build body rows with row-level click navigation
  var bodyHtml = "";
  for (var r = 0; r < items.length; r++) {
    var rowId = items[r].id !== null && items[r].id !== undefined ? items[r].id : "";
    bodyHtml += '<tr data-row-id="' + rowId + '">';
    for (var c = 0; c < headers.length; c++) {
      var hiddenClass = hiddenColumns[headers[c]] ? " col-hidden" : "";
      var val = items[r][headers[c]];
      bodyHtml += '<td class="' + hiddenClass.trim() + '">' + (val !== null && val !== undefined ? val : "") + "</td>";
    }
    bodyHtml += "</tr>";
  }
  tbody.innerHTML = bodyHtml;

  // Attach row click handlers for navigation to edit page
  var rows = tbody.querySelectorAll("tr");
  for (var rr = 0; rr < rows.length; rr++) {
    rows[rr].addEventListener("click", function () {
      var rowId = this.getAttribute("data-row-id");
      if (currentTable && rowId !== "") {
        location.href = "edit.html?table=" + encodeURIComponent(currentTable) + "&id=" + encodeURIComponent(rowId);
      }
    });
  }
}

function sortByColumn(column) {
  if (currentSortColumn === column) {
    // Toggle direction
    currentSortDirection = currentSortDirection === "asc" ? "desc" : "asc";
  } else {
    currentSortColumn = column;
    currentSortDirection = "asc";
  }

  currentItems.sort(function (a, b) {
    var valA = a[column] !== null && a[column] !== undefined ? a[column] : "";
    var valB = b[column] !== null && b[column] !== undefined ? b[column] : "";

    if (typeof valA === "string") valA = valA.toLowerCase();
    if (typeof valB === "string") valB = valB.toLowerCase();

    if (valA < valB) return currentSortDirection === "asc" ? -1 : 1;
    if (valA > valB) return currentSortDirection === "asc" ? 1 : -1;
    return 0;
  });

  renderTable(currentHeaders, currentItems);
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
    delete hiddenColumns[column];
  } else {
    hiddenColumns[column] = true;
  }
  renderTable(currentHeaders, currentItems);
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

function initEditPage() {
  // Placeholder for edit page initialization
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
