/* Dashboard → Cheklar → Yangi chek (templates/admin/receipts/manual.html).
 * A scanner types fast and ends with Enter: an exact hit (barcode / single result) is added at once, the same
 * variant again only raises its quantity. Typed names show a list (↑ ↓ Enter, Esc). The 80 mm preview, totals and
 * the hidden `lines` JSON follow every change; the button stays off until there is a line, and posts once. */
(function () {
  "use strict";
  var script = document.currentScript || document.querySelector("script[data-search]");
  var SEARCH = script && script.dataset.search;
  var form = document.getElementById("nzr-form");
  if (!form || !SEARCH) return;

  var q = document.getElementById("nzr-q"), res = document.getElementById("nzr-res"), body = document.getElementById("nzr-lines"),
      empty = document.getElementById("nzr-empty"), paper = document.getElementById("nzr-paper-lines"), json = document.getElementById("nzr-lines-json"),
      submit = document.getElementById("nzr-submit"), hint = document.getElementById("nzr-hint");
  var lines = [], results = [], active = -1, timer = null, seq = 0, sending = false, zeroOk = false;

  try { lines = JSON.parse(json.value || "[]") || []; } catch (e) { lines = []; }

  function fmt(n) { return Math.round(n || 0).toLocaleString("ru-RU").replace(/\s/g, " "); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function all(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }
  function say(text, bad) { hint.textContent = text || ""; hint.classList.toggle("bad", !!bad); }

  function render() {
    var total = 0, count = 0;
    body.innerHTML = lines.map(function (l, i) {
      var sum = l.quantity * l.unit_price; total += sum; count += l.quantity;
      return '<tr data-i="' + i + '"><td><b>' + esc(l.name) + '</b>' + (l.sku ? '<small>' + esc(l.sku) + '</small>' : '') + '</td>' +
        '<td class="c"><div class="nzr-qty"><button type="button" data-step="-1" aria-label="Kamaytirish">−</button>' +
        '<input type="number" min="1" max="9999" inputmode="numeric" value="' + l.quantity + '" data-f="quantity" aria-label="Soni">' +
        '<button type="button" data-step="1" aria-label="Ko\'paytirish">+</button></div></td>' +
        '<td class="r"><input class="nzr-price" type="number" min="0" step="100" inputmode="numeric" value="' + l.unit_price + '" data-f="unit_price" aria-label="Narxi"></td>' +
        '<td class="r"><b>' + fmt(sum) + '</b></td>' +
        '<td><button type="button" class="nzr-del" data-del aria-label="O\'chirish"><i class="fas fa-xmark" aria-hidden="true"></i></button></td></tr>';
    }).join("");
    empty.hidden = lines.length > 0;
    paper.innerHTML = lines.length ? lines.map(function (l) {
      return '<div class="nzr-paper-line"><span>' + esc(l.name) + '<small>' + l.quantity + ' × ' + fmt(l.unit_price) + '</small></span><b>' + fmt(l.quantity * l.unit_price) + '</b></div>';
    }).join("") : '<p class="nzr-paper-empty">Mahsulot qo\'shilgach shu yerda ko\'rinadi</p>';
    all("[data-nzr-total]").forEach(function (el) { el.textContent = fmt(total); });
    all("[data-nzr-count]").forEach(function (el) { el.textContent = count; });
    all("[data-nzr-lines]").forEach(function (el) { el.textContent = lines.length; });
    all("[data-nzr-vat]").forEach(function (el) { var r = parseFloat(el.dataset.rate) || 0; el.textContent = fmt(total * r / (100 + r)); });
    json.value = JSON.stringify(lines.map(function (l) { return { variant_id: l.variant_id, name: l.name, sku: l.sku, quantity: l.quantity, unit_price: l.unit_price }; }));
    var zero = lines.some(function (l) { return !l.unit_price; });
    submit.disabled = !lines.length || sending;
    if (!zero) zeroOk = false;
    if (lines.length && zero) say("Narxi 0 bo'lgan qator bor — tekshiring.", true); else if (!sending) say("");
  }

  function add(p) {
    var same = lines.filter(function (l) { return p.variant_id && l.variant_id === p.variant_id; })[0];
    if (same) same.quantity = Math.min(9999, same.quantity + 1);
    else lines.push({ variant_id: p.variant_id, name: p.name, sku: p.sku || "", quantity: 1, unit_price: Math.max(0, Math.round(parseFloat(p.price) || 0)) });
    close(); q.value = ""; render(); q.focus();
    var row = body.querySelector('tr[data-i="' + (same ? lines.indexOf(same) : lines.length - 1) + '"]');
    if (row) { row.classList.remove("flash"); void row.offsetWidth; row.classList.add("flash"); }
  }

  function close() { res.hidden = true; active = -1; q.setAttribute("aria-expanded", "false"); }
  function highlight(i) {
    var items = res.querySelectorAll("[data-k]"); if (!items.length) return;
    active = (i + items.length) % items.length;
    items.forEach(function (b, k) { b.classList.toggle("on", k === active); b.setAttribute("aria-selected", k === active ? "true" : "false"); });
    items[active].scrollIntoView({ block: "nearest" });
  }
  function show(list, text) {
    results = list;
    res.innerHTML = list.length ? list.map(function (p, i) {
      return '<button type="button" role="option" data-k="' + i + '"><span><b>' + esc(p.name) + '</b><small>' + esc(p.sku || "") + '</small></span><em>' + fmt(parseFloat(p.price)) + " so'm</em></button>";
    }).join("") : '<p class="nzr-noresult"><i class="fas fa-magnifying-glass" aria-hidden="true"></i> ' + esc(text) + '</p>';
    res.hidden = false; q.setAttribute("aria-expanded", "true");
    if (list.length) highlight(0);
  }

  function search(enter) {
    var v = q.value.replace(/[\u0000-\u001f]/g, "").trim();
    if (v.length < 2) { close(); return; }
    var mine = ++seq;
    res.classList.add("busy");
    fetch(SEARCH + "?q=" + encodeURIComponent(v), { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) { return r.json(); })
      .then(function (b) {
        if (mine !== seq) return; // an older, slower answer must not replace a newer one
        res.classList.remove("busy");
        var list = (b && b.results) || [];
        if (enter && list.length === 1) { add(list[0]); return; } // scanner / exact code
        show(list, "«" + v + "» topilmadi — shtrix-kod yoki nomni tekshiring");
      })
      .catch(function () { if (mine === seq) { res.classList.remove("busy"); show([], "Qidiruv ishlamadi — internetni tekshiring"); } });
  }

  q.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(function () { search(false); }, 220); });
  q.addEventListener("keydown", function (e) {
    if (e.key === "ArrowDown" && !res.hidden) { e.preventDefault(); highlight(active + 1); }
    else if (e.key === "ArrowUp" && !res.hidden) { e.preventDefault(); highlight(active - 1); }
    else if (e.key === "Escape") { close(); }
    else if (e.key === "Enter") {
      e.preventDefault();
      if (!res.hidden && active >= 0 && results[active] && !e.ctrlKey && !e.metaKey) { add(results[active]); return; }
      clearTimeout(timer); search(true);
    }
  });
  res.addEventListener("mousedown", function (e) { e.preventDefault(); }); // keep the input focused
  res.addEventListener("click", function (e) { var b = e.target.closest("[data-k]"); if (b) add(results[+b.dataset.k]); });
  document.addEventListener("click", function (e) { if (!e.target.closest(".nzr-search")) close(); });

  body.addEventListener("input", function (e) {
    var tr = e.target.closest("tr[data-i]"), f = e.target.dataset.f; if (!tr || !f) return;
    var l = lines[+tr.dataset.i], v = parseFloat(e.target.value);
    if (f === "quantity") l.quantity = Math.min(9999, Math.max(1, Math.round(v) || 1));
    else l.unit_price = Math.max(0, Math.round(v) || 0);
    // while typing only the derived cells change (the caret stays put); leaving the field re-draws the row
    tr.cells[3].innerHTML = "<b>" + fmt(l.quantity * l.unit_price) + "</b>";
    paperOnly();
  });
  function paperOnly() { // totals + preview without touching the inputs being typed in
    var total = lines.reduce(function (s, l) { return s + l.quantity * l.unit_price; }, 0);
    all("[data-nzr-total]").forEach(function (el) { el.textContent = fmt(total); });
    all("[data-nzr-vat]").forEach(function (el) { var r = parseFloat(el.dataset.rate) || 0; el.textContent = fmt(total * r / (100 + r)); });
    paper.innerHTML = lines.map(function (l) { return '<div class="nzr-paper-line"><span>' + esc(l.name) + '<small>' + l.quantity + ' × ' + fmt(l.unit_price) + '</small></span><b>' + fmt(l.quantity * l.unit_price) + '</b></div>'; }).join("");
    json.value = JSON.stringify(lines.map(function (l) { return { variant_id: l.variant_id, name: l.name, sku: l.sku, quantity: l.quantity, unit_price: l.unit_price }; }));
  }
  body.addEventListener("change", function () { render(); });
  body.addEventListener("click", function (e) {
    var tr = e.target.closest("tr[data-i]"); if (!tr) return;
    var i = +tr.dataset.i, st = e.target.closest("[data-step]");
    if (st) { lines[i].quantity = Math.min(9999, Math.max(1, lines[i].quantity + (+st.dataset.step))); render(); return; }
    if (e.target.closest("[data-del]")) { lines.splice(i, 1); render(); q.focus(); }
  });

  function syncChoices() {
    var pay = form.querySelector('input[name="payment_method"]:checked'), kind = form.querySelector('input[name="kind"]:checked');
    all("[data-nzr-pay]").forEach(function (el) { el.textContent = pay ? pay.nextElementSibling.textContent.trim() : ""; });
    var refund = kind && kind.value === "refund";
    form.classList.toggle("is-refund", refund);
    all("[data-nzr-kind-label]").forEach(function (el) { el.textContent = refund ? "Qaytarish cheki" : "Sotuv cheki"; });
    submit.querySelector("span").textContent = refund ? "Qaytarish chekini yaratish" : "Chekni yaratish";
  }
  form.addEventListener("change", function (e) { if (e.target.name === "payment_method" || e.target.name === "kind") syncChoices(); });

  form.addEventListener("submit", function (e) {
    render();
    if (!lines.length) { e.preventDefault(); say("Kamida bitta mahsulot qo'shing.", true); q.focus(); return; }
    if (sending) { e.preventDefault(); return; }
    if (lines.some(function (l) { return !l.unit_price; }) && !zeroOk) { // a free line is rare: ask once, the next press creates it
      e.preventDefault(); zeroOk = true; say("Narxi 0 bo'lgan qator bor. Shunday yaratish uchun tugmani yana bir bor bosing.", true); return;
    }
    sending = true; submit.disabled = true; submit.classList.add("busy"); say("Yaratilmoqda…");
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && !submit.disabled) { e.preventDefault(); form.requestSubmit ? form.requestSubmit(submit) : submit.click(); }
  });

  syncChoices(); render();
})();
