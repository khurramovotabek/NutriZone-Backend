/*
 * NutriZone Admin -- order desk pages (templates/admin/ordering/*):
 * dialogs, copy / print, ship-from stock warning, list filter auto-submit, the create page's quantity
 * steppers with a live value, and double-submit protection on every action form.
 */
(function () {
  "use strict";

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function fmt(n) { return Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, " "); }

  var PALETTE = ["#6366f1", "#0ea5e9", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#14b8a6", "#ec4899", "#f97316", "#3b82f6"];
  function paintAvatars() {
    $$(".nzp-avatar[data-seed]").forEach(function (el) {
      var s = el.getAttribute("data-seed") || el.textContent, h = 0;
      for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
      el.style.setProperty("--av", PALETTE[h % PALETTE.length]);
    });
  }

  function toast(text) {
    var el = $("[data-nzp-toast]");
    if (!el) return;
    el.textContent = text; el.hidden = false;
    clearTimeout(toast.t); toast.t = setTimeout(function () { el.hidden = true; }, 1800);
  }

  function initDialogs() {
    $$("[data-nzd-open]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var dlg = document.getElementById(btn.getAttribute("data-nzd-open"));
        if (dlg && dlg.showModal) { dlg.showModal(); var f = dlg.querySelector("textarea, input:not([type=hidden]):not([type=radio])"); if (f) f.focus(); }
      });
    });
    $$("dialog.nzd-dialog").forEach(function (dlg) {
      $$("[data-nzd-close]", dlg).forEach(function (b) { b.addEventListener("click", function () { dlg.close(); }); });
      dlg.addEventListener("click", function (e) { if (e.target === dlg) dlg.close(); }); // click on the backdrop
    });
  }

  function initCopy() {
    $$("[data-nzd-copy]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var text = btn.getAttribute("data-nzd-copy");
        var ok = function () { toast((window.NZ_I18N && NZ_I18N.copied) || "✓"); var i = btn.querySelector("i"); if (i) { var c = i.className; i.className = "fas fa-check"; setTimeout(function () { i.className = c; }, 1200); } };
        if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(ok);
        else { var ta = document.createElement("textarea"); ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0"; document.body.appendChild(ta); ta.select(); try { document.execCommand("copy"); ok(); } catch (e) { /* ignore */ } ta.remove(); }
      });
    });
    $$("[data-nzd-print]").forEach(function (b) { b.addEventListener("click", function () { window.print(); }); });
  }

  // One click = one request: a status change must never be posted twice.
  function initSubmitGuard() {
    $$(".nzd form[method=post]").forEach(function (form) {
      form.addEventListener("submit", function () {
        if (form.dataset.sent) return;
        form.dataset.sent = "1";
        setTimeout(function () { $$("button[type=submit], button:not([type])", form).forEach(function (b) { b.disabled = true; b.classList.add("is-busy"); }); }, 0);
      });
    });
  }

  function initShip() {
    var form = $("[data-nzd-ship]");
    if (!form) return;
    var warn = $("[data-nzd-ship-warn]", form);
    function sync() {
      var chosen = $("input[name=store_id]:checked", form);
      if (warn) warn.hidden = !chosen || chosen.getAttribute("data-ok") === "1";
    }
    $$("input[name=store_id]", form).forEach(function (r) { r.addEventListener("change", sync); });
    sync();
  }

  function initFilters() {
    $$("[data-nzd-autosubmit]").forEach(function (el) { el.addEventListener("change", function () { el.form.submit(); }); });
  }

  function initMoney() {
    $$("[data-nzd-money]").forEach(function (input) {
      input.addEventListener("input", function () { input.value = input.value.replace(/[^\d.,\s]/g, ""); });
    });
    $$("[data-nzd-fill]").forEach(function (b) {
      b.addEventListener("click", function () { var input = b.parentNode.querySelector("input"); if (input) { input.value = b.getAttribute("data-nzd-fill"); input.focus(); } });
    });
  }

  function initCreate() {
    var form = $("[data-nzd-create]");
    if (!form) return;
    var list = $("[data-nzd-lines]", form);
    var valueEl = $("[data-nzd-value]", form);
    var submit = $("[data-nzd-submit]", form);
    var none = $("[data-nzd-none]", form);
    var scopeAll = $("input[data-nzd-scope][value=all]", form);

    function total() {
      var sum = 0, units = 0;
      $$("li[data-unit]", list).forEach(function (li) {
        var input = $("input[type=number]", li);
        var q = input && !input.disabled ? parseInt(input.value, 10) || 0 : 0;
        if (scopeAll && scopeAll.checked && input && !input.disabled) q = parseInt(input.max, 10) || 0;
        sum += q * parseFloat(li.getAttribute("data-unit") || "0");
        units += q;
      });
      if (valueEl) valueEl.textContent = fmt(sum);
      if (submit) submit.disabled = units === 0;
      if (none) none.hidden = units !== 0;
    }
    $$("li[data-unit]", list).forEach(function (li) {
      var input = $("input[type=number]", li);
      if (!input) return;
      $$("button[data-step]", li).forEach(function (b) {
        b.addEventListener("click", function () {
          var v = (parseInt(input.value, 10) || 0) + parseInt(b.getAttribute("data-step"), 10);
          input.value = Math.max(0, Math.min(v, parseInt(input.max, 10) || 0));
          total();
        });
      });
      input.addEventListener("input", function () {
        var v = parseInt(input.value, 10);
        if (isNaN(v) || v < 0) v = 0;
        input.value = Math.min(v, parseInt(input.max, 10) || 0);
        total();
      });
    });
    function syncScope() {
      if (!scopeAll) return;
      list.classList.toggle("is-locked", scopeAll.checked);
      total();
    }
    $$("input[data-nzd-scope]", form).forEach(function (r) { r.addEventListener("change", syncScope); });
    var completeNow = $("[data-nzd-complete-now]", form), refundRow = $("[data-nzd-refund-row]", form);
    if (completeNow && refundRow) {
      var syncRefund = function () { refundRow.hidden = !completeNow.checked; };
      completeNow.addEventListener("change", syncRefund); syncRefund();
    }
    syncScope();
    total();
  }

  function init() {
    if (!$(".nzd")) return;
    paintAvatars(); initDialogs(); initCopy(); initSubmitGuard(); initShip(); initFilters(); initMoney(); initCreate();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
