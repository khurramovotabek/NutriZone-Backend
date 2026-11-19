/* Permission matrix: search, per-section "view only / all / none", row toggle, live counters. */
(function () {
  "use strict";
  function ready(fn) { if (document.readyState !== "loading") fn(); else document.addEventListener("DOMContentLoaded", fn); }
  ready(function () {
    document.querySelectorAll(".nzpm").forEach(function (root) {
      var total = root.querySelector("[data-pm-total]");
      function boxes(el) { return Array.prototype.slice.call(el.querySelectorAll('input[type="checkbox"]')); }
      function count() {
        root.querySelectorAll(".nzpm-app").forEach(function (app) {
          var all = boxes(app), on = all.filter(function (b) { return b.checked; }).length, c = app.querySelector(".nzpm-count");
          c.textContent = on + " / " + all.length; c.classList.toggle("is-on", on > 0);
        });
        total.textContent = boxes(root).filter(function (b) { return b.checked; }).length;
      }
      root.addEventListener("change", count);
      root.addEventListener("click", function (e) {
        var tool = e.target.closest("[data-pm]");
        if (tool) {
          e.preventDefault();
          var app = tool.closest(".nzpm-app"), mode = tool.getAttribute("data-pm");
          app.open = true;
          app.querySelectorAll("tbody tr").forEach(function (tr) {
            if (tr.classList.contains("is-hidden")) return;
            tr.querySelectorAll("td").forEach(function (td, i) {
              boxes(td).forEach(function (b) { b.checked = mode === "all" ? true : mode === "none" ? false : i === 0; });
            });
          });
          count(); return;
        }
        var row = e.target.closest(".nzpm-row");
        if (row) {
          var bs = boxes(row.closest("tr")), any = bs.some(function (b) { return !b.checked; });
          bs.forEach(function (b) { b.checked = any; }); count(); return;
        }
        if (e.target.closest("[data-pm-expand]")) {
          var apps = root.querySelectorAll(".nzpm-app"), open = Array.prototype.some.call(apps, function (a) { return !a.open; });
          apps.forEach(function (a) { a.open = open; });
          e.target.closest("[data-pm-expand]").textContent = open ? "Hammasini yopish" : "Hammasini ochish";
        }
      });
      var input = root.querySelector(".nzpm-search input");
      input.addEventListener("keydown", function (e) { if (e.key === "Enter") e.preventDefault(); });
      input.addEventListener("input", function () {
        var q = input.value.trim().toLowerCase();
        root.querySelectorAll(".nzpm-app").forEach(function (app) {
          var hits = 0;
          app.querySelectorAll("tbody tr").forEach(function (tr) {
            var ok = !q || tr.getAttribute("data-search").indexOf(q) !== -1;
            tr.classList.toggle("is-hidden", !ok); if (ok) hits++;
          });
          app.classList.toggle("is-hidden", !hits);
          if (q) app.open = hits > 0;
        });
      });
    });
  });
})();
