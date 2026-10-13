/*
 * NutriZone Dashboard -- "Daily sales by store".
 *
 * One smooth line per branch in the branch's own lifelong colour (Store.color, set when the
 * store is created), real data from /django-admin/pos/salemodel/by-store.json. Range chips,
 * a premium tooltip (every store for the hovered day, sorted, with proportional bars and the
 * day's total), an interactive legend (toggle / search / show all, remembered per browser),
 * summary cards and a small chart for every branch. Loading, empty and error states included.
 */
(function () {
  "use strict";

  var root = document.getElementById("nz-store-sales");
  if (!root || typeof window.Chart === "undefined") return;

  var L = {};
  try { L = JSON.parse(document.getElementById("nzsc-labels").textContent) || {}; } catch (e) { L = {}; }
  var HIDDEN_KEY = "nzsc_hidden_stores";
  var state = { range: "7d", data: null, hidden: loadHidden(), chart: null, sparks: [], query: "", ctrl: null };

  var canvas = root.querySelector("#nzsc-canvas");
  var tip = root.querySelector(".nzsc-tooltip");
  var stateBox = root.querySelector(".nzsc-state");
  var legend = root.querySelector(".nzsc-legend");
  var grid = root.querySelector(".nzsc-grid");
  var search = root.querySelector(".nzsc-search");
  var fromInput = root.querySelector("[data-from]");
  var toInput = root.querySelector("[data-to]");

  // ---------------------------------------------------------------- helpers

  function loadHidden() {
    try { return new Set(JSON.parse(localStorage.getItem(HIDDEN_KEY) || "[]")); } catch (e) { return new Set(); }
  }
  function saveHidden() {
    try { localStorage.setItem(HIDDEN_KEY, JSON.stringify(Array.from(state.hidden))); } catch (e) { /* storage blocked */ }
  }
  function money(n) {
    return Math.round(n || 0).toLocaleString("ru-RU").replace(/ /g, " ");
  }
  function compact(n) {
    var a = Math.abs(n);
    if (a >= 1e9) return (n / 1e9).toFixed(a >= 1e10 ? 0 : 1).replace(/\.0$/, "") + " mlrd";
    if (a >= 1e6) return (n / 1e6).toFixed(a >= 1e7 ? 0 : 1).replace(/\.0$/, "") + " mln";
    if (a >= 1e3) return Math.round(n / 1e3) + " ming";
    return String(Math.round(n));
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; });
  }
  function isDark() {
    var t = document.documentElement.getAttribute("data-nz-theme");
    if (t) return t === "dark";
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  }
  function palette() {
    var dark = isDark();
    return {
      grid: dark ? "rgba(148,163,184,0.12)" : "rgba(15,23,42,0.07)",
      text: dark ? "#94a3b8" : "#64748b",
      surface: dark ? "#0f172a" : "#ffffff",
    };
  }
  function alpha(hex, a) {
    var h = (hex || "#94a3b8").replace("#", "");
    var r = parseInt(h.substr(0, 2), 16), g = parseInt(h.substr(2, 2), 16), b = parseInt(h.substr(4, 2), 16);
    return "rgba(" + r + "," + g + "," + b + "," + a + ")";
  }
  function dayLabel(iso) {
    // "2026-09-21" -> "21 Sen" (the axis); hours stay "09:00"
    if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) return iso;
    var m = parseInt(iso.slice(5, 7), 10) - 1;
    var name = (L.months && L.months[m]) || "";
    return parseInt(iso.slice(8, 10), 10) + " " + name.charAt(0).toUpperCase() + name.slice(1, 3);
  }
  function fmtDate(iso) {
    return iso ? iso.slice(8, 10) + "." + iso.slice(5, 7) + "." + iso.slice(0, 4) : "";
  }
  function visibleStores() {
    return (state.data ? state.data.stores : []).filter(function (s) { return !state.hidden.has(s.id); });
  }
  function showState(kind, text) {
    if (!kind) { stateBox.hidden = true; return; }
    stateBox.hidden = false;
    stateBox.setAttribute("data-state", kind);
    if (kind === "loading") stateBox.innerHTML = '<i class="fas fa-circle-notch fa-spin" aria-hidden="true"></i> ' + esc(text || "");
    else if (kind === "error") stateBox.innerHTML = '<i class="fas fa-triangle-exclamation" aria-hidden="true"></i> ' + esc(L.error) + ' <button type="button" class="nzsc-link" data-retry>' + esc(L.retry) + "</button>";
    else stateBox.innerHTML = '<i class="fas fa-chart-line" aria-hidden="true"></i> ' + esc(L.empty);
  }

  // ---------------------------------------------------------------- data

  function load() {
    if (state.ctrl) state.ctrl.abort();
    state.ctrl = typeof AbortController !== "undefined" ? new AbortController() : null;
    var params = new URLSearchParams({ range: state.range });
    if (state.range === "custom") {
      params.set("from", fromInput.value);
      params.set("to", toInput.value);
    }
    root.setAttribute("aria-busy", "true");
    if (!state.data) showState("loading", stateBox.textContent.trim());
    else stateBox.hidden = true;
    root.classList.add("is-loading");
    fetch(root.getAttribute("data-endpoint") + "?" + params.toString(), { credentials: "same-origin", signal: state.ctrl ? state.ctrl.signal : undefined, headers: { Accept: "application/json" } })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (data) {
        state.data = data;
        if (state.range !== "custom") { fromInput.value = data.from; toInput.value = data.to; }
        render();
      })
      .catch(function (err) {
        if (err && err.name === "AbortError") return;
        showState("error");
      })
      .then(function () {
        root.classList.remove("is-loading");
        root.removeAttribute("aria-busy");
      });
  }

  // ---------------------------------------------------------------- rendering

  function render() {
    var d = state.data;
    if (!d) return;
    var s = d.summary;
    root.querySelector("[data-nzsc-period]").textContent = d.from === d.to ? fmtDate(d.from) : fmtDate(d.from) + " — " + fmtDate(d.to);
    setKpi("total", money(s.total) + " " + L.som);
    setKpi("sales", s.sales + " " + L.sales);
    setKpi("stores", s.stores_with_sales + " / " + s.stores);
    var top = root.querySelector('[data-kpi="top"]');
    top.innerHTML = s.top ? '<i class="nzsc-dot" style="background:' + esc(s.top.color) + '"></i>' + esc(s.top.name) : "—";
    setKpi("top-sum", s.top ? money(s.top.total) + " " + L.som : "");
    var ch = root.querySelector('[data-kpi="change"]');
    if (s.change_pct === null || s.change_pct === undefined) {
      ch.textContent = "—";
      ch.className = "";
      setKpi("prev", L.noPrev);
    } else {
      ch.textContent = (s.change_pct > 0 ? "▲ +" : s.change_pct < 0 ? "▼ " : "") + s.change_pct + "%";
      ch.className = s.change_pct > 0 ? "up" : s.change_pct < 0 ? "down" : "";
      setKpi("prev", L.prev + ": " + money(s.previous_total) + " " + L.som);
    }

    renderChart();
    renderLegend();
    renderGrid();
    showState(s.total > 0 ? null : "empty");
  }

  function setKpi(name, text) {
    var el = root.querySelector('[data-kpi="' + name + '"]');
    if (el) el.textContent = text;
  }

  function datasets() {
    var dense = state.data.labels.length > 40;
    var p = palette();
    return state.data.stores.map(function (st) {
      return {
        label: st.name,
        storeId: st.id,
        data: st.series,
        borderColor: st.color,
        backgroundColor: st.color,
        pointBackgroundColor: st.color,
        pointBorderColor: p.surface,
        pointBorderWidth: 1.5,
        pointRadius: dense ? 0 : 3,
        pointHoverRadius: 6,
        pointHoverBorderWidth: 2,
        borderWidth: 2.5,
        tension: 0.35,
        cubicInterpolationMode: "monotone",
        fill: false,
        hidden: state.hidden.has(st.id),
      };
    });
  }

  function renderChart() {
    var p = palette();
    var labels = state.data.labels;
    if (state.chart) {
      state.chart.data.labels = labels;
      state.chart.data.datasets = datasets();
      state.chart.update();
      return;
    }
    state.chart = new window.Chart(canvas.getContext("2d"), {
      type: "line",
      data: { labels: labels, datasets: datasets() },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 280 },
        interaction: { mode: "index", intersect: false },
        plugins: { legend: { display: false }, tooltip: { enabled: false, external: renderTooltip } },
        scales: {
          x: {
            grid: { display: false },
            border: { display: false },
            ticks: {
              color: p.text, autoSkip: true, maxRotation: 0,
              maxTicksLimit: window.innerWidth < 640 ? 5 : 12,
              callback: function (value) { return dayLabel(this.getLabelForValue(value)); },
            },
          },
          y: {
            beginAtZero: true,
            grid: { color: p.grid, drawTicks: false },
            border: { display: false },
            ticks: { color: p.text, padding: 8, maxTicksLimit: 6, callback: function (v) { return compact(v); } },
          },
        },
      },
    });
  }

  function renderTooltip(ctx) {
    var model = ctx.tooltip;
    if (!model || model.opacity === 0 || !model.dataPoints || !model.dataPoints.length) {
      tip.hidden = true;
      return;
    }
    var i = model.dataPoints[0].dataIndex;
    var d = state.data;
    var rows = visibleStores().map(function (st) { return { name: st.name, color: st.color, value: st.series[i] || 0 }; })
      .sort(function (a, b) { return b.value - a.value; });
    var max = rows.length ? Math.max(rows[0].value, 1) : 1;
    var total = rows.reduce(function (n, r) { return n + r.value; }, 0);
    var title = d.granularity === "hour" ? d.from + " · " + d.labels[i] : d.labels[i];
    tip.innerHTML =
      '<div class="nzsc-tip-title">' + esc(title) + "</div>" +
      '<div class="nzsc-tip-rows">' + rows.map(function (r) {
        return '<div class="nzsc-tip-row' + (r.value ? "" : " is-zero") + '"><i class="nzsc-dot" style="background:' + esc(r.color) + '"></i>' +
          '<span class="nzsc-tip-name">' + esc(r.name) + '</span><b>' + money(r.value) + " " + esc(L.som) + "</b>" +
          '<span class="nzsc-tip-bar"><span style="width:' + Math.round((r.value / max) * 100) + "%;background:" + esc(r.color) + '"></span></span></div>';
      }).join("") + "</div>" +
      '<div class="nzsc-tip-total"><span>' + esc(L.total) + "</span><b>" + money(total) + " " + esc(L.som) + "</b></div>";
    tip.hidden = false;

    // follow the hovered day; flip to the other side near the edges; never leave the chart box
    var box = canvas.parentNode.getBoundingClientRect();
    var w = tip.offsetWidth, h = tip.offsetHeight;
    var x = model.caretX + 16;
    if (x + w > box.width - 4) x = model.caretX - w - 16;
    x = Math.max(4, Math.min(x, box.width - w - 4));
    var y = Math.max(4, Math.min(model.caretY - h / 2, box.height - h - 4));
    tip.style.transform = "translate(" + Math.round(x) + "px," + Math.round(y) + "px)";
  }

  function renderLegend() {
    var stores = state.data.stores;
    search.hidden = stores.length <= 8;
    var q = state.query.trim().toLowerCase();
    var shown = stores.filter(function (s) { return !q || s.name.toLowerCase().indexOf(q) !== -1; });
    legend.innerHTML = shown.map(function (s) {
      var off = state.hidden.has(s.id);
      return '<button type="button" class="nzsc-chip' + (off ? " off" : "") + '" aria-pressed="' + (!off) + '" data-store="' + esc(s.id) + '" style="--c:' + esc(s.color) + '">' +
        '<i class="nzsc-dot"></i><span>' + esc(s.name) + '</span><small>' + (s.total ? compact(s.total) : esc(L.noSales)) + "</small></button>";
    }).join("");
    var active = stores.length - stores.filter(function (s) { return state.hidden.has(s.id); }).length;
    root.querySelector("[data-active-count]").textContent = active + " / " + stores.length + " " + L.active;
    root.querySelector("[data-show-all]").hidden = active === stores.length;
  }

  function renderGrid() {
    state.sparks.forEach(function (c) { c.destroy(); });
    state.sparks = [];
    var d = state.data;
    var salesUrl = root.getAttribute("data-sales-url");
    var toExclusive = new Date(d.to + "T00:00:00");
    toExclusive.setDate(toExclusive.getDate() + 1);
    var toIso = toExclusive.getFullYear() + "-" + String(toExclusive.getMonth() + 1).padStart(2, "0") + "-" + String(toExclusive.getDate()).padStart(2, "0");
    grid.innerHTML = d.stores.map(function (s, i) {
      var branch = s.id === "central" ? "central" : s.id;
      var href = salesUrl + "?branch=" + encodeURIComponent(branch) + "&completed_at__gte=" + d.from + "&completed_at__lt=" + toIso;
      return '<a class="nzsc-store' + (state.hidden.has(s.id) ? " off" : "") + '" href="' + esc(href) + '" style="--c:' + esc(s.color) + '" title="' + esc(L.open) + '">' +
        '<div class="nzsc-store-top"><span class="nzsc-store-name"><i class="nzsc-dot"></i>' + esc(s.name) + "</span>" +
        '<span class="nzsc-store-share">' + s.share + "%</span></div>" +
        '<strong>' + money(s.total) + " <small>" + esc(L.som) + "</small></strong>" +
        '<span class="nzsc-store-meta">' + s.count + " " + esc(L.sales) + (s.city ? " · " + esc(s.city) : "") + "</span>" +
        '<div class="nzsc-spark"><canvas data-spark="' + i + '" aria-hidden="true"></canvas></div></a>';
    }).join("");
    Array.prototype.forEach.call(grid.querySelectorAll("canvas[data-spark]"), function (el) {
      var s = d.stores[+el.getAttribute("data-spark")];
      state.sparks.push(new window.Chart(el.getContext("2d"), {
        type: "line",
        data: { labels: d.labels, datasets: [{ data: s.series, borderColor: s.color, backgroundColor: alpha(s.color, 0.14), fill: true, borderWidth: 2, pointRadius: 0, tension: 0.35, cubicInterpolationMode: "monotone" }] },
        options: {
          responsive: true, maintainAspectRatio: false, animation: false, events: [],
          plugins: { legend: { display: false }, tooltip: { enabled: false } },
          scales: { x: { display: false }, y: { display: false, beginAtZero: true } },
        },
      }));
    });
  }

  function toggleStore(id) {
    if (state.hidden.has(id)) state.hidden.delete(id);
    else state.hidden.add(id);
    saveHidden();
    if (state.chart) {
      state.chart.data.datasets.forEach(function (ds) { ds.hidden = state.hidden.has(ds.storeId); });
      state.chart.update();
    }
    renderLegend();
    Array.prototype.forEach.call(grid.querySelectorAll(".nzsc-store"), function (el, i) {
      el.classList.toggle("off", state.hidden.has(state.data.stores[i].id));
    });
  }

  // ---------------------------------------------------------------- events

  root.querySelector(".nzsc-ranges").addEventListener("click", function (e) {
    var btn = e.target.closest("button[data-range]");
    if (!btn) return;
    if (btn.getAttribute("data-range") === "custom" && !(fromInput.value && toInput.value)) {
      fromInput.focus();
      return;
    }
    state.range = btn.getAttribute("data-range");
    Array.prototype.forEach.call(root.querySelectorAll(".nzsc-ranges button[data-range]"), function (b) {
      var on = b.getAttribute("data-range") === state.range && state.range !== "custom";
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", String(on));
    });
    root.querySelector(".nzsc-custom").classList.toggle("on", state.range === "custom");
    load();
  });
  legend.addEventListener("click", function (e) {
    var chip = e.target.closest("[data-store]");
    if (chip) toggleStore(chip.getAttribute("data-store"));
  });
  root.querySelector("[data-show-all]").addEventListener("click", function () {
    state.hidden.clear();
    saveHidden();
    render();
  });
  search.addEventListener("input", function () {
    state.query = search.value;
    renderLegend();
  });
  stateBox.addEventListener("click", function (e) {
    if (e.target.closest("[data-retry]")) load();
  });
  canvas.addEventListener("mouseleave", function () { tip.hidden = true; });
  document.addEventListener("nutrizone:theme-changed", function () {
    if (state.chart) { state.chart.destroy(); state.chart = null; }
    if (state.data) render();
  });

  load();
})();
