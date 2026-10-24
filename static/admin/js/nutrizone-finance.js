/* Moliya: the operation form shows only what the chosen kind needs (transfer -> target account; income/expense -> their categories). */
(function () {
  "use strict";

  function init() {
    var kind = document.querySelector("select[name=kind]");
    var cat = document.querySelector("select[name=category]");
    var to = document.querySelector("select[name=to_account]");
    if (!kind || !cat) return;
    var kinds = {};
    try { kinds = JSON.parse(cat.dataset.kinds || "{}"); } catch (e) { kinds = {}; }
    function row(el) { return el && (el.closest(".form-group, .form-row, .fieldBox, .nzc-field, .row") || el.parentElement); }
    function sync() {
      var k = kind.value;
      var isTransfer = k === "transfer";
      if (row(to)) row(to).style.display = isTransfer ? "" : "none";
      if (row(cat)) row(cat).style.display = isTransfer ? "none" : "";
      Array.prototype.forEach.call(cat.options, function (o) {
        if (!o.value) return;
        var ok = !isTransfer && kinds[o.value] === k;
        o.hidden = !ok;
        o.disabled = !ok;
      });
      if (cat.selectedOptions[0] && cat.selectedOptions[0].disabled) cat.value = "";
      if (isTransfer) cat.value = "";
      else if (to) to.value = "";
    }
    kind.addEventListener("change", sync);
    sync();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
