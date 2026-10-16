/*
 * Dashboard-wide form polish (every add / change page).
 *
 * Wide tabular inlines (variants, prices, receipts ...) used to scroll sideways with 20px-wide inputs. Any tabular
 * inline with 6+ editable columns -- or one that overflows its card -- turns into a stack of cards: one card per row,
 * fields in a responsive grid, each field captioned with its column header. Rows added later with "Add another"
 * get the same captions. Pure progressive enhancement: the table markup and form posting are untouched.
 */
(function () {
  "use strict";

  var MIN_COLUMNS = 6;

  function columnLabels(table) {
    var labels = {};
    table.querySelectorAll("thead th").forEach(function (th) {
      var m = (th.className || "").match(/(?:^|\s)column-([\w-]+)/);
      if (!m) return;
      var text = "";
      th.childNodes.forEach(function (n) { if (n.nodeType === 3) text += n.textContent; });
      labels[m[1]] = { text: text.replace(/\s+/g, " ").trim(), required: th.classList.contains("required"), help: (th.querySelector(".help-tooltip") || {}).title || "" };
    });
    return labels;
  }

  function labelRow(row, labels) {
    row.querySelectorAll("td").forEach(function (td) {
      var m = (td.className || "").match(/(?:^|\s)field-([\w-]+)/);
      if (!m || !labels[m[1]] || td.hasAttribute("data-label")) return;
      var l = labels[m[1]];
      td.setAttribute("data-label", l.text + (l.required ? " *" : ""));
      if (l.help) td.setAttribute("title", l.help);
    });
  }

  function enhance(group) {
    var table = group.querySelector("table");
    if (!table || group.classList.contains("nzf-cards")) return;
    var labels = columnLabels(table);
    var count = Object.keys(labels).length;
    var overflow = table.scrollWidth > (group.clientWidth || 0) + 8;
    if (count < MIN_COLUMNS && !overflow) return;
    group.classList.add("nzf-cards");
    group.querySelectorAll("tbody tr.form-row").forEach(function (row) { labelRow(row, labels); });
    group._nzfLabels = labels;
  }

  function init(root) {
    (root || document).querySelectorAll('.inline-group[data-inline-type="tabular"]').forEach(enhance);
  }

  document.addEventListener("formset:added", function (e) {
    var row = e.target && e.target.closest ? e.target.closest("tr.form-row") : null;
    var group = row && row.closest(".inline-group.nzf-cards");
    if (group && group._nzfLabels) labelRow(row, group._nzfLabels);
  });
  // jQuery-dispatched variant (Django < 4.1 / some Jazzmin builds)
  if (window.django && window.django.jQuery) {
    window.django.jQuery(document).on("formset:added", function (_e, $row) {
      var row = $row && $row[0];
      var group = row && row.closest(".inline-group.nzf-cards");
      if (group && group._nzfLabels) labelRow(row, group._nzfLabels);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function () { init(); });
  else init();
})();
