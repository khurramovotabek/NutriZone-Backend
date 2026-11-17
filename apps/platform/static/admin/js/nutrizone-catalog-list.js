/* Catalog lists (analytics_change_list.html): the bulk-action bar shows only while rows are selected; "/" focuses search;
 * every cell carries its column title (data-label) so phones can show each row as a card ("Narx: 890 000"). */
(function () {
  "use strict";
  function sync() {
    var n = document.querySelectorAll("#result_list tbody input.action-select:checked").length;
    document.body.classList.toggle("nzc-has-selection", n > 0);
  }
  function label() {
    var table = document.getElementById("result_list"); if (!table) return;
    var heads = Array.prototype.map.call(table.querySelectorAll("thead th"), function (th) { return (th.innerText || "").replace(/\s+/g, " ").trim(); });
    table.querySelectorAll("tbody tr").forEach(function (tr) {
      if (tr.dataset.nzcLabelled) return;
      tr.dataset.nzcLabelled = "1";
      var lead = false;
      Array.prototype.forEach.call(tr.children, function (cell, i) {
        if (cell.classList.contains("action-checkbox")) { cell.classList.add("nzc-cell-check"); return; }
        var h = heads[i] || "";
        if (!h) { cell.classList.add("nzc-cell-media"); return; } // thumbnail / logo columns have no title
        if (!lead) { lead = true; cell.classList.add("nzc-cell-lead"); return; }
        cell.setAttribute("data-label", h);
      });
    });
  }
  document.addEventListener("change", function (e) { if (e.target.matches("#result_list input.action-select, #result_list #action-toggle")) setTimeout(sync, 0); });
  document.addEventListener("click", function (e) { if (e.target.closest("#result_list") || e.target.closest(".actions")) setTimeout(sync, 0); });
  document.addEventListener("nz:rows-added", function () { label(); sync(); }); // "Yana ko'rsatish"
  document.addEventListener("keydown", function (e) {
    if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey) return;
    var t = e.target; if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return;
    var q = document.getElementById("searchbar"); if (q) { e.preventDefault(); q.focus(); q.select(); }
  });
  function init() { label(); sync(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
