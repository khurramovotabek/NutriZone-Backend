/*
 * NutriZone Admin -- the online kassa (templates/admin/pos/terminal.html), on the branch-till engine (stores.pos_service).
 * Flow: open the shift (note + kassa PIN) → scan / tap products → customer (coins) → pay (discount, cash / card / split) → receipt.
 * Branch kassas sell from the storefront's own POS terminal; this till only sells online orders (main warehouse stock).
 * Keyboard: F2 search · F4 pay · Esc closes a dialog · a 2D scanner (keyboard wedge) works wherever the focus is.
 */
(function () {
  "use strict";
  var app = document.getElementById("px-app");
  if (!app) return;
  var cfg = JSON.parse(document.getElementById("px-config").textContent);
  var L = JSON.parse(document.getElementById("px-i18n").textContent);
  var dlg = document.getElementById("px-dialog");
  var S = { session: null, sale: null, catalog: [], q: "", inStock: true, busy: false, storeInfo: null, timer: null, top: [], hasPin: true };
  function pref(k, v) { try { if (v === undefined) return localStorage.getItem("nzpos_" + k); localStorage.setItem("nzpos_" + k, v); } catch (e) { return null; } }
  var scan = { text: "", at: 0 };

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function money(n) { return Math.round(Number(n) || 0).toLocaleString("ru-RU").replace(/ /g, " "); }
  function num(v) { v = String(v == null ? "" : v).replace(/\s/g, "").replace(",", "."); return v === "" ? 0 : Number(v) || 0; }
  function csrf() { var i = document.querySelector("input[name=csrfmiddlewaretoken]"); return i ? i.value : ""; }
  function url(action, params) {
    var q = Object.keys(params || {}).map(function (k) { return k + "=" + encodeURIComponent(params[k]); }).join("&");
    return cfg.urls.api.replace("__", action) + (q ? "?" + q : "");
  }
  function call(action, body, params) {
    var opts = { credentials: "same-origin", headers: { "X-CSRFToken": csrf(), "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" } };
    if (body !== undefined) { opts.method = "POST"; opts.body = JSON.stringify(body); }
    return fetch(url(action, params), opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok || !j.success) { var e = new Error((j.error && j.error.message) || L.error); e.code = j.error && j.error.code; e.details = j.error && j.error.details; throw e; } return j.data; });
    });
  }
  function toast(t, bad) { var el = document.querySelector("[data-nzp-toast]"); el.textContent = t; el.classList.toggle("is-error", !!bad); el.hidden = false; clearTimeout(toast.t); toast.t = setTimeout(function () { el.hidden = true; }, bad ? 4200 : 1600); }
  function beep(ok) { try { var c = new (window.AudioContext || window.webkitAudioContext)(), o = c.createOscillator(), g = c.createGain(); o.frequency.value = ok ? 880 : 220; g.gain.value = 0.05; o.connect(g); g.connect(c.destination); o.start(); setTimeout(function () { o.stop(); c.close(); }, ok ? 80 : 250); } catch (e) { /* no audio */ } }
  function thumb(src, cls) { return '<span class="' + (cls || "px-thumb") + '">' + (src ? '<img src="' + esc(src) + '" alt="">' : '<i class="fas fa-box" aria-hidden="true"></i>') + "</span>"; }
  function date(iso) { var d = new Date(iso); return d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" }); }

  /* ================= boot ================= */
  function boot() {
    call("state", undefined).then(function (d) { S.session = d.session; S.sale = d.sale; S.storeInfo = d.store; S.hasPin = d.has_pin; S.top = d.top || []; render(); if (S.session) loadCatalog(); })
      .catch(function (e) { app.innerHTML = '<div class="nzp-empty"><span class="nzp-empty-icon" style="--c:#e11d48"><i class="fas fa-triangle-exclamation" aria-hidden="true"></i></span><h3>' + esc(e.message) + "</h3></div>"; });
  }

  /* kassa PIN pad: onPin(pin) returns a promise; a wrong PIN shakes the pad and shows what is left */
  function pinDialog(title, sub, onPin) {
    var pin = "";
    var pad = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "del", "0", "ok"];
    openDialog('<div class="px-pin"><span class="px-pin-avatar" style="--c:#10b981"><i class="fas fa-key" aria-hidden="true"></i></span><h3>' + esc(title) + "</h3><p>" + esc(sub) + '</p><div class="px-dots" data-dots></div><p class="px-pin-err" data-err></p>' +
      '<input type="password" inputmode="numeric" autocomplete="off" class="px-pin-input" data-pin maxlength="6" autofocus aria-label="PIN">' +
      '<div class="px-pad">' + pad.map(function (k) { return '<button type="' + (k === "ok" ? "submit" : "button") + '" data-k="' + k + '" class="' + (k === "ok" ? "is-ok" : k === "del" ? "is-del" : "") + '"' + (k === "del" ? ' aria-label="⌫"' : k === "ok" ? ' aria-label="OK"' : "") + ">" + (k === "del" ? '<i class="fas fa-delete-left" aria-hidden="true"></i>' : k === "ok" ? '<i class="fas fa-check" aria-hidden="true"></i>' : k) + "</button>"; }).join("") + "</div>" +
      '<button type="button" class="px-link" data-close>' + esc(L.cancel) + "</button></div>",
    function (f) {
      if (pin.length < 4) return;
      onPin(pin).then(function () { dlg.close(); }).catch(function (e) {
        pin = ""; draw(); beep(false);
        var left = e.details && e.details.left;
        f.querySelector("[data-err]").textContent = e.code === "PIN_LOCKED" ? L.pinLocked : e.code === "PIN_WRONG" ? L.pinWrong + (left ? " (" + left + ")" : "") : e.code === "KASSA_PIN_NOT_SET" ? L.pinNotSet : e.message;
        var box = f.querySelector(".px-pin"); box.classList.remove("shake"); void f.offsetWidth; box.classList.add("shake");
      });
    });
    var f = dlg.querySelector("[data-px-dialog]"), input = f.querySelector("[data-pin]");
    function draw() { f.querySelector("[data-dots]").innerHTML = [0, 1, 2, 3, 4, 5].slice(0, Math.max(4, pin.length)).map(function (i) { return '<i class="' + (i < pin.length ? "on" : "") + '"></i>'; }).join(""); input.value = pin; }
    f.onclick = function (e) {
      var b = e.target.closest("[data-k]"); if (b && b.getAttribute("data-k") !== "ok") { var k = b.getAttribute("data-k"); pin = k === "del" ? pin.slice(0, -1) : (pin + k).slice(0, 6); draw(); input.focus(); }
      if (e.target.closest("[data-close]")) closeDialog();
    };
    input.oninput = function () { pin = input.value.replace(/\D/g, "").slice(0, 6); draw(); };
    draw();
  }

  function kassaChip() {
    return '<span class="px-chip px-chip-kassa"><i class="fas fa-globe" aria-hidden="true"></i><b>' + esc(S.storeInfo ? S.storeInfo.name : "") + "</b>" + (S.storeInfo && S.storeInfo.location ? "<small>" + esc(S.storeInfo.location) + "</small>" : "") + "</span>";
  }

  function render() {
    if (!S.session) return renderClosed();
    var ses = S.session;
    app.innerHTML =
      '<div class="px-bar">' +
        kassaChip() +
        '<span class="px-chip px-chip-live"><i class="fas fa-circle" aria-hidden="true"></i>' + esc(L.shift) + " · " + date(ses.opened_at) + " · <b>" + ses.sales_count + "</b> " + esc(L.shiftSales) + " · <b>" + money(ses.expected_cash) + "</b> " + esc(L.shiftCash) + "</span>" +
        '<span class="px-chip"><i class="fas fa-user" aria-hidden="true"></i>' + esc(cfg.cashier) + "</span>" +
        '<button type="button" class="px-chip' + (pref("autoprint") === "1" ? " is-on" : "") + '" data-act="autoprint" title="' + esc(L.autoPrintHint) + '"><i class="fas fa-print" aria-hidden="true"></i>' + esc(L.autoPrint) + "</button>" +
        '<span class="px-bar-right"><span class="px-keys">' + esc(L.keys) + '</span><button type="button" class="nzp-btn nzp-btn-ghost nzp-btn-sm" data-act="recent"><i class="fas fa-receipt" aria-hidden="true"></i> ' + esc(L.recent) + '</button><button type="button" class="nzp-btn nzp-btn-ghost nzp-btn-sm" data-act="close-shift"><i class="fas fa-lock" aria-hidden="true"></i> ' + esc(L.closeShift) + "</button></span>" +
      "</div>" +
      '<div class="px-grid">' +
        '<section class="px-left">' +
          '<label class="px-search"><i class="fas fa-magnifying-glass" aria-hidden="true"></i><input data-q value="' + esc(S.q) + '" placeholder="' + esc(L.searchLeft || L.search) + '" autocomplete="off"><span class="px-ready"><i class="fas fa-magnifying-glass" aria-hidden="true"></i></span></label>' +
          (S.top.length ? '<div class="px-top"><span class="px-top-label"><i class="fas fa-fire" aria-hidden="true"></i> ' + esc(L.top) + "</span>" + S.top.map(function (p, n) {
            return '<button type="button" class="px-top-btn" data-top="' + n + '">' + thumb(p.image_url, "px-top-img") + "<span><b>" + esc(p.name) + "</b><small>" + (p.price ? money(p.price) : "") + "</small></span></button>";
          }).join("") + "</div>" : "") +
          '<div class="px-filters"><label class="nzd-check px-instock"><input type="checkbox" data-instock' + (S.inStock ? " checked" : "") + "><span><b>" + esc(L.inStockOnly) + "</b></span></label></div>" +
          '<div class="px-products" data-products></div>' +
        "</section>" +
        '<aside class="px-right"><div class="px-scan" data-scanner></div><div class="px-basket" data-basket></div></aside>' +
      "</div>";
    renderProducts(); renderScanner(); renderBasket();
    focusScanner();
  }

  function renderClosed() {
    var now = new Date();
    app.innerHTML = '<div class="px-bar">' + kassaChip() + "</div>" +
      '<section class="nzp-card px-open"><span class="px-open-icon"><i class="fas fa-cash-register" aria-hidden="true"></i></span><h2>' + esc(L.shiftClosed) + "</h2><p>" + esc(L.shiftClosedHint) + "</p>" +
      '<dl class="px-open-facts"><div><dt>' + esc(L.kassa) + "</dt><dd>" + esc(S.storeInfo ? S.storeInfo.name : "") + "</dd></div><div><dt>" + esc(L.seller) + "</dt><dd>" + esc(cfg.cashier) + "</dd></div><div><dt>" + esc(L.now) + '</dt><dd data-clock>' + now.toLocaleTimeString("ru-RU") + "</dd></div></dl>" +
      (S.hasPin ? "" : '<p class="px-open-warn"><i class="fas fa-triangle-exclamation" aria-hidden="true"></i> ' + esc(L.pinNotSet) + ' <a href="' + esc(cfg.urls.cashiers) + '">' + esc(L.setPin) + "</a></p>") +
      '<label class="nzd-field-label">' + esc(L.openNote) + '<input class="nzd-input" data-onote maxlength="200" placeholder="' + esc(L.openNotePh) + '"></label>' +
      '<button type="button" class="nzp-btn nzp-btn-primary px-big-btn" data-act="open-shift"' + (S.hasPin ? "" : " disabled") + '><i class="fas fa-lock-open" aria-hidden="true"></i> ' + esc(L.openShift) + "</button>" +
      '<small class="px-open-hint"><i class="fas fa-key" aria-hidden="true"></i> ' + esc(L.openPinHint) + "</small></section>";
    clearInterval(renderClosed.t);
    renderClosed.t = setInterval(function () { var c = app.querySelector("[data-clock]"); if (!c) return clearInterval(renderClosed.t); c.textContent = new Date().toLocaleTimeString("ru-RU"); }, 1000);
  }

  function openShift() {
    var note = (app.querySelector("[data-onote]") || {}).value || "";
    pinDialog(L.openShift, L.enterKassaPin, function (pin) {
      return call("open_shift", { note: note, pin: pin }).then(function (d) {
        S.session = d.session; S.sale = d.sale; render(); loadCatalog(); toast("✓ " + L.shiftOpened);
        call("top").then(function (t) { S.top = t.top || []; if (!dlg.open) render(); }).catch(function () {});
      });
    });
  }

  function renderProducts() {
    var box = app.querySelector("[data-products]"); if (!box) return;
    if (!S.catalog.length) { box.innerHTML = '<div class="nzp-empty"><p>' + esc(S.q ? L.emptyBasketHint : "…") + "</p></div>"; return; }
    box.innerHTML = S.catalog.map(function (p, n) {
      var off = !p.sellable;
      return '<button type="button" class="px-card' + (off ? " is-off" : "") + '" data-pick="' + n + '">' + thumb(p.image_url, "px-card-img") +
        '<span class="px-card-body"><b>' + esc(p.name) + "</b><small>" + esc(p.variant_label || p.sku) + "</small>" +
        '<span class="px-card-foot"><em>' + (p.price ? money(p.price) + " <small>" + esc(L.som) + "</small>" : esc(L.noPrice)) + "</em>" +
        '<span class="wx-state ' + (p.stock > 5 ? "ok" : p.stock > 0 ? "low" : "out") + '">' + (p.stock > 0 ? p.stock + " " + esc(L.pcs) : esc(L.outOfStock)) + "</span></span></span></button>";
    }).join("");
  }

  function basketTotals() {
    var s = S.sale || { items: [], total: "0" };
    return { units: s.items.reduce(function (a, l) { return a + l.quantity; }, 0), total: num(s.total) };
  }

  function renderBasket() {
    var box = app.querySelector("[data-basket]"); if (!box) return;
    var s = S.sale, t = basketTotals(), c = s && s.customer;
    box.innerHTML =
      '<header class="px-basket-head"><h3><i class="fas fa-basket-shopping" aria-hidden="true"></i> ' + esc(L.basket) + ' <b class="px-count">' + t.units + "</b></h3>" +
        (s && s.items.length ? '<button type="button" class="px-link" data-act="void"><i class="fas fa-trash" aria-hidden="true"></i> ' + esc(L.clear) + "</button>" : "") + "</header>" +
      '<div class="px-customer">' + (c
        ? '<span class="px-avatar">' + esc((c.full_name || "?").slice(0, 1)) + '</span><span class="px-cust-text"><b>' + esc(c.full_name || c.phone_number) + "</b><small>" + esc(c.phone_number) + " · " + money(c.balance) + " coin" + (c.tier ? " · " + esc(c.tier.name) : "") + '</small></span><button type="button" class="px-link" data-act="remove-customer" aria-label="' + esc(L.remove) + '"><i class="fas fa-xmark" aria-hidden="true"></i></button>'
        : '<button type="button" class="px-add-customer" data-act="customer"><i class="fas fa-user-plus" aria-hidden="true"></i> ' + esc(L.addCustomer) + "</button>") + "</div>" +
      '<ul class="px-lines">' + (s && s.items.length ? s.items.map(function (l) {
        var max = l.stock != null && l.quantity >= l.stock;
        return '<li class="px-line' + (S.last && S.last.kind === "added" && S.last.item.variant_id === l.variant_id ? " is-last" : "") + '" data-line="' + l.id + '">' + thumb(l.image_url) + '<div class="px-line-main"><b>' + esc(l.name) + "</b><small>" + (l.variant_label ? esc(l.variant_label) + " · " : "") + money(l.unit_price) + " × " + l.quantity + "</small>" +
          ((l.batches || []).length ? '<span class="px-batches">' + l.batches.map(function (b) { return '<span>' + (b.batch ? "LOT " + esc(b.batch) : esc(L.batch)) + (b.expiry ? " · " + b.expiry.split("-").reverse().join(".") : "") + " ×" + b.qty + "</span>"; }).join("") + "</span>" : "") +
          '<span class="px-stepper"><button type="button" data-qty="-1" aria-label="−">−</button><b>' + l.quantity + '</b><button type="button" data-qty="1" aria-label="+"' + (max ? " disabled" : "") + '>+</button></span></div>' +
          '<div class="px-line-side"><b>' + money(l.line_total) + '</b><button type="button" class="px-link" data-remove aria-label="' + esc(L.remove) + '"><i class="fas fa-xmark" aria-hidden="true"></i></button></div></li>';
      }).join("") : '<li class="px-empty"><i class="fas fa-basket-shopping" aria-hidden="true"></i><b>' + esc(L.emptyBasket) + "</b><small>" + esc(L.emptyBasketHint) + "</small></li>") + "</ul>" +
      '<footer class="px-basket-foot"><div class="px-total"><span>' + esc(L.total) + "</span><b>" + money(t.total) + " <small>" + esc(L.som) + "</small></b></div>" +
        '<button type="button" class="nzp-btn nzp-btn-primary px-pay" data-act="pay"' + (s && s.items.length ? "" : " disabled") + '><i class="fas fa-credit-card" aria-hidden="true"></i> ' + esc(L.pay) + " <kbd>F4</kbd></button></footer>";
  }

  function focusSearch() { var q = app.querySelector("[data-q]"); if (q && !dlg.open) q.focus(); }
  function focusScanner() { var q = app.querySelector("[data-s]"); if (q && !dlg.open) q.focus(); }

  /* ================= scan → cart (right column, above the basket) ================= */
  function renderScanner() {
    var box = app.querySelector("[data-scanner]"); if (!box) return;
    var price = !!S.priceMode;
    box.className = "px-scan" + (price ? " is-price" : "");
    box.innerHTML =
      '<div class="px-scan-head"><span><i class="fas fa-barcode" aria-hidden="true"></i> ' + esc(price ? L.scanPriceTitle : L.scanTitle) + "</span>" +
        '<span class="px-scan-modes" role="radiogroup" aria-label="' + esc(L.scanMode) + '"><button type="button" role="radio" aria-checked="' + !price + '" data-smode="add"' + (price ? "" : ' class="on"') + ">" + esc(L.scanModeAdd) + '</button><button type="button" role="radio" aria-checked="' + price + '" data-smode="price"' + (price ? ' class="on"' : "") + '><i class="fas fa-tag" aria-hidden="true"></i> ' + esc(L.scanModePrice) + "</button></span></div>" +
      '<form class="px-scan-field" data-sform><i class="fas fa-barcode" aria-hidden="true"></i><input data-s autocomplete="off" spellcheck="false" placeholder="' + esc(price ? L.scanPricePh : L.scanPh) + '" aria-label="' + esc(price ? L.scanPricePh : L.scanPh) + '">' +
        (price ? "" : '<label class="px-scan-qty" title="' + esc(L.scanQty) + '"><span>×</span><input type="number" min="1" max="999" value="' + (S.mult || 1) + '" data-sq aria-label="' + esc(L.scanQty) + '"></label>') + "</form>" +
      '<div data-slast></div>';
    renderLast();
  }
  function renderLast() {
    var box = app.querySelector("[data-slast]"); if (!box) return;
    var l = S.last;
    if (!l) { box.innerHTML = ""; return; }
    if (l.kind === "error") { box.innerHTML = '<div class="px-last is-bad" role="status"><i class="fas fa-circle-exclamation" aria-hidden="true"></i><span><code>' + esc(l.code) + "</code> — " + esc(l.message) + "</span></div>"; return; }
    var p = l.item;
    box.innerHTML = '<div class="px-last ' + (l.kind === "price" ? "is-price" : "is-ok") + '" role="status">' + thumb(p.image_url, "px-last-img") +
      '<span class="px-last-text"><b>' + esc(p.name) + "</b><small>" + (p.price ? money(p.price) + " " + esc(L.som) : esc(L.noPrice)) + " · " + p.stock + " " + esc(L.pcs) + (p.batch ? " · LOT " + esc(p.batch.number || p.batch.expiry || "") : "") + "</small></span>" +
      (l.kind === "added"
        ? '<span class="px-last-badge">+' + l.qty + " → " + l.inBasket + '</span><button type="button" class="px-link" data-act="undo-scan" title="' + esc(L.scanUndo) + " (−" + l.qty + ')" aria-label="' + esc(L.scanUndo) + '"><i class="fas fa-rotate-left" aria-hidden="true"></i></button>'
        : '<span class="px-last-badge is-price">' + esc(p.sellable ? L.scanPriceOnly : L.outOfStock) + "</span>") + "</div>";
  }
  function lineOf(variantId) { return (S.sale && S.sale.items || []).filter(function (x) { return x.variant_id === variantId; })[0]; }
  function undoScan() {
    var l = S.last; if (!l || l.kind !== "added") return;
    var line = lineOf(l.item.variant_id); if (!line) return;
    var next = line.quantity - l.qty;
    (next > 0 ? act("qty", { line_id: line.id, quantity: next }) : act("remove", { line_id: line.id }))
      .then(function () { S.last = null; renderLast(); focusScanner(); }).catch(function () {});
  }
  function adjustLast(delta) {
    var l = S.last; if (!l || l.kind !== "added") return;
    var line = lineOf(l.item.variant_id); if (!line) return;
    var next = line.quantity + delta;
    (next > 0 ? act("qty", { line_id: line.id, quantity: next }) : act("remove", { line_id: line.id }))
      .then(function () { l.inBasket = Math.max(0, next); renderLast(); }).catch(function () {});
  }

  /* ================= data ================= */
  function loadCatalog() {
    return call("catalog", undefined, { q: S.q, in_stock: S.inStock ? "1" : "" }).then(function (d) { S.catalog = d.results || []; renderProducts(); return d; });
  }
  function adopt(d) { if (d.sale) S.sale = d.sale; if (d.session) S.session = d.session; renderBasket(); }
  function act(action, body) {
    if (S.busy) return Promise.resolve();
    S.busy = true;
    return call(action, Object.assign({ sale_id: S.sale && S.sale.id }, body || {})).then(function (d) { adopt(d); return d; })
      .catch(function (e) { beep(false); toast(e.message, true); throw e; })
      .finally(function () { S.busy = false; });
  }
  function add(p, code, qty) {
    qty = qty || 1;
    if (!p.sellable) { beep(false); S.last = { kind: "error", code: code || p.sku, message: p.stock > 0 ? L.noPrice : L.outOfStock }; renderLast(); toast(S.last.message, true); return; }
    if (p.batch && p.batch.expired) { beep(false); S.last = { kind: "error", code: code || p.sku, message: L.expiredBatch || L.outOfStock }; renderLast(); return; }
    act("add", { variant_id: p.variant_id, quantity: qty, code: code || "" }).then(function () {
      beep(true);
      var line = lineOf(p.variant_id);
      S.last = { kind: "added", item: p, qty: qty, inBasket: line ? line.quantity : qty };
      renderLast(); renderBasket();
    }).catch(function (e) { S.last = { kind: "error", code: code || p.sku, message: e.message }; renderLast(); });
  }
  function handleCode(code, qty) {
    code = (code || "").trim(); if (!code) return;
    call("catalog", undefined, { q: code }).then(function (d) {
      var hit = d.exact_match || (d.results && d.results.length === 1 ? d.results[0] : null);
      if (!hit) { beep(false); S.last = { kind: "error", code: code, message: L.scanNotFound }; renderLast(); return; }
      if (S.priceMode) { beep(true); S.last = { kind: "price", item: hit }; renderLast(); return; }
      add(hit, code, qty);
    }).catch(function (e) { beep(false); toast(e.message, true); });
  }

  /* ================= dialogs ================= */
  function openDialog(html, onSubmit, wide) {
    var form = dlg.querySelector("[data-px-dialog]");
    form.innerHTML = html; dlg.classList.toggle("px-wide", !!wide);
    form.onsubmit = function (e) { e.preventDefault(); onSubmit(form); };
    dlg.showModal();
    var first = form.querySelector("[autofocus]") || form.querySelector("input"); if (first) { first.focus(); if (first.select) first.select(); }
  }
  function closeDialog() { dlg.close(); focusScanner(); }
  dlg.addEventListener("close", focusScanner);

  function payDialog() {
    var s = S.sale, c = s.customer, total = num(s.total), maxPct = num(cfg.max_discount_percent);
    var redeem = c && c.redeem && c.redeem.enabled ? c.redeem : null;
    var html = '<header><span class="nzd-dialog-icon" style="color:#10b981;background:color-mix(in srgb,#10b981 13%,transparent)"><i class="fas fa-credit-card" aria-hidden="true"></i></span><div><h3>' + esc(L.pay) + '</h3><p>' + esc(S.storeInfo.name) + " · " + s.items.length + " · " + money(total) + " " + esc(L.som) + "</p></div></header>" +
      '<div class="px-pay-grid"><div>' +
        '<div class="wx-two"><label class="nzd-field-label">' + esc(L.discount) + " (" + esc(L.som) + ')<input class="nzd-input" data-disc inputmode="numeric" placeholder="0"><small class="wx-muted">' + esc(L.discountMax.replace("%s", maxPct).replace("%%", "%")) + '</small></label>' +
        '<label class="nzd-field-label">' + esc(L.discountReason) + '<input class="nzd-input" data-reason maxlength="120"></label></div>' +
        (redeem ? '<label class="nzd-field-label">' + esc(L.useCoins) + " (max " + money(redeem.max_coins) + ')<input class="nzd-input" data-coins inputmode="numeric" placeholder="0"><small class="wx-muted">' + esc(L.balance) + ": " + money(c.balance) + "</small></label>" : "") +
        '<div class="px-methods" role="radiogroup">' + ["cash", "uzcard", "humo", "split"].map(function (m, i) { return '<label class="px-method"><input type="radio" name="m" value="' + m + '"' + (i === 0 ? " checked" : "") + '><span><i class="fas ' + ({ cash: "fa-money-bill-wave", uzcard: "fa-credit-card", humo: "fa-credit-card", split: "fa-layer-group" })[m] + '" aria-hidden="true"></i>' + esc(L[m]) + "</span></label>"; }).join("") + "</div>" +
        '<div data-cash><label class="nzd-field-label">' + esc(L.tendered) + '<input class="nzd-input px-big" data-tendered inputmode="numeric" autofocus></label><div class="px-quick" data-quick></div></div>' +
        '<div data-split hidden><div class="px-split">' + ["cash", "uzcard", "humo"].map(function (m) { return '<label class="nzd-field-label">' + esc(L[m]) + '<input class="nzd-input" data-part="' + m + '" inputmode="numeric" placeholder="0"></label>'; }).join("") + "</div><small class=\"wx-muted\">" + esc(L.parts) + "</small></div>" +
      '</div><div class="px-due"><span>' + esc(L.total) + '</span><b data-due>' + money(total) + '</b><small data-change-row hidden>' + esc(L.changeDue) + ': <b data-change>0</b></small></div></div>' +
      '<div class="nzd-next-row" style="justify-content:flex-end"><button type="button" class="nzp-btn nzp-btn-ghost" data-close>' + esc(L.cancel) + '</button><button class="nzp-btn nzp-btn-primary px-big-btn"><i class="fas fa-check" aria-hidden="true"></i> ' + esc(L.complete) + "</button></div>";
    openDialog(html, function (f) {
      var m = f.querySelector("input[name=m]:checked").value, due = calc(f);
      var body = { discount: num(f.querySelector("[data-disc]").value), discount_reason: f.querySelector("[data-reason]").value, coins: f.querySelector("[data-coins]") ? num(f.querySelector("[data-coins]").value) : 0 };
      if (m === "split") {
        body.payment_method = "cash"; // with `payments` the split decides; the method is only a fallback
        body.payments = ["cash", "uzcard", "humo"].map(function (k) { return { method: k, amount: num(f.querySelector('[data-part="' + k + '"]').value) }; }).filter(function (p) { return p.amount > 0; });
        body.amount_tendered = (body.payments.filter(function (p) { return p.method === "cash"; })[0] || {}).amount || null;
      } else {
        body.payment_method = m;
        body.amount_tendered = m === "cash" ? (num(f.querySelector("[data-tendered]").value) || due) : null;
      }
      complete(body);
    }, true);
    var f = dlg.querySelector("[data-px-dialog]");
    function calc() {
      var disc = num(f.querySelector("[data-disc]").value), coins = f.querySelector("[data-coins]") ? num(f.querySelector("[data-coins]").value) : 0;
      var due = Math.max(0, total - disc - coins);
      f.querySelector("[data-due]").textContent = money(due);
      var m = f.querySelector("input[name=m]:checked").value;
      f.querySelector("[data-cash]").hidden = m !== "cash"; f.querySelector("[data-split]").hidden = m !== "split";
      var tend = num(f.querySelector("[data-tendered]").value);
      f.querySelector("[data-change-row]").hidden = !(m === "cash" && tend > due);
      f.querySelector("[data-change]").textContent = money(tend - due);
      var quick = [due, Math.ceil(due / 10000) * 10000, Math.ceil(due / 50000) * 50000, Math.ceil(due / 100000) * 100000].filter(function (v, i, a) { return v > 0 && a.indexOf(v) === i; });
      f.querySelector("[data-quick]").innerHTML = quick.map(function (v) { return '<button type="button" data-tend="' + v + '">' + money(v) + "</button>"; }).join("");
      return due;
    }
    f.oninput = calc; f.onchange = calc;
    f.onclick = function (e) { var b = e.target.closest("[data-tend]"); if (b) { f.querySelector("[data-tendered]").value = b.getAttribute("data-tend"); calc(); } if (e.target.closest("[data-close]")) closeDialog(); };
    calc();
  }

  function complete(body) {
    act("complete", body).then(function (d) { dlg.close(); successDialog(d.done); }).catch(function () {});
  }

  function autoPrint(url) {
    // a hidden frame loads the 80 mm slip and opens the print dialog (silent with Chrome --kiosk-printing)
    var old = document.getElementById("px-print-frame"); if (old) old.remove();
    var fr = document.createElement("iframe");
    fr.id = "px-print-frame"; fr.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0;visibility:hidden";
    fr.src = url + (url.indexOf("?") > -1 ? "&" : "?") + "w=" + (pref("paper") || "80");
    fr.onload = function () { try { fr.contentWindow.focus(); fr.contentWindow.print(); } catch (e) { window.open(url + "?print=1", "_blank"); } };
    document.body.appendChild(fr);
  }

  function successDialog(done) {
    var receipt = cfg.urls.receipt.replace("00000000-0000-0000-0000-000000000000", done.id);
    if (pref("autoprint") === "1") autoPrint(receipt);
    var change = num(done.change);
    openDialog('<div class="px-success"><span class="px-success-icon"><i class="fas fa-check" aria-hidden="true"></i></span><h3>' + esc(L.done) + "</h3><p>" + esc(L.receiptNo) + " <b>" + esc(done.number) + "</b></p>" +
      '<div class="px-success-sum"><b>' + money(done.amount_due) + " " + esc(L.som) + "</b>" + (change > 0 ? "<span>" + esc(L.changeDue) + ": <b>" + money(change) + "</b></span>" : "") + (done.coins_earned ? "<span>" + esc(L.earned) + ": +" + done.coins_earned + "</span>" : "") + "</div>" +
      (done.customer ? '<p class="px-sent"><i class="fab fa-telegram" aria-hidden="true"></i> ' + esc(L.receiptSent) + "</p>" : "") +
      '<div class="px-success-actions"><a class="nzp-btn nzp-btn-ghost" href="' + receipt + '?print=1" target="_blank" rel="noopener"><i class="fas fa-print" aria-hidden="true"></i> ' + esc(L.printReceipt) + '</a><a class="nzp-btn nzp-btn-ghost" href="' + cfg.urls.sale.replace("00000000-0000-0000-0000-000000000000", done.id) + '" target="_blank" rel="noopener"><i class="fas fa-up-right-from-square" aria-hidden="true"></i> ' + esc(L.openSale) + '</a><button class="nzp-btn nzp-btn-primary" autofocus><i class="fas fa-plus" aria-hidden="true"></i> ' + esc(L.newSale) + " <kbd>Enter</kbd></button></div></div>", function () { closeDialog(); });
    beep(true);
    loadCatalog();
    render();
    call("top").then(function (t) { // best sellers move with every sale
      S.top = t.top || [];
      if (!dlg.open) return render();
      dlg.addEventListener("close", function again() { dlg.removeEventListener("close", again); render(); });
    }).catch(function () {});
  }

  function customerDialog() {
    openDialog('<header><span class="nzd-dialog-icon" style="color:#6366f1;background:color-mix(in srgb,#6366f1 13%,transparent)"><i class="fas fa-user" aria-hidden="true"></i></span><div><h3>' + esc(L.customer) + "</h3></div></header>" +
      '<label class="nzp-search"><i class="fas fa-magnifying-glass" aria-hidden="true"></i><input data-cq placeholder="' + esc(L.customerPh) + '" autofocus autocomplete="off"></label><ul class="px-cust-list" data-clist></ul>' +
      '<details class="px-new-cust"><summary>' + esc(L.newCustomer) + '</summary><div class="wx-two"><input class="nzd-input" data-nphone placeholder="+998"><input class="nzd-input" data-nname placeholder="' + esc(L.fullName) + '"></div></details>' +
      '<div class="nzd-next-row" style="justify-content:flex-end"><button type="button" class="nzp-btn nzp-btn-ghost" data-close>' + esc(L.cancel) + '</button><button class="nzp-btn nzp-btn-primary">' + esc(L.addCustomer) + "</button></div>",
    function (f) {
      var phone = f.querySelector("[data-nphone]").value.trim();
      if (!phone) return;
      act("set_customer", { phone_number: phone, full_name: f.querySelector("[data-nname]").value.trim() }).then(closeDialog).catch(function () {});
    });
    var f = dlg.querySelector("[data-px-dialog]"), t = null;
    f.oninput = function (e) {
      if (!e.target.matches("[data-cq]")) return;
      clearTimeout(t); var q = e.target.value.trim(); if (q.length < 2) return;
      t = setTimeout(function () {
        call("customers", undefined, { q: q }).then(function (d) {
          f.querySelector("[data-clist]").innerHTML = (d.results || []).map(function (c) { return '<li><button type="button" data-cid="' + c.id + '"><span class="px-avatar">' + esc((c.full_name || "?").slice(0, 1)) + "</span><span><b>" + esc(c.full_name || "—") + "</b><small>" + esc(c.phone_number) + " · " + money(c.balance) + " coin</small></span></button></li>"; }).join("") || "<li class=\"wx-muted\">—</li>";
          if (/^\+?\d{9,}$/.test(q.replace(/\s/g, ""))) f.querySelector("[data-nphone]").value = q;
        });
      }, 250);
    };
    f.onclick = function (e) { var b = e.target.closest("[data-cid]"); if (b) act("set_customer", { customer_id: b.getAttribute("data-cid") }).then(closeDialog).catch(function () {}); if (e.target.closest("[data-close]")) closeDialog(); };
  }

  function closeShiftDialog() {
    call("shift_totals", undefined).then(function (d) {
      var s = d.session;
      openDialog('<header><span class="nzd-dialog-icon"><i class="fas fa-lock" aria-hidden="true"></i></span><div><h3>' + esc(L.closeShift) + "</h3><p>" + esc(S.storeInfo.name) + " · " + date(s.opened_at) + "</p></div></header>" +
        '<dl class="px-z"><dt>' + esc(L.shiftSalesTitle) + "</dt><dd>" + s.sales_count + "</dd><dt>" + esc(L.cash) + "</dt><dd>" + money(s.cash_sales) + "</dd><dt>Uzcard</dt><dd>" + money(s.uzcard_sales) + "</dd><dt>Humo</dt><dd>" + money(s.humo_sales) + "</dd><dt>" + esc(L.coins) + "</dt><dd>" + money(s.coins_redeemed) + "</dd><dt><b>" + esc(L.expected) + "</b></dt><dd><b>" + money(s.expected_cash) + "</b></dd></dl>" +
        '<label class="nzd-field-label">' + esc(L.counted) + '<input class="nzd-input px-big" data-counted inputmode="numeric" value="' + Math.round(num(s.expected_cash)) + '" autofocus></label><p class="px-diff" data-diff></p>' +
        '<input class="nzd-input" data-cnote maxlength="200" placeholder="' + esc(L.closeNote) + '">' +
        '<div class="nzd-next-row" style="justify-content:flex-end"><button type="button" class="nzp-btn nzp-btn-ghost" data-close>' + esc(L.cancel) + '</button><button class="nzp-btn nzp-btn-danger">' + esc(L.closeShift) + "</button></div>",
      function (f) {
        call("close_shift", { counted_cash: num(f.querySelector("[data-counted]").value), note: f.querySelector("[data-cnote]").value }).then(function () { closeDialog(); S.session = null; S.sale = null; render(); toast("✓ " + L.closeShift); })
          .catch(function (e) { toast(e.message, true); });
      });
      var f = dlg.querySelector("[data-px-dialog]");
      function diff() { var d = num(f.querySelector("[data-counted]").value) - num(s.expected_cash); f.querySelector("[data-diff]").innerHTML = esc(L.difference) + ': <b class="' + (d < 0 ? "wx-minus" : d > 0 ? "wx-plus" : "") + '">' + (d > 0 ? "+" : "") + money(d) + "</b>"; }
      f.oninput = diff; diff();
      f.onclick = function (e) { if (e.target.closest("[data-close]")) closeDialog(); };
    }).catch(function (e) { toast(e.message, true); });
  }

  function recentDialog() {
    call("recent", undefined).then(function (d) {
      openDialog('<header><span class="nzd-dialog-icon" style="color:#2563eb;background:color-mix(in srgb,#2563eb 13%,transparent)"><i class="fas fa-receipt" aria-hidden="true"></i></span><div><h3>' + esc(L.recent) + "</h3><p>" + esc(S.storeInfo.name) + "</p></div></header>" +
        '<ul class="px-recent">' + ((d.results || []).map(function (r) {
          return '<li><a href="' + cfg.urls.sale.replace("00000000-0000-0000-0000-000000000000", r.id) + '" target="_blank" rel="noopener"><b class="nz-num">' + esc(r.number) + "</b><span>" + (r.completed_at ? date(r.completed_at) : "") + " · " + r.item_count + " " + esc(L.pcs) + (r.customer ? " · " + esc(r.customer.full_name || r.customer.phone_number || "") : "") + "</span><em>" + money(r.paid) + "</em></a></li>";
        }).join("") || "<li class=\"wx-muted\">" + esc(L.noRecent) + "</li>") + "</ul>" +
        '<div class="nzd-next-row" style="justify-content:flex-end"><a class="nzp-btn nzp-btn-ghost" href="' + cfg.urls.sales + '">' + esc(L.openSale) + '</a><button class="nzp-btn nzp-btn-primary">' + esc(L.back) + "</button></div>", closeDialog, true);
    }).catch(function (e) { toast(e.message, true); });
  }

  /* ================= events ================= */
  app.addEventListener("click", function (e) {
    var b;
    if ((b = e.target.closest("[data-pick]"))) { add(S.catalog[Number(b.getAttribute("data-pick"))]); return; }
    if ((b = e.target.closest("[data-top]"))) { add(S.top[Number(b.getAttribute("data-top"))]); return; }
    var line = e.target.closest("[data-line]");
    if (line && (b = e.target.closest("[data-qty]"))) {
      var l = S.sale.items.filter(function (x) { return x.id === line.getAttribute("data-line"); })[0];
      act("qty", { line_id: l.id, quantity: l.quantity + Number(b.getAttribute("data-qty")) }).catch(function () {});
      return;
    }
    if (line && e.target.closest("[data-remove]")) { act("remove", { line_id: line.getAttribute("data-line") }).catch(function () {}); return; }
    var mode = e.target.closest("[data-smode]");
    if (mode) { S.priceMode = mode.getAttribute("data-smode") === "price"; renderScanner(); focusScanner(); return; }
    if (!(b = e.target.closest("[data-act]"))) return;
    var a = b.getAttribute("data-act");
    if (a === "open-shift") openShift();
    else if (a === "close-shift") closeShiftDialog();
    else if (a === "pay") payDialog();
    else if (a === "customer") customerDialog();
    else if (a === "remove-customer") act("remove_customer").catch(function () {});
    else if (a === "void") act("void").catch(function () {});
    else if (a === "recent") recentDialog();
    else if (a === "undo-scan") undoScan();
    else if (a === "autoprint") { pref("autoprint", pref("autoprint") === "1" ? "0" : "1"); b.classList.toggle("is-on", pref("autoprint") === "1"); toast(pref("autoprint") === "1" ? L.autoPrintOn : L.autoPrintOff); }
  });
  app.addEventListener("input", function (e) {
    if (e.target.matches("[data-q]")) { S.q = e.target.value; clearTimeout(S.timer); S.timer = setTimeout(loadCatalog, 220); }
  });
  app.addEventListener("change", function (e) {
    if (e.target.matches("[data-instock]")) { S.inStock = e.target.checked; loadCatalog(); }
    if (e.target.matches("[data-sq]")) { S.mult = Math.min(999, Math.max(1, parseInt(e.target.value, 10) || 1)); e.target.value = S.mult; }
  });
  // the scan form has two fields (code + "× N") and no submit button, so browsers don't submit it on Enter -- do it here
  function submitScan(form) {
    var input = form.querySelector("[data-s]"), q = form.querySelector("[data-sq]");
    var qty = q ? Math.min(999, Math.max(1, parseInt(q.value, 10) || 1)) : 1;
    var code = input.value; input.value = "";
    S.mult = 1; if (q) q.value = 1; // "× N" is for the next scan only
    handleCode(code, qty);
  }
  app.addEventListener("submit", function (e) { if (e.target.matches("[data-sform]")) { e.preventDefault(); submitScan(e.target); } });
  app.addEventListener("keydown", function (e) {
    if (e.target.matches("[data-s]") && !e.target.value && (e.key === "+" || e.key === "-")) { e.preventDefault(); adjustLast(e.key === "+" ? 1 : -1); return; }
    if (e.target.matches("[data-s], [data-sq]") && e.key === "Enter") { e.preventDefault(); submitScan(e.target.closest("[data-sform]")); if (e.target.matches("[data-sq]")) focusScanner(); return; }
    if (e.target.matches("[data-q]") && e.key === "Enter") {
      e.preventDefault();
      var exactOne = S.catalog.length === 1 && S.q.trim();
      if (exactOne) add(S.catalog[0], S.q.trim()); else handleCode(S.q);
      S.q = ""; e.target.value = ""; setTimeout(loadCatalog, 50);
    }
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "F2") { e.preventDefault(); focusSearch(); return; }
    if (e.key === "F3") { e.preventDefault(); focusScanner(); return; }
    if (e.key === "F4" && S.sale && S.sale.items.length && !dlg.open) { e.preventDefault(); payDialog(); return; }
    // keyboard-wedge scanner: fast keystrokes ending in Enter, wherever the focus is (except another input)
    var el = e.target, typing = el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT");
    if (typing || dlg.open || !S.session) return;
    var now = Date.now();
    if (e.key === "Enter") { if (scan.text.length >= 4) { e.preventDefault(); handleCode(scan.text, 1); } scan.text = ""; return; }
    if (e.key.length === 1) { scan.text = now - scan.at > 60 ? e.key : scan.text + e.key; scan.at = now; }
  });
  window.addEventListener("beforeunload", function (e) { if (S.busy) { e.preventDefault(); e.returnValue = ""; } });
  window.addEventListener("online", function () { toast(L.online); });
  window.addEventListener("offline", function () { toast(L.offline, true); });
  boot();
})();
