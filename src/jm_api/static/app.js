const TABLES = ["bots"];

document.addEventListener("DOMContentLoaded", function () {
  // Detect which page we're on
  if (document.getElementById("data-table")) {
    initTablePage();
  } else if (document.getElementById("create-form")) {
    initCreatePage();
  }
});

function initTablePage() {
  const params = new URLSearchParams(location.search);
  const table = params.get("table");

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

  // Build header row
  var headerRow = "<tr>";
  for (var i = 0; i < headers.length; i++) {
    headerRow += "<th>" + headers[i] + "</th>";
  }
  headerRow += "</tr>";
  thead.innerHTML = headerRow;

  // Build body rows
  var bodyHtml = "";
  for (var r = 0; r < items.length; r++) {
    bodyHtml += "<tr>";
    for (var c = 0; c < headers.length; c++) {
      var val = items[r][headers[c]];
      bodyHtml += "<td>" + (val !== null && val !== undefined ? val : "") + "</td>";
    }
    bodyHtml += "</tr>";
  }
  tbody.innerHTML = bodyHtml;
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

  // Discover fields from OpenAPI schema (works even when table is empty)
  fetch("/openapi.json")
    .then(function (response) {
      if (!response.ok) {
        throw new Error("HTTP " + response.status);
      }
      return response.json();
    })
    .then(function (schema) {
      var fields = discoverFieldsFromSchema(schema, table);
      if (fields.length === 0) {
        showError(
          "Cannot determine fields for '" +
            table +
            "'. No create schema found in API spec."
        );
        return;
      }
      renderCreateForm(table, fields);
    })
    .catch(function (err) {
      showError("Failed to load field info: " + err.message);
    });
}

function discoverFieldsFromSchema(schema, table) {
  // Look for a POST endpoint for this table and extract the request body schema
  var postPath = "/api/v1/" + table;
  var paths = schema.paths || {};
  var pathObj = paths[postPath];
  if (!pathObj || !pathObj.post) {
    return [];
  }

  var requestBody = pathObj.post.requestBody;
  if (!requestBody || !requestBody.content) {
    return [];
  }

  var jsonContent = requestBody.content["application/json"];
  if (!jsonContent || !jsonContent.schema) {
    return [];
  }

  var ref = jsonContent.schema["$ref"];
  if (!ref) {
    // Inline schema — read properties directly
    return Object.keys(jsonContent.schema.properties || {});
  }

  // Resolve $ref like "#/components/schemas/BotCreate"
  var parts = ref.replace("#/", "").split("/");
  var resolved = schema;
  for (var i = 0; i < parts.length; i++) {
    resolved = resolved[parts[i]];
    if (!resolved) return [];
  }

  return Object.keys(resolved.properties || {});
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
