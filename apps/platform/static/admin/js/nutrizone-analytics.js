/*
 * Dashboard → Analitika: revenue chart (store tills vs online, stacked by day / hour) and the payment-method donut.
 * Data: the #nza-data JSON (analytics_view._chart_data). Re-themes when the dashboard theme switch flips.
 */
(function () {
  "use strict";

  var el = document.getElementById("nza-data");
  if (!el || typeof window.Chart === "undefined") return;
  var data;
  try { data = JSON.parse(el.textContent); } catch (e) { return; }

  var PAY = ["#4f46e5", "#06b6d4", "#22c55e", "#f59e0b", "#ec4899", "#8b5cf6", "#14b8a6", "#ef4444"];
  var charts = [];

  function isDark() {
    var t = document.documentElement.getAttribute("data-nz-theme");
    if (t) return t === "dark";
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  }
  function money(n) { return Math.round(n || 0).toLocaleString("ru-RU").replace(/\s/g, " ") + " so'm"; }
  function compact(n) {
    var a = Math.abs(n);
    if (a >= 1e9) return (n / 1e9).toFixed(1).replace(/\.0$/, "").replace(".", ",") + " mlrd";
    if (a >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, "").replace(".", ",") + " mln";
    if (a >= 1e3) return Math.round(n / 1e3) + " ming";
    return String(Math.round(n));
  }
  function colors() {
    var dark = isDark();
    return { grid: dark ? "rgba(148,163,184,.12)" : "rgba(15,23,42,.07)", text: dark ? "#94a3b8" : "#64748b", tipBg: dark ? "#0f172a" : "#ffffff", tipText: dark ? "#e2e8f0" : "#0f172a", border: dark ? "#1b212b" : "#ffffff" };
  }
  function gradient(ctx, area, color) {
    var g = ctx.createLinearGradient(0, area.bottom, 0, area.top);
    g.addColorStop(0, color + "99");
    g.addColorStop(1, color);
    return g;
  }

  function build() {
    charts.forEach(function (c) { c.destroy(); });
    charts = [];
    var c = colors();
    var tooltip = {
      backgroundColor: c.tipBg, titleColor: c.tipText, bodyColor: c.tipText, borderColor: "rgba(99,102,241,.35)", borderWidth: 1,
      padding: 12, cornerRadius: 12, boxPadding: 4, usePointStyle: true,
    };

    var rev = document.getElementById("nza-revenue");
    var s = data.series || {};
    if (rev && s.labels && s.labels.length) {
      charts.push(new Chart(rev, {
        type: "bar",
        data: {
          labels: s.labels,
          datasets: [
            { label: "Do'konlar", data: s.pos, stack: "r", borderRadius: 6, borderSkipped: false, maxBarThickness: 34,
              backgroundColor: function (ctx) { var a = ctx.chart.chartArea; return a ? gradient(ctx.chart.ctx, a, "#4f46e5") : "#4f46e5"; } },
            { label: "Onlayn", data: s.online, stack: "r", borderRadius: 6, borderSkipped: false, maxBarThickness: 34,
              backgroundColor: function (ctx) { var a = ctx.chart.chartArea; return a ? gradient(ctx.chart.ctx, a, "#06b6d4") : "#06b6d4"; } },
          ].concat((s.previous || []).some(function (v) { return v > 0; }) ? [{
            label: "Oldingi davr", type: "line", data: s.previous, borderColor: "#f59e0b", backgroundColor: "#f59e0b", borderWidth: 2,
            borderDash: [6, 4], pointRadius: 0, pointHoverRadius: 4, tension: 0.35, order: -1,
          }] : []),
        },
        options: {
          responsive: true, maintainAspectRatio: false, animation: { duration: 500 },
          interaction: { mode: "index", intersect: false },
          plugins: {
            legend: { display: false },
            tooltip: Object.assign({}, tooltip, {
              callbacks: {
                label: function (ctx) { return " " + ctx.dataset.label + ": " + money(ctx.parsed.y); },
                footer: function (items) { var t = 0; items.forEach(function (i) { if (i.dataset.stack === "r") t += i.parsed.y; }); return "Jami: " + money(t); },
              },
            }),
          },
          scales: {
            x: { stacked: true, grid: { display: false }, ticks: { color: c.text, maxRotation: 0, autoSkipPadding: 10, font: { size: 11 } } },
            y: { stacked: true, beginAtZero: true, grid: { color: c.grid }, border: { display: false }, ticks: { color: c.text, font: { size: 11 }, callback: function (v) { return compact(v); } } },
          },
        },
      }));
    }

    var pay = document.getElementById("nza-payments");
    var rows = data.payments || [];
    if (pay && rows.length) {
      document.querySelectorAll("[data-pay]").forEach(function (i) { i.style.setProperty("--c", PAY[+i.getAttribute("data-pay") % PAY.length]); });
      charts.push(new Chart(pay, {
        type: "doughnut",
        data: { labels: rows.map(function (r) { return r.label; }), datasets: [{ data: rows.map(function (r) { return r.amount; }), backgroundColor: rows.map(function (_r, i) { return PAY[i % PAY.length]; }), borderColor: c.border, borderWidth: 3, hoverOffset: 6 }] },
        options: {
          responsive: true, maintainAspectRatio: false, cutout: "72%",
          plugins: { legend: { display: false }, tooltip: Object.assign({}, tooltip, { callbacks: { label: function (ctx) { return " " + ctx.label + ": " + money(ctx.parsed); } } }) },
        },
      }));
    }
  }

  build();
  new MutationObserver(build).observe(document.documentElement, { attributes: true, attributeFilter: ["data-nz-theme"] });
})();
