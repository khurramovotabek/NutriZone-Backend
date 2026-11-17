/* Catalog lists (analytics_change_list.html): the bulk-action bar shows only while rows are selected; "/" focuses search. */
(function () {
  "use strict";
  function sync() {
    var n = document.querySelectorAll("#result_list tbody input.action-select:checked").length;
    document.body.classList.toggle("nzc-has-selection", n > 0);
  }
  document.addEventListener("change", function (e) { if (e.target.matches("#result_list input.action-select, #result_list #action-toggle")) setTimeout(sync, 0); });
  document.addEventListener("click", function (e) { if (e.target.closest("#result_list") || e.target.closest(".actions")) setTimeout(sync, 0); });
  document.addEventListener("keydown", function (e) {
    if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey) return;
    var t = e.target; if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return;
    var q = document.getElementById("searchbar"); if (q) { e.preventDefault(); q.focus(); q.select(); }
  });
  document.addEventListener("DOMContentLoaded", sync);
  sync();
})();
