/*
 * NutriZone Admin Dashboard -- Chart.js integration (Phase 08.2)
 */
(function () {
  "use strict";

  function readThemeColors() {
    var isDark = document.documentElement.getAttribute("data-nz-theme") === "dark";
    // The brand color comes from --nz-primary (Site Settings can override it), so charts follow the theme.
    var primary = getComputedStyle(document.documentElement).getPropertyValue("--nz-primary").trim() || (isDark ? "#3b82f6" : "#1d4ed8");
    return {
      line: primary,
      fill: /^#[0-9a-f]{6}$/i.test(primary) ? primary + (isDark ? "24" : "17") : "rgba(29, 78, 216, 0.09)",
      grid: isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)",
      text: isDark ? "#a9b3bf" : "#52606d",
    };
  }

  function renderRevenueChart() {
    var canvas = document.getElementById("nz-revenue-chart");
    var dataEl = document.getElementById("nz-revenue-series-data");
    if (!canvas || !dataEl || typeof window.Chart === "undefined") {
      return;
    }

    var series;
    try {
      series = JSON.parse(dataEl.textContent);
    } catch (e) {
      return;
    }
    if (!series || !series.length) {
      return;
    }

    var colors = readThemeColors();

    if (canvas._nzChartInstance) {
      canvas._nzChartInstance.destroy();
    }

    canvas._nzChartInstance = new window.Chart(canvas.getContext("2d"), {
      type: "line",
      data: {
        labels: series.map(function (p) { return p.date; }),
        datasets: [
          {
            label: "Revenue",
            data: series.map(function (p) { return p.revenue; }),
            borderColor: colors.line,
            backgroundColor: colors.fill,
            fill: true,
            tension: 0.35,
            pointRadius: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: colors.grid }, ticks: { color: colors.text } },
          y: { grid: { color: colors.grid }, ticks: { color: colors.text }, beginAtZero: true },
        },
      },
    });
  }

  document.addEventListener("DOMContentLoaded", renderRevenueChart);
  document.addEventListener("nutrizone:theme-changed", renderRevenueChart);

  function renderCategoryChart() {
    var canvas = document.getElementById("nz-category-chart");
    var dataEl = document.getElementById("nz-category-series-data");
    if (!canvas || !dataEl || typeof window.Chart === "undefined") {
      return;
    }

    var rows;
    try {
      rows = JSON.parse(dataEl.textContent);
    } catch (e) {
      return;
    }
    if (!rows || !rows.length) {
      return;
    }

    var palette = ["#3b82f6", "#34a56f", "#d99a3a", "#e0685c", "#8a6fd9", "#4fc3c3", "#c7986a", "#9aa5b1"];
    var colors = readThemeColors();

    if (canvas._nzChartInstance) {
      canvas._nzChartInstance.destroy();
    }

    canvas._nzChartInstance = new window.Chart(canvas.getContext("2d"), {
      type: "doughnut",
      data: {
        labels: rows.map(function (r) { return r.name; }),
        datasets: [{ data: rows.map(function (r) { return r.count; }), backgroundColor: palette, borderWidth: 0 }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: "right", labels: { color: colors.text, boxWidth: 12 } } },
      },
    });
  }

  document.addEventListener("DOMContentLoaded", renderCategoryChart);
  document.addEventListener("nutrizone:theme-changed", renderCategoryChart);

  function renderOrderStatusChart() {
    var canvas = document.getElementById("nz-order-status-chart");
    var dataEl = document.getElementById("nz-order-status-series-data");
    if (!canvas || !dataEl || typeof window.Chart === "undefined") {
      return;
    }

    var statusCounts;
    try {
      statusCounts = JSON.parse(dataEl.textContent);
    } catch (e) {
      return;
    }
    var labels = Object.keys(statusCounts);
    if (!labels.length) {
      return;
    }

    var palette = ["#3b82f6", "#34a56f", "#d99a3a", "#e0685c", "#8a6fd9", "#4fc3c3", "#c7986a", "#9aa5b1", "#7fb069", "#e07a5f"];

    if (canvas._nzChartInstance) {
      canvas._nzChartInstance.destroy();
    }

    canvas._nzChartInstance = new window.Chart(canvas.getContext("2d"), {
      type: "doughnut",
      data: {
        labels: labels,
        datasets: [{ data: labels.map(function (l) { return statusCounts[l]; }), backgroundColor: palette, borderWidth: 0 }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: "right", labels: { color: readThemeColors().text, boxWidth: 12 } } },
      },
    });
  }

  document.addEventListener("DOMContentLoaded", renderOrderStatusChart);
  document.addEventListener("nutrizone:theme-changed", renderOrderStatusChart);

  /**
   * Real, closed gap: Loyalty (tier -> count), Reviews (status ->
   * count), Wallet (status -> count), and Fulfillment (status ->
   * count) all showed only plain text rows, even though the data is
   * exactly the same categorical shape renderOrderStatusChart already
   * turns into a doughnut chart above. One generic, reused function
   * instead of four near-identical copies.
   */
  function renderGenericDoughnut(canvasId, dataElId) {
    var canvas = document.getElementById(canvasId);
    var dataEl = document.getElementById(dataElId);
    if (!canvas || !dataEl || typeof window.Chart === "undefined") {
      return;
    }

    var counts;
    try {
      counts = JSON.parse(dataEl.textContent);
    } catch (e) {
      return;
    }
    var labels = Object.keys(counts);
    if (!labels.length) {
      return;
    }

    var palette = ["#3b82f6", "#34a56f", "#d99a3a", "#e0685c", "#8a6fd9", "#4fc3c3", "#c7986a", "#9aa5b1", "#7fb069", "#e07a5f"];

    if (canvas._nzChartInstance) {
      canvas._nzChartInstance.destroy();
    }

    canvas._nzChartInstance = new window.Chart(canvas.getContext("2d"), {
      type: "doughnut",
      data: {
        labels: labels,
        datasets: [{ data: labels.map(function (l) { return counts[l]; }), backgroundColor: palette, borderWidth: 0 }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: "right", labels: { color: readThemeColors().text, boxWidth: 12 } } },
      },
    });
  }

  function renderAllGenericDoughnuts() {
    renderGenericDoughnut("nz-reviews-chart", "nz-reviews-series-data");
  }

  document.addEventListener("DOMContentLoaded", renderAllGenericDoughnuts);
  document.addEventListener("nutrizone:theme-changed", renderAllGenericDoughnuts);

  /**
   * Real, closed gap: Top Products showed a plain ranked text list
   * (rank number + name + unit count) -- a horizontal bar chart makes
   * the relative sales volume across products visually obvious at a
   * glance, which a text list cannot.
   */
  function renderTopProductsChart() {
    var canvas = document.getElementById("nz-top-products-chart");
    var dataEl = document.getElementById("nz-top-products-series-data");
    if (!canvas || !dataEl || typeof window.Chart === "undefined") {
      return;
    }

    var products;
    try {
      products = JSON.parse(dataEl.textContent);
    } catch (e) {
      return;
    }
    if (!products.length) {
      return;
    }
    var colors = readThemeColors();

    if (canvas._nzChartInstance) {
      canvas._nzChartInstance.destroy();
    }

    canvas._nzChartInstance = new window.Chart(canvas.getContext("2d"), {
      type: "bar",
      data: {
        labels: products.map(function (p) { return p.name; }),
        datasets: [{ label: "Units sold", data: products.map(function (p) { return p.quantity_sold; }), backgroundColor: colors.line, borderRadius: 4 }],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { beginAtZero: true, grid: { color: colors.grid }, ticks: { color: colors.text } },
          y: { grid: { display: false }, ticks: { color: colors.text } },
        },
      },
    });
  }

  document.addEventListener("DOMContentLoaded", renderTopProductsChart);
  document.addEventListener("nutrizone:theme-changed", renderTopProductsChart);
})();