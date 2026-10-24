/* Narxlarni qayta baholash: builder helpers (searchable selects, check-all, live % and margin on edited prices) and confirms. */
(function () {
  "use strict";

  var HINTS = {
    percent: ["Foiz (+ oshirish, − kamaytirish)", "10 → hamma narx 10% qimmat; −15 → 15% arzon."],
    amount: ["Summa, so'm (+ / −)", "20000 → har bir narxga 20 000 so'm qo'shiladi; −10000 → kamayadi."],
    markup: ["Ustama, %", "30 → yangi narx = tannarx × 1,3. Tannarxi kiritilmagan mahsulotlar o'tkazib yuboriladi."],
    fixed: ["Yangi narx, so'm", "Tanlangan hamma variantga bir xil narx qo'yiladi."],
  };

  function t(text) { return window.nzTranslate ? window.nzTranslate(text) : text; }

  function fmt(n) { return Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, " "); }

  function init() {
    document.querySelectorAll("[data-filter-for]").forEach(function (input) {
      var select = document.getElementById(input.dataset.filterFor);
      if (!select) return;
      input.addEventListener("input", function () {
        var q = input.value.trim().toLowerCase();
        Array.prototype.forEach.call(select.options, function (o) { o.hidden = q && o.text.toLowerCase().indexOf(q) === -1 && !o.selected; });
      });
    });
    // multi-selects without Ctrl: a click toggles the option
    document.querySelectorAll(".nzr select[multiple]").forEach(function (sel) {
      sel.addEventListener("mousedown", function (e) {
        if (e.target.tagName !== "OPTION") return;
        e.preventDefault();
        e.target.selected = !e.target.selected;
        sel.focus();
      });
    });

    var modeLabel = document.querySelector("[data-value-label]");
    var hint = document.querySelector("[data-hint]");
    function syncMode() {
      var checked = document.querySelector("input[name=mode]:checked");
      var h = HINTS[checked ? checked.value : "percent"];
      if (modeLabel && h) modeLabel.textContent = t(h[0]);
      if (hint && h) hint.textContent = t(h[1]);
    }
    document.querySelectorAll("input[name=mode]").forEach(function (r) { r.addEventListener("change", syncMode); });
    syncMode();

    var all = document.querySelector("[data-check-all]");
    if (all) all.addEventListener("change", function () {
      document.querySelectorAll(".nzr-table tbody input[type=checkbox]").forEach(function (c) { c.checked = all.checked; });
    });

    document.querySelectorAll(".nzr-new").forEach(function (input) {
      input.addEventListener("input", function () {
        var tr = input.closest("tr");
        var price = parseFloat(tr.dataset.price), cost = parseFloat(tr.dataset.cost);
        var v = parseFloat(input.value.replace(/\s/g, ""));
        var d = tr.querySelector("[data-delta]"), m = tr.querySelector("[data-margin]");
        if (!isNaN(v) && price) {
          var pct = (v - price) / price * 100;
          d.textContent = (pct > 0 ? "+" : "") + pct.toFixed(1) + "%";
          d.className = "r nzr-delta " + (pct > 0 ? "is-up" : pct < 0 ? "is-down" : "");
        }
        if (!isNaN(v) && cost && v) m.textContent = ((v - cost) / v * 100).toFixed(1) + "%";
        tr.classList.toggle("is-below", !isNaN(v) && !isNaN(cost) && cost > 0 && v < cost);
        var box = tr.querySelector("input[type=checkbox]");
        if (box && !isNaN(v) && v > 0) box.checked = true;
      });
      input.addEventListener("blur", function () {
        var v = parseFloat(input.value.replace(/\s/g, ""));
        if (!isNaN(v)) input.value = fmt(v);
      });
    });

    var save = document.querySelector("[data-nzr-confirm]");
    if (save) save.addEventListener("click", function (e) {
      var n = document.querySelectorAll(".nzr-table tbody input[type=checkbox]:checked").length;
      var when = document.querySelector("input[name=when]:checked");
      if (when && when.value === "now" && !window.confirm(t(n + " ta narx hozir o'zgaradi. Davom etasizmi?"))) e.preventDefault();
    });
    document.querySelectorAll("[data-nzr-ask]").forEach(function (b) {
      b.addEventListener("click", function (e) { if (!window.confirm(t(b.dataset.nzrAsk))) e.preventDefault(); });
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
