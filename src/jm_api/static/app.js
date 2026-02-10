const TABLES = ["bots"];

document.addEventListener("DOMContentLoaded", function () {
  // Detect which page we're on
  if (document.getElementById("data-table")) {
    initTablePage();
  }
});

function initTablePage() {
  const params = new URLSearchParams(location.search);
  const table = params.get("table");

  if (!table) {
    showError("No table specified in URL.");
    return;
  }

  if (!TABLES.includes(table)) {
    showError("Unknown table: " + table);
    return;
  }

  const titleEl = document.getElementById("table-title");
  if (titleEl) {
    titleEl.textContent = table;
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

  // Build header row using safe DOM APIs
  var headerRow = document.createElement("tr");
  for (var i = 0; i < headers.length; i++) {
    var th = document.createElement("th");
    th.textContent = headers[i];
    headerRow.appendChild(th);
  }
  thead.appendChild(headerRow);

  // Build body rows using safe DOM APIs
  for (var r = 0; r < items.length; r++) {
    var tr = document.createElement("tr");
    for (var c = 0; c < headers.length; c++) {
      var td = document.createElement("td");
      var val = items[r][headers[c]];
      td.textContent = val !== null && val !== undefined ? val : "";
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
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
