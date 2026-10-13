/*
 * NutriZone Dashboard → Loyalty darajalari: the ladder calculator (coins for a typed order amount on every tier) and
 * the editor's live "1 mln xariddan" column. Coins = floor(amount × percent / 100), 1 so'm = 1 coin.
 */
(function () {
  "use strict";

  function money(n) { return Math.floor(Number(n) || 0).toLocaleString("ru-RU").replace(/ /g, " "); }
  function num(v) { return Number(String(v || "").replace(/[^\d.,]/g, "").replace(",", ".")) || 0; }

  var calc = document.querySelector("[data-nzl-calc]");
  function ladder() {
    var amount = calc ? num(calc.value) : 1000000;
    document.querySelectorAll("[data-nzl-pct]").forEach(function (el) { el.textContent = "+" + money(amount * num(el.getAttribute("data-nzl-pct")) / 100) + " coin"; });
  }
  if (calc) {
    calc.addEventListener("input", function () { ladder(); });
    calc.addEventListener("change", function () { calc.value = money(num(calc.value)); });
    ladder();
  }

  function rows() {
    document.querySelectorAll(".nzl-row").forEach(function (row) {
      var pct = row.querySelector('input[name$="-percent"]'), out = row.querySelector("[data-nzl-row-pct]");
      if (pct && out) out.textContent = "+" + money(1000000 * num(pct.value) / 100);
      var on = row.querySelector('input[name$="-is_active"]');
      if (on) row.classList.toggle("is-off", !on.checked);
    });
  }
  document.addEventListener("input", function (e) { if (e.target.closest(".nzl-row")) rows(); });
  document.addEventListener("change", function (e) { if (e.target.closest(".nzl-row")) rows(); });
  rows();
})();
