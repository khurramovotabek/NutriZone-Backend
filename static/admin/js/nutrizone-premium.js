/*
 * NutriZone Dashboard premium admin (Identity, Loyalty, ...). Lists (admin/premium/list.html): a click on a row opens it, select-all and the
 * bulk bar. Forms (admin/premium/form.html): confirm risky panel buttons (block, sign out everywhere, remove a role)
 * and group the role editor's permission checkboxes into searchable module cards.
 */
(function () {
  "use strict";

  function qa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  /* ---------- lists ---------- */
  var list = document.querySelector(".nzi-listform");
  if (list) {
    var bulk = list.querySelector("[data-nzi-bulk]"), all = list.querySelector("[data-nzi-all]");
    var boxes = qa("input.action-select", list);
    var sync = function () {
      var n = boxes.filter(function (b) { return b.checked; }).length;
      boxes.forEach(function (b) { (b.closest(".nzi-tr") || b.closest(".nzi-card")).classList.toggle("is-picked", b.checked); });
      if (bulk) { bulk.hidden = !n; bulk.querySelector("[data-nzi-count]").textContent = n; }
      if (all) { all.checked = n && n === boxes.length; all.indeterminate = n > 0 && n < boxes.length; }
    };
    if (all) all.addEventListener("change", function () { boxes.forEach(function (b) { b.checked = all.checked; }); sync(); });
    list.addEventListener("change", function (e) { if (e.target.classList.contains("action-select")) sync(); });
    list.addEventListener("click", function (e) {
      var row = e.target.closest(".nzi-tr[data-href], .nzi-card[data-href]");
      if (!row || e.target.closest("a, input, button, label, select")) return;
      if (window.getSelection && String(window.getSelection())) return; // selecting text is not a click
      if (e.ctrlKey || e.metaKey) window.open(row.getAttribute("data-href"), "_blank"); else window.location = row.getAttribute("data-href");
    });
    list.addEventListener("submit", function (e) {
      var btn = e.submitter;
      if (btn && /blok|chiqar|olib tashla|yopish/i.test(btn.textContent) && !window.confirm(btn.textContent.trim() + " — tanlangan " + boxes.filter(function (b) { return b.checked; }).length + " ta yozuv uchun bajarilsinmi?")) e.preventDefault();
    });
    sync();
  }

  /* ---------- copy buttons ([data-copy]) ---------- */
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-copy]");
    if (!btn) return;
    e.preventDefault(); e.stopPropagation();
    var done = function () { btn.classList.add("is-copied"); setTimeout(function () { btn.classList.remove("is-copied"); }, 1400); };
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(btn.getAttribute("data-copy")).then(done);
    else { var t = document.createElement("textarea"); t.value = btn.getAttribute("data-copy"); document.body.appendChild(t); t.select(); try { document.execCommand("copy"); done(); } catch (x) { /* no clipboard */ } t.remove(); }
  }, true);

  /* ---------- forms: confirm risky panel actions ---------- */
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("button[data-nzi-confirm]");
    if (!btn || !btn.getAttribute("data-nzi-confirm")) return;
    if (!window.confirm(btn.getAttribute("data-nzi-confirm"))) e.preventDefault();
  });

  /* ---------- role editor: permissions grouped by module ---------- */
  var inputs = qa('.card.nzi-perms input[type=checkbox][name="permissions"]');
  if (inputs.length) {
    var host = inputs[0].closest(".form-group") || inputs[0].closest(".card-body");
    var wrap = document.createElement("div");
    var groups = {}, order = [];
    inputs.forEach(function (input) {
      var mod = input.getAttribute("data-module") || "Boshqa";
      if (!groups[mod]) { groups[mod] = { icon: input.getAttribute("data-icon") || "fa-key", color: input.getAttribute("data-color") || "#6366f1", items: [] }; order.push(mod); }
      var lab = input.closest("label");
      groups[mod].items.push({ input: input, text: input.getAttribute("data-label") || (lab ? lab.textContent : input.value).trim(), code: input.getAttribute("data-code") || input.value });
    });
    var head = document.createElement("div");
    head.className = "nzi-pm-head";
    head.innerHTML = '<input type="search" placeholder="Ruxsatni qidirish…" aria-label="Ruxsatni qidirish"><b data-nzi-total></b>';
    var grid = document.createElement("div");
    grid.className = "nzi-pm-grid";
    order.forEach(function (mod) {
      var g = groups[mod], card = document.createElement("section");
      card.className = "nzi-pm"; card.style.setProperty("--t", g.color);
      card.innerHTML = '<header><i class="fas ' + g.icon + '" aria-hidden="true"></i><b></b><small data-n></small><label><input type="checkbox" data-all> hammasi</label></header><ul></ul>';
      card.querySelector("b").textContent = mod;
      var ul = card.querySelector("ul");
      g.items.forEach(function (it) {
        var li = document.createElement("li"), lab = document.createElement("label"), span = document.createElement("span"), code = document.createElement("code");
        span.textContent = it.text; code.textContent = it.code; span.appendChild(code);
        lab.appendChild(it.input); lab.appendChild(span); li.appendChild(lab); ul.appendChild(li);
        li.setAttribute("data-q", (it.text + " " + it.code).toLowerCase());
      });
      g.card = card;
      grid.appendChild(card);
    });
    var count = function () {
      var on = 0;
      order.forEach(function (mod) {
        var g = groups[mod], n = g.items.filter(function (it) { return it.input.checked; }).length;
        on += n;
        g.card.querySelector("[data-n]").textContent = n + " / " + g.items.length;
        var a = g.card.querySelector("[data-all]"); a.checked = n === g.items.length; a.indeterminate = n > 0 && n < g.items.length;
      });
      head.querySelector("[data-nzi-total]").textContent = on + " / " + inputs.length + " ta ruxsat tanlangan";
    };
    grid.addEventListener("change", function (e) {
      if (e.target.hasAttribute("data-all")) {
        var card = e.target.closest(".nzi-pm");
        qa('li:not([hidden]) input[name="permissions"]', card).forEach(function (i) { i.checked = e.target.checked; i.dispatchEvent(new Event("change", { bubbles: true })); });
      }
      count();
    });
    head.querySelector("input").addEventListener("input", function (e) {
      var q = e.target.value.trim().toLowerCase();
      order.forEach(function (mod) {
        var shown = 0;
        qa("li", groups[mod].card).forEach(function (li) { var hit = !q || li.getAttribute("data-q").indexOf(q) >= 0; li.hidden = !hit; if (hit) shown++; });
        groups[mod].card.hidden = !shown;
      });
    });
    wrap.appendChild(head); wrap.appendChild(grid);
    var old = host.querySelector("#id_permissions") || inputs[0].closest("div");
    host.innerHTML = "";
    host.appendChild(wrap);
    void old;
    count();
  }
})();
