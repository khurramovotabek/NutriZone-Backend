/* NutriZone Admin -- dashboard "All sections" filter: narrows the section cards to matching apps/models as you type. */
(function () {
  "use strict";
  function init() {
    var input = document.querySelector("[data-nzh-filter]");
    if (!input) return;
    var apps = Array.prototype.slice.call(document.querySelectorAll("[data-nzh-app]"));
    var empty = document.querySelector("[data-nzh-empty]");
    function apply() {
      var q = input.value.trim().toLowerCase();
      var shown = 0;
      apps.forEach(function (app) {
        var head = (app.querySelector("h4").textContent || "").toLowerCase();
        var appHit = !q || head.indexOf(q) !== -1;
        var rows = app.querySelectorAll("[data-nzh-model]");
        var hits = 0;
        Array.prototype.forEach.call(rows, function (row) {
          var hit = appHit || (row.textContent || "").toLowerCase().indexOf(q) !== -1;
          row.classList.toggle("nzh-hidden", !hit);
          if (hit) hits++;
        });
        var visible = appHit || hits > 0;
        app.classList.toggle("nzh-hidden", !visible);
        if (visible) shown++;
      });
      if (empty) empty.hidden = shown > 0;
    }
    input.addEventListener("input", apply);
    input.addEventListener("keydown", function (e) { if (e.key === "Escape") { input.value = ""; apply(); } });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
