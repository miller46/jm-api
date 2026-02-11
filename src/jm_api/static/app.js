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
