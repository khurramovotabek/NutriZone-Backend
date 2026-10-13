/*
 * NutriZone Dashboard -- "Online orders revenue": storefront orders per day, earned (delivered/completed)
 * vs still in the pipeline vs lost, with the number of orders placed as bars; status split and top cities.
 * Real data from /django-admin/dashboard/online-orders.json.
 */
(function () {
  "use strict";

  var root = document.getElementById("nz-online-orders");
  if (!root || typeof window.Chart === "undefined") return;

  var STATUS = {
    pending_payment: ["To'lov kutilmoqda", "#f59e0b"], confirmed: ["Tasdiqlangan", "#6366f1"], processing: ["Tayyorlanmoqda", "#8b5cf6"],
    shipped: ["Yo'lda", "#0ea5e9"], delivered: ["Yetkazilgan", "#10b981"], completed: ["Yakunlangan", "#16a34a"],
    cancelled: ["Bekor qilingan", "#ef4444"], returned: ["Qaytarilgan", "#f97316"], failed: ["Muvaffaqiyatsiz", "#b91c1c"],
  };
  var MONTHS = ["yan", "fev", "mar", "apr", "may", "iyn", "iyl", "avg", "sen", "okt", "noy", "dek"];
  var state = { range: "30d", chart: null, donut: null, data: null, ctrl: null };
  var canvas = root.querySelector("#nzoo-canvas");
  var tip = root.querySelector(".nzsc-tooltip");
  var box = root.querySelector(".nzsc-state");

  function money(n) { return Math.round(n || 0).toLocaleString("ru-RU").replace(/ /g, " "); }
  function compact(n) { var a = Math.abs(n); return a >= 1e9 ? (n / 1e9).toFixed(1).replace(/\.0$/, "") + " mlrd" : a >= 1e6 ? (n / 1e6).toFixed(a >= 1e7 ? 0 : 1).replace(/\.0$/, "") + " mln" : a >= 1e3 ? Math.round(n / 1e3) + " ming" : String(Math.round(n)); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function dark() { var t = document.documentElement.getAttribute("data-nz-theme"); return t ? t === "dark" : window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches; }
  function set(k, v) { var el = root.querySelector('[data-k="' + k + '"]'); if (el) el.textContent = v; }
  function day(iso) { return parseInt(iso.slice(8, 10), 10) + " " + MONTHS[parseInt(iso.slice(5, 7), 10) - 1]; }
  function fmt(iso) { return iso.slice(8, 10) + "." + iso.slice(5, 7) + "." + iso.slice(0, 4); }

  function load() {
    if (state.ctrl && state.ctrl.abort) state.ctrl.abort();
    state.ctrl = typeof AbortController !== "undefined" ? new AbortController() : null;
    root.classList.add("is-loading");
    fetch(root.getAttribute("data-endpoint") + "?range=" + state.range, { credentials: "same-origin", signal: state.ctrl ? state.ctrl.signal : undefined })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (d) { state.data = d; render(); })
      .catch(function (e) {
        if (e && e.name === "AbortError") return;
        box.hidden = false; box.setAttribute("data-state", "error");
        box.innerHTML = '<i class="fas fa-triangle-exclamation"></i> Ma\'lumotni yuklab bo\'lmadi <button type="button" class="nzsc-link" data-retry>Qayta urinish</button>';
      })
      .then(function () { root.classList.remove("is-loading"); });
  }

  function render() {
    var d = state.data, s = d.summary, p = dark();
    root.querySelector("[data-nzoo-period]").textContent = fmt(d.from) + " — " + fmt(d.to);
    set("revenue", money(s.revenue) + " so'm");
    var ch = root.querySelector('[data-k="change"]');
    ch.textContent = s.change_pct === null ? "Oldingi davrda yetkazilgan buyurtma yo'q" : (s.change_pct >= 0 ? "▲ +" : "▼ ") + s.change_pct + "% oldingi davrga";
    ch.style.color = s.change_pct === null ? "" : s.change_pct >= 0 ? "#16a34a" : "#dc2626";
    set("orders", String(s.orders));
    set("customers", s.earned_orders + " ta yetkazilgan · " + s.customers + " mijoz");
    set("pipeline", String(s.pipeline_orders));
    set("pipeline-sum", money(s.pipeline_value) + " so'm kutilmoqda");
    set("avg", money(s.average) + " so'm");
    set("loss", "Bekor/qaytarilgan: " + s.lost_orders + " (" + s.loss_rate + "%)");
    set("total-orders", String(s.orders));

    var grid = p ? "rgba(148,163,184,0.12)" : "rgba(15,23,42,0.07)", text = p ? "#94a3b8" : "#64748b";
    var hasLost = d.series.lost.some(function (v) { return v > 0; });
    var sets = [
      { type: "bar", label: "Buyurtmalar", data: d.series.orders, yAxisID: "y1", backgroundColor: p ? "rgba(148,163,184,0.18)" : "rgba(100,116,139,0.16)", borderRadius: 6, maxBarThickness: 18, order: 3 },
      { type: "line", label: "Daromad (yetkazilgan)", data: d.series.earned, borderColor: "#10b981", backgroundColor: "rgba(16,185,129,0.12)", fill: true, tension: 0.35, cubicInterpolationMode: "monotone", borderWidth: 2.5, pointRadius: d.labels.length > 40 ? 0 : 3, pointHoverRadius: 6, order: 1 },
      { type: "line", label: "Jarayonda", data: d.series.pipeline, borderColor: "#6366f1", borderDash: [6, 5], fill: false, tension: 0.35, cubicInterpolationMode: "monotone", borderWidth: 2, pointRadius: 0, pointHoverRadius: 5, order: 2 },
    ];
    if (hasLost) sets.push({ type: "line", label: "Yo'qotilgan", data: d.series.lost, borderColor: "#ef4444", borderDash: [2, 4], fill: false, tension: 0.35, borderWidth: 2, pointRadius: 0, pointHoverRadius: 5, order: 2 });

    if (state.chart) state.chart.destroy();
    state.chart = new window.Chart(canvas.getContext("2d"), {
      data: { labels: d.labels, datasets: sets },
      options: {
        responsive: true, maintainAspectRatio: false, animation: { duration: 280 }, interaction: { mode: "index", intersect: false },
        plugins: { legend: { position: "top", align: "end", labels: { color: text, usePointStyle: true, boxWidth: 8, font: { size: 11, weight: "600" } } }, tooltip: { enabled: false, external: tooltip } },
        scales: {
          x: { grid: { display: false }, border: { display: false }, ticks: { color: text, autoSkip: true, maxRotation: 0, maxTicksLimit: window.innerWidth < 640 ? 5 : 10, callback: function (v) { return day(this.getLabelForValue(v)); } } },
          y: { beginAtZero: true, grid: { color: grid, drawTicks: false }, border: { display: false }, ticks: { color: text, padding: 8, maxTicksLimit: 6, callback: function (v) { return compact(v); } } },
          y1: { position: "right", beginAtZero: true, grid: { display: false }, border: { display: false }, ticks: { color: text, precision: 0, maxTicksLimit: 5 } },
        },
      },
    });

    var statuses = Object.keys(d.statuses).sort(function (a, b) { return d.statuses[b] - d.statuses[a]; });
    if (state.donut) state.donut.destroy();
    state.donut = new window.Chart(root.querySelector("#nzoo-donut").getContext("2d"), {
      type: "doughnut",
      data: { labels: statuses.map(function (k) { return (STATUS[k] || [k])[0]; }), datasets: [{ data: statuses.map(function (k) { return d.statuses[k]; }), backgroundColor: statuses.map(function (k) { return (STATUS[k] || [0, "#94a3b8"])[1]; }), borderWidth: 0 }] },
      options: { responsive: true, maintainAspectRatio: false, cutout: "72%", plugins: { legend: { display: false } } },
    });
    root.querySelector("[data-statuses]").innerHTML = statuses.length ? statuses.map(function (k) {
      var meta = STATUS[k] || [k, "#94a3b8"];
      return '<li><i class="nzsc-dot" style="background:' + meta[1] + '"></i>' + esc(meta[0]) + "<b>" + d.statuses[k] + "</b></li>";
    }).join("") : '<li class="wms-muted">Buyurtma yo\'q</li>';
    var top = d.cities.length ? d.cities[0].revenue || 1 : 1;
    root.querySelector("[data-cities]").innerHTML = d.cities.length ? d.cities.map(function (c) {
      return '<li><span class="name">' + esc(c.city) + '</span><span class="bar"><span style="width:' + Math.round((c.revenue / top) * 100) + '%"></span></span><b>' + compact(c.revenue) + "</b></li>";
    }).join("") : '<li style="color:var(--nz-text-muted)">Yetkazilgan buyurtma yo\'q</li>';

    box.hidden = s.orders > 0;
    if (!s.orders) { box.setAttribute("data-state", "empty"); box.innerHTML = '<i class="fas fa-globe"></i> Bu davrda onlayn buyurtma yo\'q'; }
  }

  function tooltip(ctx) {
    var m = ctx.tooltip;
    if (!m || m.opacity === 0 || !m.dataPoints || !m.dataPoints.length) { tip.hidden = true; return; }
    var i = m.dataPoints[0].dataIndex, s = state.data.series;
    var row = function (color, label, value, strong) { return '<div class="nzsc-tip-row"><i class="nzsc-dot" style="background:' + color + '"></i><span class="nzsc-tip-name">' + label + "</span><b" + (strong ? ' style="font-size:.85rem"' : "") + ">" + value + "</b></div>"; };
    tip.innerHTML = '<div class="nzsc-tip-title">' + esc(state.data.labels[i]) + '</div><div class="nzsc-tip-rows">' +
      row("#10b981", "Daromad (yetkazilgan)", money(s.earned[i]) + " so'm", true) + row("#6366f1", "Jarayonda", money(s.pipeline[i]) + " so'm") +
      (s.lost[i] ? row("#ef4444", "Yo'qotilgan", money(s.lost[i]) + " so'm") : "") + "</div>" +
      '<div class="nzsc-tip-total"><span>Buyurtmalar</span><b>' + s.orders[i] + " ta</b></div>";
    tip.hidden = false;
    var bx = canvas.parentNode.getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight;
    var x = m.caretX + 16; if (x + w > bx.width - 4) x = m.caretX - w - 16;
    x = Math.max(4, Math.min(x, bx.width - w - 4));
    tip.style.transform = "translate(" + Math.round(x) + "px," + Math.round(Math.max(4, Math.min(m.caretY - h / 2, bx.height - h - 4))) + "px)";
  }

  root.querySelector(".nzsc-ranges").addEventListener("click", function (e) {
    var b = e.target.closest("button[data-range]");
    if (!b) return;
    state.range = b.getAttribute("data-range");
    root.querySelectorAll(".nzsc-ranges button").forEach(function (x) { x.classList.toggle("on", x === b); x.setAttribute("aria-pressed", String(x === b)); });
    load();
  });
  box.addEventListener("click", function (e) { if (e.target.closest("[data-retry]")) load(); });
  canvas.addEventListener("mouseleave", function () { tip.hidden = true; });
  document.addEventListener("nutrizone:theme-changed", function () { if (state.data) render(); });
  load();
})();
