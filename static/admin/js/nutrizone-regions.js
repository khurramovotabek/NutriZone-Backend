/* Dashboard → "Hududlar bo'yicha savdo": tile map of Uzbekistan's regions + detail panel + table (regions_report.py). */
(function () {
  "use strict";
  var root = document.getElementById("nz-regions");
  if (!root) return;
  var L = {};
  try { L = JSON.parse(document.getElementById("nzrg-i18n").textContent || "{}"); } catch (e) { L = {}; }
  var t = function (k, d) { return L[k] || d || k; };
  var state = { range: "30d", metric: "revenue", data: null, selected: null };
  var map = root.querySelector("[data-rg-map]");
  var detail = root.querySelector("[data-rg-detail]");
  var rowsEl = root.querySelector("[data-rg-rows]");
  var stateEl = root.querySelector(".nzsc-state");
  var COLS = 9, ROWS = 3;

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function num(n) { return Math.round(n || 0).toLocaleString("ru-RU").replace(/,/g, " "); }
  function money(n) { return num(n) + " " + t("som"); }
  function compact(n) {
    n = n || 0;
    if (n >= 1e9) return (n / 1e9).toFixed(1).replace(".0", "") + " " + t("mlrd");
    if (n >= 1e6) return (n / 1e6).toFixed(1).replace(".0", "") + " " + t("mln");
    if (n >= 1e3) return Math.round(n / 1e3) + " " + t("ming");
    return num(n);
  }
  function metricText(r, m) {
    if (m === "revenue") return compact(r.revenue);
    if (m === "average") return compact(r.average);
    return num(r[m]);
  }
  function changeHtml(pct) {
    if (pct === null || pct === undefined) return '<span class="nzrg-chg">—</span>';
    var dir = pct > 0 ? "up" : pct < 0 ? "down" : "flat";
    return '<span class="nzrg-chg ' + dir + '">' + (pct > 0 ? "↑ " : pct < 0 ? "↓ " : "") + Math.abs(pct) + "%</span>";
  }

  function setLoading(on) {
    root.classList.toggle("is-loading", on);
    if (on) { stateEl.hidden = false; stateEl.dataset.state = "loading"; stateEl.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i>'; }
  }

  function load() {
    setLoading(true);
    fetch(root.dataset.endpoint + "?range=" + encodeURIComponent(state.range), { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (d) { state.data = d; stateEl.hidden = true; root.classList.remove("is-loading"); render(); })
      .catch(function () {
        root.classList.remove("is-loading");
        stateEl.hidden = false; stateEl.dataset.state = "error";
        stateEl.innerHTML = esc(t("error")) + ' <button type="button" class="nzsc-link">' + esc(t("retry")) + "</button>";
        stateEl.querySelector("button").onclick = load;
      });
  }

  function render() {
    var d = state.data, s = d.summary;
    root.querySelector("[data-rg-period]").textContent = d.title + " · " + d.period;
    var q = function (k) { return root.querySelector('[data-rg="' + k + '"]'); };
    q("revenue").textContent = money(s.revenue);
    q("change").innerHTML = s.change === null ? esc(s.previous_revenue ? "" : t("noPrev")) : changeHtml(s.change) + " " + esc(d.compare);
    q("active").textContent = s.regions_active + " / " + s.regions_total;
    q("orders").textContent = num(s.orders) + " " + t("orders") + " · " + num(s.customers) + " " + t("customers");
    q("top").textContent = s.top || "—";
    q("top-share").textContent = s.top ? s.top_share + "% " + t("share") : t("noSales");
    q("split").textContent = s.revenue ? s.tashkent_share + "% / " + Math.round((100 - s.tashkent_share) * 10) / 10 + "%" : "—";
    q("pipeline").textContent = num(s.pipeline_orders) + " " + t("inPipeline") + " · " + compact(s.pipeline_value) + " " + t("som");

    var m = state.metric;
    var max = Math.max.apply(null, d.regions.map(function (r) { return r[m] || 0; }).concat([0]));
    var tiles = "";
    d.regions.forEach(function (r) {
      if (r.col === null || r.col === undefined) return;
      var v = r[m] || 0, k = max ? v / max : 0;
      tiles += '<button type="button" role="listitem" class="nzrg-tile' + (v ? "" : " is-zero") + (state.selected === r.code ? " is-on" : "") + '" data-code="' + esc(r.code) + '"' +
        ' style="grid-column:' + (r.col + 1) + ";grid-row:" + (r.row + 1) + ";--k:" + k.toFixed(3) + '" title="' + esc(r.name) + '">' +
        "<small>" + esc(r.short) + "</small><b>" + (v ? esc(metricText(r, m)) : "·") + "</b>" + (r.branches.length ? '<i class="fas fa-store" aria-hidden="true"></i>' : "") + "</button>";
    });
    map.style.gridTemplateColumns = "repeat(" + COLS + ", minmax(0, 1fr))";
    map.style.gridTemplateRows = "repeat(" + ROWS + ", auto)";
    map.innerHTML = tiles;

    rowsEl.innerHTML = d.regions.map(function (r) {
      var cls = (state.selected === r.code ? "is-on " : "") + (r.orders ? "" : "is-zero");
      return '<tr data-code="' + esc(r.code) + '" class="' + cls.trim() + '">' +
        '<td><span class="nzrg-name">' + esc(r.name) + "</span></td>" +
        '<td class="num"><b>' + money(r.revenue) + "</b></td>" +
        '<td class="num"><span class="nzrg-share"><i style="width:' + Math.min(100, r.share) + '%"></i></span>' + r.share + "%</td>" +
        '<td class="num">' + compact(r.online_revenue) + '</td><td class="num">' + compact(r.pos_revenue) + "</td>" +
        '<td class="num">' + num(r.orders) + '</td><td class="num">' + num(r.customers) + '</td><td class="num">' + compact(r.average) + "</td>" +
        '<td class="num">' + (r.pipeline_orders ? num(r.pipeline_orders) : "—") + '</td><td class="num">' + (r.loss_rate ? r.loss_rate + "%" : "—") + "</td>" +
        '<td class="num">' + changeHtml(r.change) + "</td>" +
        "<td>" + (r.branches.length ? '<span class="nzrg-badge">' + r.branches.length + "</span>" : "—") + "</td></tr>";
    }).join("");

    if (!state.selected) {
      var lead = d.regions.filter(function (r) { return r.orders; })[0];
      state.selected = lead ? lead.code : null;
      if (state.selected) return render();
    }
    renderDetail();
  }

  function renderDetail() {
    var r = (state.data.regions || []).filter(function (x) { return x.code === state.selected; })[0];
    if (!r) { detail.innerHTML = '<p class="nzrg-pick"><i class="fas fa-hand-pointer"></i> ' + esc(t("pick")) + "</p>"; return; }
    var cities = r.cities.length ? r.cities.map(function (c) {
      var w = r.cities[0].revenue ? Math.max(4, c.revenue / r.cities[0].revenue * 100) : 0;
      return '<li><span>' + esc(c.city) + "</span><b>" + compact(c.revenue) + '</b><small>' + num(c.orders) + " " + t("orders") + '</small><i style="width:' + w + '%"></i></li>';
    }).join("") : '<li class="is-empty">—</li>';
    detail.innerHTML =
      '<div class="nzrg-d-head"><h4>' + esc(r.name) + "</h4>" + changeHtml(r.change) + "</div>" +
      '<div class="nzrg-d-big">' + money(r.revenue) + "<small>" + r.share + "% " + esc(t("share")) + "</small></div>" +
      '<div class="nzrg-d-grid">' +
      "<div><small>" + esc(t("online")) + "</small><b>" + compact(r.online_revenue) + "</b></div>" +
      "<div><small>" + esc(t("pos")) + "</small><b>" + compact(r.pos_revenue) + "</b></div>" +
      "<div><small>" + esc(t("orders")) + "</small><b>" + num(r.orders) + "</b></div>" +
      "<div><small>" + esc(t("customers")) + "</small><b>" + num(r.customers) + "</b></div>" +
      "<div><small>" + esc(t("avg")) + "</small><b>" + compact(r.average) + "</b></div>" +
      "<div><small>" + esc(t("pipeline")) + "</small><b>" + num(r.pipeline_orders) + "</b></div>" +
      "<div><small>" + esc(t("lost")) + "</small><b>" + num(r.lost_orders) + "</b></div>" +
      "<div><small>" + esc(t("delivery")) + "</small><b>" + compact(r.delivery_fees) + "</b></div>" +
      "</div>" +
      "<h5>" + esc(t("cities")) + '</h5><ul class="nzrg-cities">' + cities + "</ul>" +
      "<h5>" + esc(t("branches")) + '</h5><p class="nzrg-branches">' + (r.branches.length ? r.branches.map(function (b) { return "<span>" + esc(b) + "</span>"; }).join("") : esc(t("noBranches"))) + "</p>";
  }

  function pick(code) { state.selected = code; render(); }
  map.addEventListener("click", function (e) { var b = e.target.closest("[data-code]"); if (b) pick(b.dataset.code); });
  rowsEl.addEventListener("click", function (e) { var tr = e.target.closest("tr[data-code]"); if (tr) pick(tr.dataset.code); });
  root.querySelector("[data-rg-metrics]").addEventListener("click", function (e) {
    var b = e.target.closest("button[data-metric]"); if (!b) return;
    root.querySelectorAll("[data-rg-metrics] button").forEach(function (x) { x.classList.toggle("on", x === b); });
    state.metric = b.dataset.metric; if (state.data) render();
  });
  root.querySelector("[data-rg-ranges]").addEventListener("click", function (e) {
    var b = e.target.closest("button[data-range]"); if (!b) return;
    root.querySelectorAll("[data-rg-ranges] button").forEach(function (x) { x.classList.toggle("on", x === b); });
    state.range = b.dataset.range; state.selected = null; load();
  });
  var initial = root.dataset.range;
  if (initial && root.querySelector('[data-rg-ranges] button[data-range="' + initial + '"]')) {
    state.range = initial;
    root.querySelectorAll("[data-rg-ranges] button").forEach(function (x) { x.classList.toggle("on", x.dataset.range === initial); });
  }
  load();
})();
