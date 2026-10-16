/*
 * NutriZone WMS -- transfer workspace. One screen runs the whole document:
 *   DRAFT      route, scan / search products from the source's stock, choose the BATCH (FEFO first), quantities
 *   READY      pick & scan at the source (planned vs scanned per batch line), dispatch
 *   IN TRANSIT / RECEIVING / PARTIAL   scan & count at the destination per batch line, wrong product / batch / expiry
 *              warnings, shortage / excess reasons, partial or final receipt
 *   DISCREPANCY  a manager settles every difference;  RECEIVED  complete;  COMPLETED / CANCELLED  read-only tabs
 *
 * Scanning rules
 *   - one scan = one unit, times the "× N" field (boxes); the row's stepper or typed number corrects it
 *   - the same code arriving twice within 150 ms is one physical scan (scanners that send CR+LF / double triggers);
 *     a deliberate second scan always counts -- and the "last scan" chip undoes the last one (−N)
 *   - a product with several batches: an extra batch barcode picks its batch, otherwise the open line expiring first
 *   - the receiver never gets the sent quantity pre-filled: every unit is scanned or typed
 * Saving: counts are absolute (idempotent), auto-saved 0.9 s after a change; a failed save keeps the counts on the
 * screen, retries every 5 s and when the network returns. Another user's change is picked up by a 20 s poll.
 */
(function () {
  "use strict";

  var cfg = JSON.parse(document.getElementById("wms-config").textContent);
  var app = document.getElementById("wms-app");
  var modal = document.getElementById("wms-modal");
  var T = null; // transfer as returned by the server
  var S = { lines: [], pick: {}, recv: {}, reasons: {}, resolutions: {}, dirty: false, saving: false, failed: false, results: [], hl: -1,
            batches: {}, choose: null, last: null, wrong: [], tab: "items", mult: 1 };
  var saveTimer = null, searchTimer = null, retryTimer = null;

  var STEPS = [["draft", "Qoralama"], ["ready", "Yig'ish"], ["in_transit", "Yo'lda"], ["receiving", "Qabul"], ["received", "Qabul qilindi"], ["completed", "Yakunlandi"]];
  var ORDER = { draft: 0, ready: 1, in_transit: 2, receiving: 3, partial: 3, received: 4, completed: 5, cancelled: -1 };
  var TONE = { draft: "#64748b", ready: "#0ea5e9", in_transit: "#6366f1", receiving: "#f59e0b", partial: "#f97316", received: "#10b981", completed: "#16a34a", cancelled: "#ef4444" };
  var ERR = {
    INSUFFICIENT_STOCK: "Manbada yetarli qoldiq yo'q.", SAME_LOCATION: "Manba va qabul qiluvchi bir xil bo'lishi mumkin emas.",
    EMPTY_TRANSFER: "Kamida bitta mahsulot qo'shing (yoki skanerlang).", PICK_MISMATCH: "Skanerlangan soni rejadan farq qiladi.",
    PICK_ABOVE_PLANNED: "Rejadagidan ko'p olib bo'lmaydi (faqat band qilingan miqdor).", EXPIRED_BATCH: "Muddati o'tgan partiyani jo'natib bo'lmaydi.",
    DISCREPANCY_REASON_REQUIRED: "Har bir kamomad / ortiqcha uchun sababni tanlang.", NOT_RECEIVABLE: "Bu transfer hozir qabul qilinmaydi.",
    BELOW_POSTED: "Bu mahsulotdan omborga kiritilgan miqdordan kam ko'rsatib bo'lmaydi.", INVALID_TRANSITION: "Bu holatda bu amal mumkin emas.",
    RESOLUTION_REQUIRED: "Har bir tafovut uchun qarorni tanlang.", NOT_EDITABLE: "Faqat qoralamani tahrirlash mumkin.",
    PRODUCT_INACTIVE: "Faol bo'lmagan mahsulot.", FORBIDDEN: "Bu amal uchun ruxsatingiz yo'q.", COUNT_UNREALISTIC: "Son juda katta — qayta sanab ko'ring.",
    NOT_FOUND: "Bu shtrix-kod bo'yicha mahsulot topilmadi.", NOT_READY: "Transfer jo'natishga tayyor emas.",
  };
  var COST_NOTE = { receipt: "oxirgi kirim tannarxi", catalog: "katalogdagi tannarx", price: "taxminiy (sotuv narxi)" };

  // ---------------------------------------------------------------- utils
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function money(n) { return Math.round(Number(n) || 0).toLocaleString("ru-RU").replace(/ /g, " "); }
  function sum(list, fn) { return list.reduce(function (n, x) { return n + (Number(fn(x)) || 0); }, 0); }
  function csrf() { var el = document.querySelector("[name=csrfmiddlewaretoken]"); if (el) return el.value; var m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/); return m ? decodeURIComponent(m[1]) : ""; }
  function api(url, body) {
    var opts = body === undefined ? { credentials: "same-origin" } : { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() }, body: JSON.stringify(body) };
    return fetch(url, opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok || j.ok === false) { var e = new Error((j.error && j.error.message) || "Xato (" + r.status + ")"); e.code = j.error && j.error.code; e.status = r.status; e.details = (j.error && j.error.details) || {}; throw e; }
        return j.data;
      });
    }, function () { var e = new Error("Tarmoq bilan aloqa yo'q"); e.code = "NETWORK"; throw e; });
  }
  function actionUrl(name) { return cfg.urls.action.replace("__", name); }
  function toast(kind, text) {
    var box = document.getElementById("wms-toasts");
    var el = document.createElement("div");
    el.className = "wms-toast " + kind;
    el.setAttribute("role", kind === "err" ? "alert" : "status");
    el.innerHTML = '<i class="fas ' + (kind === "ok" ? "fa-circle-check" : kind === "err" ? "fa-circle-exclamation" : "fa-circle-info") + '" aria-hidden="true"></i><span>' + esc(text) + "</span>";
    box.appendChild(el);
    setTimeout(function () { el.remove(); }, kind === "err" ? 6000 : 3200);
  }
  function explain(e) { return (e.code && ERR[e.code]) ? ERR[e.code] + (e.message && ERR[e.code] !== e.message && e.code !== "NETWORK" ? " " + e.message : "") : e.message; }
  function beep(ok) {
    try {
      var ctx = beep.ctx || (beep.ctx = new (window.AudioContext || window.webkitAudioContext)());
      var o = ctx.createOscillator(), g = ctx.createGain();
      o.frequency.value = ok ? 1250 : 240; g.gain.value = 0.06; o.connect(g); g.connect(ctx.destination); o.start(); o.stop(ctx.currentTime + (ok ? 0.08 : 0.25));
    } catch (e) { /* no audio */ }
  }
  function dialog(opts) {
    return new Promise(function (resolve) {
      var d = modal.querySelector(".wms-dialog");
      d.innerHTML = "<h4>" + esc(opts.title) + "</h4>" + (opts.html || "") +
        '<div class="row-actions"><button type="button" class="wms-btn" data-x="0">' + esc(opts.cancel || "Bekor qilish") + '</button><button type="button" class="wms-btn ' + (opts.danger ? "danger solid" : "primary") + '" data-x="1">' + esc(opts.ok || "Tasdiqlash") + "</button></div>";
      modal.hidden = false;
      var input = d.querySelector("input,textarea,select");
      (input || d.querySelector('[data-x="1"]')).focus();
      function close(v) { modal.hidden = true; d.removeEventListener("click", onClick); document.removeEventListener("keydown", onKey); resolve(v); setTimeout(focusScan, 0); }
      function onClick(e) { var b = e.target.closest("[data-x]"); if (b) close(b.getAttribute("data-x") === "1" ? (input ? input.value : true) : null); }
      function onKey(e) { if (e.key === "Escape") close(null); if (e.key === "Enter" && e.target.tagName !== "TEXTAREA") { e.preventDefault(); close(input ? input.value : true); } }
      d.addEventListener("click", onClick);
      document.addEventListener("keydown", onKey);
    });
  }
  function thumb(url) { return url ? '<img class="wms-thumb" src="' + esc(url) + '" alt="">' : '<span class="wms-thumb ph"><i class="fas fa-box" aria-hidden="true"></i></span>'; }
  function fmtDate(iso) { if (!iso) return ""; var p = String(iso).slice(0, 10).split("-"); return p.length === 3 ? p[2] + "." + p[1] + "." + p[0] : iso; }
  function daysLeft(iso) { if (!iso) return null; var d = new Date(String(iso).slice(0, 10) + "T00:00:00"), now = new Date(); now.setHours(0, 0, 0, 0); return Math.round((d - now) / 86400000); }
  function expiryTag(iso) {
    if (!iso) return '<span class="wms-muted">—</span>';
    var n = daysLeft(iso), tone = n < 0 ? "bad" : n <= 60 ? "warn" : "ok";
    return '<span class="wms-exp ' + tone + '">' + esc(fmtDate(iso)) + "<small>" + (n < 0 ? "muddati o'tgan" : n + " kun") + "</small></span>";
  }
  function batchTag(batch, expiry) { return batch ? '<span class="wms-batch">' + esc(batch) + "</span>" : '<span class="wms-batch none">' + (expiry ? "partiyasiz" : "FEFO") + "</span>"; }
  function batchName(l) { return l.batch || (l.expiry ? "partiyasiz" : "FEFO"); }
  function mode() {
    if (!T) return "loading";
    if (T.status === "draft") return "draft";
    if (T.status === "ready") return "pick";
    if (T.discrepancy_open) return "approve";
    if (["in_transit", "receiving", "partial"].indexOf(T.status) !== -1) return "receive";
    if (T.status === "received") return "received";
    return "done";
  }
  function lineKey(variant, batch, expiry) { return variant + "|" + (batch || "") + "|" + (expiry || ""); }

  // ---------------------------------------------------------------- state from server
  function adopt(data) {
    T = data;
    S.lines = T.items.map(function (i) {
      return { key: lineKey(i.variant_id, i.batch, i.expiry), variant_id: i.variant_id, name: i.name, sku: i.sku, barcode: i.barcode, size: i.size, image_url: i.image_url,
               available: i.source_available + (T.status === "ready" ? i.planned : 0), qty: i.planned, batch: i.batch, expiry: i.expiry, unit_cost: Number(i.unit_cost) || 0, cost_source: i.cost_source };
    });
    S.pick = {}; S.recv = {}; S.reasons = {}; S.resolutions = {};
    T.items.forEach(function (i) {
      S.pick[i.id] = i.picked;
      S.recv[i.id] = i.received;
      S.reasons[i.id] = { reason: i.reason || "", note: i.note || "" };
    });
    S.dirty = false; S.failed = false;
    if (T.status === "draft" && T.items.length) loadBatches(T.items.map(function (i) { return i.variant_id; }));
    render();
  }
  function load() { return api(cfg.urls.data).then(adopt).catch(function (e) { app.innerHTML = '<div class="wms-banner err"><i class="fas fa-triangle-exclamation" aria-hidden="true"></i><div><b>Transferni yuklab bo\'lmadi.</b> ' + esc(explain(e)) + ' <button type="button" class="wms-btn" onclick="location.reload()">Qayta yuklash</button></div></div>'; }); }
  function loadBatches(ids) {
    var need = ids.filter(function (id) { return !S.batches[id]; });
    if (!need.length || !cfg.urls.batches) return;
    api(cfg.urls.batches + "?location=" + T.source.id + "&variants=" + need.join(",")).then(function (map) {
      need.forEach(function (id) { S.batches[id] = map[id] || []; });
      if (mode() === "draft") render();
    }).catch(function () { /* the batch column just shows what the lines carry */ });
  }
  function batchQty(line) {
    var list = S.batches[line.variant_id];
    if (!list || !line.batch) return null;
    var hit = list.filter(function (b) { return b.batch === line.batch && (b.expiry || "") === (line.expiry || ""); })[0];
    return hit ? hit.quantity + (T.status === "ready" ? line.qty : 0) : 0;
  }

  // ---------------------------------------------------------------- render
  function render() {
    var m = mode(), st = T.status;
    var active = document.activeElement, keep = active && active.id === "wms-scan" ? active.value : null;
    app.innerHTML =
      '<div class="wms-head"><h2><i class="fas fa-right-left" style="color:var(--nz-primary)" aria-hidden="true"></i> ' + esc(T.number) +
      ' <span class="wms-pill" style="--t:' + (TONE[st] || "#64748b") + '">' + esc(T.status_label) + "</span>" + (T.discrepancy_open ? ' <span class="wms-pill" style="--t:#ef4444">Tafovut tasdig\'i kutilmoqda</span>' : "") + "</h2>" +
      '<div class="wms-routebar">' + chip(T.source, "Jo'natuvchi") + '<i class="fas fa-arrow-right wms-muted" aria-hidden="true"></i>' + chip(T.destination, "Qabul qiluvchi") + "</div></div>" +
      timeline() + netBanner() +
      '<div class="wms-ws"><div class="wms-main">' + main(m) + '</div><aside class="wms-side">' + side(m) + "</aside></div>";
    bind(m);
    var scan = document.getElementById("wms-scan");
    if (scan && keep) scan.value = keep;
    focusScan();
  }
  function chip(loc, label) {
    return '<span class="wms-loc-chip" style="--c:' + esc(loc.color) + '" title="' + esc(label) + '"><i class="fas ' + (loc.kind === "warehouse" ? "fa-warehouse" : "fa-store") + '" style="color:' + esc(loc.color) + '" aria-hidden="true"></i><span><small>' + esc(label) + "</small>" + esc(loc.name) + "</span></span>";
  }
  function timeline() {
    if (T.status === "cancelled") return '<div class="wms-banner err"><i class="fas fa-ban" aria-hidden="true"></i><div><b>Bekor qilingan</b> ' + esc(T.cancelled_at || "") + (T.cancel_reason ? " — " + esc(T.cancel_reason) : "") + "</div></div>";
    var now = ORDER[T.status];
    var meta = { draft: T.created_at + " · " + (T.created_by || ""), ready: T.ready_at || "", in_transit: T.dispatched_at ? T.dispatched_at + " · " + T.dispatched_by : "", received: T.received_at ? T.received_at + " · " + T.received_by : "", completed: T.completed_at ? T.completed_at + " · " + T.completed_by : "" };
    return '<ol class="wms-timeline" aria-label="Transfer bosqichlari">' + STEPS.map(function (s, i) {
      var cls = i < now || T.status === "completed" ? "done" : i === now ? "now" : "";
      if (i === 3 && T.status === "partial") cls = T.discrepancy_open ? "now bad" : "now warn";
      var label = i === 3 && T.status === "partial" ? (T.discrepancy_open ? "Tafovut" : "Qisman qabul") : s[1];
      return '<li class="wms-step ' + cls + '"' + (i === now ? ' aria-current="step"' : "") + "><i>" + (cls.indexOf("done") !== -1 ? "✓" : i + 1) + "</i>" + esc(label) + (meta[s[0]] ? "<small>" + esc(meta[s[0]]) + "</small>" : "") + "</li>";
    }).join("") + "</ol>";
  }
  function netBanner() {
    if (!S.failed) return "";
    return '<div class="wms-banner err" role="alert"><i class="fas fa-wifi" aria-hidden="true"></i><div><b>O\'zgarishlar hali saqlanmadi.</b> Skanerlashni davom ettiring — sonlar ekranda turadi va aloqa tiklanishi bilan avtomatik saqlanadi. <button type="button" class="wms-btn" data-act="retry"><i class="fas fa-rotate" aria-hidden="true"></i> Hozir saqlash</button></div></div>';
  }
  function scanBox(placeholder) {
    return '<div class="wms-scan"><i class="fas fa-barcode" aria-hidden="true"></i><input id="wms-scan" autocomplete="off" spellcheck="false" placeholder="' + esc(placeholder) + '" aria-label="' + esc(placeholder) + '">' +
      '<label class="wms-mult" title="Bitta skaner necha dona qo\'shadi (quti uchun)"><span>×</span><input id="wms-mult" type="number" min="1" max="999" inputmode="numeric" value="' + S.mult + '" aria-label="Har skaner miqdori"></label>' +
      "<div class='wms-results' hidden></div></div>" + lastScan() + chooser();
  }
  function lastScan() {
    if (!S.last) return "";
    return '<div class="wms-lastscan ' + (S.last.ok ? "ok" : "bad") + '" role="status"><i class="fas ' + (S.last.ok ? "fa-circle-check" : "fa-circle-exclamation") + '" aria-hidden="true"></i><span><b>' + esc(S.last.title) + "</b> " + esc(S.last.text || "") + "</span>" +
      (S.last.undo ? '<button type="button" class="wms-btn ghost" data-act="undo"><i class="fas fa-rotate-left" aria-hidden="true"></i> Bekor qilish (−' + S.last.undo.n + ")</button>" : "") + "</div>";
  }
  function stat(label, value, tone) { return '<div class="wms-stat"' + (tone ? ' style="--t:' + tone + '"' : "") + "><b>" + value + "</b><span>" + esc(label) + "</span></div>"; }

  function main(m) {
    if (m === "draft") return draftView();
    if (m === "pick") return pickView();
    if (m === "receive") return receiveView();
    if (m === "approve") return approveView();
    return readonlyView();
  }

  // ---- DRAFT
  function chooser() {
    var c = S.choose;
    if (!c) return "";
    var list = c.batches.map(function (b, i) {
      var n = daysLeft(b.expiry);
      return '<button type="button" class="wms-bopt' + (b.expired ? " off" : "") + '" data-pick="' + i + '"' + (b.expired ? " disabled" : "") + "><kbd>" + (i + 1) + "</kbd><span><b>" + esc(b.batch || "Partiyasiz") + "</b><small>" +
        (b.expiry ? esc(fmtDate(b.expiry)) + " · " + (n < 0 ? "muddati o'tgan" : n + " kun qoldi") : "muddati ko'rsatilmagan") + "</small></span><em>" + b.quantity + " dona</em>" + (i === c.fefo ? '<span class="wms-fefo">FEFO</span>' : "") + "</button>";
    }).join("");
    return '<div class="wms-chooser" role="dialog" aria-label="Partiyani tanlang"><div class="wms-chooser-head">' + thumb(c.product.image_url) + "<div><b>" + esc(c.product.name) + '</b><small>Bu mahsulotning bir nechta partiyasi bor — qaysi biridan jo\'natiladi? (1–' + c.batches.length + " tugmasi, Esc — bekor)</small></div></div>" +
      '<div class="wms-bopts">' + list + '<button type="button" class="wms-bopt auto" data-pick="auto"><kbd>0</kbd><span><b>Avtomatik (FEFO)</b><small>Jo\'natishda eng avval muddati tugaydiganidan olinadi</small></span><em>' + Math.min(c.product.available, sum(c.batches.filter(function (b) { return !b.expired; }), function (b) { return b.quantity; })) + " dona</em></button></div></div>";
  }
  function draftView() {
    var editable = cfg.perms.edit;
    var locOpts = function (sel, other) {
      return cfg.locations.map(function (l) { return '<option value="' + l.id + '"' + (l.id === sel ? " selected" : "") + (l.id === other ? " disabled" : "") + ">" + esc(l.name) + (l.kind === "warehouse" ? " (sklad)" : "") + "</option>"; }).join("");
    };
    var perVariant = {};
    S.lines.forEach(function (l) { perVariant[l.variant_id] = (perVariant[l.variant_id] || 0) + (Number(l.qty) || 0); });
    var rows = S.lines.map(function (l, idx) {
      var bq = batchQty(l), limit = bq != null ? bq : l.available;
      var over = (Number(l.qty) || 0) > limit || perVariant[l.variant_id] > l.available;
      var options = (S.batches[l.variant_id] || []).map(function (b) { var v = b.batch + "|" + b.expiry; return '<option value="' + esc(v) + '"' + (b.batch === l.batch && b.expiry === (l.expiry || "") ? " selected" : "") + (b.expired ? " disabled" : "") + ">" + esc(b.batch || "Partiyasiz") + (b.expiry ? " · " + fmtDate(b.expiry) : "") + " (" + b.quantity + ")</option>"; }).join("");
      var known = (S.batches[l.variant_id] || []).some(function (b) { return b.batch === l.batch && b.expiry === (l.expiry || ""); });
      var batchCell = editable ? '<select class="wms-input" data-batchsel aria-label="Partiya"><option value="|"' + (!l.batch ? " selected" : "") + ">FEFO (avtomatik)</option>" + options + (l.batch && !known ? '<option selected value="' + esc(l.batch + "|" + (l.expiry || "")) + '">' + esc(l.batch) + "</option>" : "") + "</select>" : batchTag(l.batch, l.expiry);
      return '<tr data-i="' + idx + '"' + (over ? ' class="is-over"' : "") + '><td class="num wms-muted">' + (idx + 1) + '</td><td><div class="wms-prod">' + thumb(l.image_url) + "<span><b>" + esc(l.name) + "</b><small>" + esc(l.sku) + (l.size ? " · " + esc(l.size) : "") + " · <code>" + esc(l.barcode || "—") + "</code></small></span></div></td>" +
        "<td>" + batchCell + "</td><td>" + expiryTag(l.expiry) + "</td>" +
        '<td class="num"><b' + (limit ? "" : ' style="color:#dc2626"') + ">" + limit + "</b>" + (bq != null ? '<small class="wms-muted d-block">partiyada</small>' : "") + "</td>" +
        '<td><div class="wms-stepper"><button type="button" data-dec aria-label="Kamaytirish">−</button><input data-qty inputmode="numeric" value="' + l.qty + '" aria-label="Transfer soni"><button type="button" data-inc aria-label="Ko\'paytirish">+</button></div>' + (over ? '<div class="wms-err-note">qoldiqdan ko\'p</div>' : "") + "</td>" +
        '<td class="num">' + money(l.unit_cost) + (l.cost_source === "price" ? '<small class="wms-warn-note d-block" title="' + esc(COST_NOTE.price) + '">taxminiy</small>' : "") + '</td><td class="num"><b>' + money(l.unit_cost * (Number(l.qty) || 0)) + "</b></td>" +
        '<td><button type="button" class="wms-btn ghost danger" data-rm aria-label="O\'chirish"><i class="fas fa-trash" aria-hidden="true"></i></button></td></tr>';
    }).join("");
    var units = sum(S.lines, function (l) { return l.qty; });
    var value = sum(S.lines, function (l) { return l.unit_cost * (Number(l.qty) || 0); });
    var products = Object.keys(perVariant).length, batches = S.lines.filter(function (l) { return l.batch; }).length;
    return '<div class="wms-card">' +
      '<div class="wms-grid2" style="margin-bottom:14px"><div class="wms-field"><label for="wms-src">Qayerdan</label><select class="wms-input" id="wms-src"' + (editable ? "" : " disabled") + ">" + locOpts(T.source.id, T.destination.id) + '</select></div>' +
      '<div class="wms-field"><label for="wms-dst">Qayerga</label><select class="wms-input" id="wms-dst"' + (editable ? "" : " disabled") + ">" + locOpts(T.destination.id, T.source.id) + "</select></div>" +
      '<div class="wms-field" style="grid-column:1/-1"><label for="wms-notes">Izoh</label><input class="wms-input" id="wms-notes" maxlength="500" value="' + esc(T.notes) + '"' + (editable ? "" : " disabled") + "></div></div>" +
      '<div class="wms-stats">' + stat("Mahsulot turlari", products) + stat("Partiyali qatorlar", batches) + stat("Jami dona", units) + stat("Jami qiymat (tannarx)", money(value) + " <small>so'm</small>") + "</div>" +
      (editable ? scanBox("Shtrix-kodni skanerlang yoki mahsulot nomini yozing…") : "") +
      (S.lines.length ? '<div class="wms-scroll"><table class="wms-table"><thead><tr><th class="num">№</th><th>Mahsulot</th><th>Partiya</th><th>Yaroqlilik</th><th class="num">Mavjud</th><th>Soni</th><th class="num">Tannarx</th><th class="num">Summa</th><th><span class="sr-only">Amallar</span></th></tr></thead><tbody>' + rows + "</tbody></table></div>"
        : '<div class="wms-empty"><i class="fas fa-barcode" aria-hidden="true"></i>Mahsulotni skanerlang yoki yuqoridan qidiring. Faqat <b>' + esc(T.source.name) + "</b> qoldig'idagi mahsulotlar qo'shiladi; bir nechta partiya bo'lsa, tanlash oynasi chiqadi.</div>") +
      '<div class="wms-foot"><div class="totals"><span>Turlar <b>' + products + "</b></span><span>Dona <b>" + units + "</b></span><span>Qiymat <b>" + money(value) + '</b></span><span id="wms-savestate" class="wms-muted" aria-live="polite"></span></div>' +
      '<div class="wms-toolbar">' + (cfg.perms.cancel ? '<button type="button" class="wms-btn danger" data-act="cancel"><i class="fas fa-ban" aria-hidden="true"></i> Bekor qilish</button>' : "") +
      (editable ? '<button type="button" class="wms-btn" data-act="save"><i class="fas fa-floppy-disk" aria-hidden="true"></i> Qoralamani saqlash</button><button type="button" class="wms-btn primary lg" data-act="ready"><i class="fas fa-lock" aria-hidden="true"></i> Ko\'rib chiqish va band qilish</button>' : "") +
      "</div></div></div>";
  }

  // ---- PICK & DISPATCH
  function pickView() {
    var rows = T.items.map(function (i, n) {
      var p = S.pick[i.id] || 0, d = p - i.planned;
      return '<tr data-id="' + i.id + '" class="' + (d === 0 ? "is-done" : "") + '"><td class="num wms-muted">' + (n + 1) + '</td><td><div class="wms-prod">' + thumb(i.image_url) + "<span><b>" + esc(i.name) + "</b><small>" + esc(i.sku) + " · <code>" + esc(i.barcode || "—") + "</code></small></span></div></td>" +
        "<td>" + batchTag(i.batch, i.expiry) + "</td><td>" + expiryTag(i.expiry) + '</td><td class="num"><b>' + i.planned + "</b></td>" +
        '<td><div class="wms-stepper"><button type="button" data-dec aria-label="Kamaytirish">−</button><input data-cnt inputmode="numeric" value="' + p + '" aria-label="Skanerlangan soni"><button type="button" data-inc aria-label="Ko\'paytirish">+</button></div></td>' +
        '<td class="num"><span class="wms-diff ' + (d === 0 ? "ok" : d < 0 ? "short" : "over") + '">' + (d === 0 ? "✓ mos" : (d > 0 ? "+" : "") + d) + '</span></td><td class="num">' + money(Number(i.unit_cost) * i.planned) + "</td></tr>";
    }).join("");
    var planned = sum(T.items, function (i) { return i.planned; });
    var picked = sum(T.items, function (i) { return S.pick[i.id] || 0; });
    var done = T.items.filter(function (i) { return (S.pick[i.id] || 0) === i.planned; }).length;
    return '<div class="wms-card"><div class="wms-banner info"><i class="fas fa-lock" aria-hidden="true"></i><div><b>1-bosqich — yig\'ish va jo\'natish.</b> Mahsulotlar ' + esc(T.source.name) + ' qoldig\'ida band qilingan. Har birini skanerlang; skanerlangan son rejaga teng bo\'lganda jo\'nating.</div></div>' +
      '<div class="wms-stats">' + stat("Reja", planned) + stat("Skanerlandi", picked, "#4f46e5") + stat("Qoldi", Math.max(0, planned - picked), planned - picked ? "#d97706" : "#16a34a") + stat("Tayyor qatorlar", done + " / " + T.items.length, done === T.items.length ? "#16a34a" : null) + "</div>" +
      '<div class="wms-progress" aria-hidden="true"><i style="width:' + (planned ? Math.min(100, Math.round(picked * 100 / planned)) : 0) + '%"></i></div>' +
      scanBox("Yig'ilayotgan mahsulotni skanerlang…") +
      '<div class="wms-scroll"><table class="wms-table"><thead><tr><th class="num">№</th><th>Mahsulot</th><th>Partiya</th><th>Yaroqlilik</th><th class="num">Reja</th><th>Skanerlandi</th><th class="num">Farq</th><th class="num">Summa</th></tr></thead><tbody>' + rows + "</tbody></table></div>" +
      '<div class="wms-foot"><div class="totals"><span>Reja <b>' + planned + "</b></span><span>Skanerlandi <b>" + picked + '</b></span><span>Farq <b class="wms-diff ' + (picked === planned ? "ok" : "short") + '">' + (picked - planned) + '</b></span><span id="wms-savestate" class="wms-muted" aria-live="polite"></span></div>' +
      '<div class="wms-toolbar"><button type="button" class="wms-btn" data-act="fill" title="Skanersiz: hammasi rejadagidek yig\'ildi deb belgilash"><i class="fas fa-check-double" aria-hidden="true"></i> Qo\'lda: hammasi mos</button>' +
      (cfg.perms.edit ? '<button type="button" class="wms-btn" data-act="back"><i class="fas fa-rotate-left" aria-hidden="true"></i> Qoralamaga</button>' : "") +
      (cfg.perms.cancel ? '<button type="button" class="wms-btn danger" data-act="cancel"><i class="fas fa-ban" aria-hidden="true"></i> Bekor qilish</button>' : "") +
      (cfg.perms.send ? '<button type="button" class="wms-btn primary lg" data-act="dispatch"><i class="fas fa-truck-fast" aria-hidden="true"></i> Jo\'natish</button>' : "") + "</div></div></div>";
  }

  // ---- RECEIVE
  function reasonSelect(id) {
    var r = S.reasons[id] || {};
    return '<select class="wms-input" data-reason aria-label="Tafovut sababi"><option value="">Sabab tanlang…</option>' + cfg.reasons.map(function (x) { return '<option value="' + x[0] + '"' + (x[0] === r.reason ? " selected" : "") + ">" + esc(x[1]) + "</option>"; }).join("") + "</select>" +
      '<input class="wms-input" data-note placeholder="Izoh (ixtiyoriy)" aria-label="Izoh" style="margin-top:6px;width:100%" value="' + esc(r.note || "") + '">';
  }
  function statusOf(sent, got) {
    if (!got && sent) return ['<span class="wms-pill" style="--t:#64748b">Kutilmoqda</span>', "wait"];
    if (got === sent) return ['<span class="wms-pill" style="--t:#16a34a">Mos</span>', "ok"];
    if (got < sent) return ['<span class="wms-pill" style="--t:#dc2626">Kamomad ' + (got - sent) + "</span>", "short"];
    return ['<span class="wms-pill" style="--t:#d97706">Ortiqcha +' + (got - sent) + "</span>", "over"];
  }
  function allocText(i) {
    if (!i.allocations || i.allocations.length < 2) return "";
    return '<small class="wms-muted d-block">' + i.allocations.map(function (a) { return esc(a.batch || "partiyasiz") + (a.expiry ? " (" + fmtDate(a.expiry) + ")" : "") + ": " + a.qty; }).join(" · ") + "</small>";
  }
  function wrongBox() {
    if (!S.wrong.length) return "";
    return '<div class="wms-banner warn"><i class="fas fa-triangle-exclamation" aria-hidden="true"></i><div><b>Transferga mos kelmagan skanlar (' + S.wrong.length + ")</b> — omborga kiritilmaydi. Kerak bo'lsa, tegishli qatorda «Noto'g'ri mahsulot» sababini tanlang va menejerga xabar bering." +
      '<ul class="wms-wrong">' + S.wrong.slice(0, 8).map(function (w) { return "<li><b>" + esc(w.kind) + "</b> " + esc(w.text) + " <small>" + esc(w.at) + "</small></li>"; }).join("") + "</ul></div></div>";
  }
  function receiveView() {
    var sent = 0, got = 0, diffLines = 0;
    var rows = "", cards = "";
    T.items.forEach(function (i, n) {
      var r = S.recv[i.id] || 0, stt = statusOf(i.dispatched, r);
      sent += i.dispatched; got += r;
      var need = r !== i.dispatched;
      if (need && r) diffLines += 1;
      var stepper = '<div class="wms-stepper"><button type="button" data-dec aria-label="Kamaytirish">−</button><input data-cnt inputmode="numeric" value="' + r + '" aria-label="Qabul qilingan soni"><button type="button" data-inc aria-label="Ko\'paytirish">+</button></div>';
      rows += '<tr data-id="' + i.id + '" class="' + (r === i.dispatched ? "is-done" : "") + '"><td class="num wms-muted">' + (n + 1) + '</td><td><div class="wms-prod">' + thumb(i.image_url) + "<span><b>" + esc(i.name) + "</b><small>" + esc(i.sku) + " · <code>" + esc(i.barcode || "—") + "</code></small></span></div></td>" +
        "<td>" + batchTag(i.batch, i.expiry) + allocText(i) + "</td><td>" + expiryTag(i.expiry) + '</td><td class="num"><b>' + i.dispatched + "</b></td>" +
        "<td>" + stepper + (i.posted ? '<div class="wms-muted" style="font-size:.68rem">omborga kirgan: ' + i.posted + "</div>" : "") + "</td>" +
        '<td class="num"><span class="wms-diff ' + stt[1] + '">' + (r - i.dispatched > 0 ? "+" : "") + (r - i.dispatched) + "</span></td><td>" + stt[0] + "</td><td>" + (need ? reasonSelect(i.id) : '<span class="wms-muted">—</span>') + "</td></tr>";
      cards += '<div class="wms-rcard ' + stt[1] + '" data-id="' + i.id + '"><div class="wms-prod">' + thumb(i.image_url) + "<span><b>" + esc(i.name) + "</b><small>" + esc(i.barcode || i.sku) + " · " + esc(batchName(i)) + (i.expiry ? " · " + fmtDate(i.expiry) : "") + "</small></span></div>" +
        '<div class="nums"><div><b>' + i.dispatched + "</b><span>Jo'natilgan</span></div><div><b>" + r + "</b><span>Qabul</span></div><div><b class='wms-diff " + stt[1] + "'>" + (r - i.dispatched) + "</b><span>Farq</span></div></div>" +
        '<div style="display:flex;justify-content:center">' + stepper + "</div>" + (need ? '<div style="margin-top:10px">' + reasonSelect(i.id) + "</div>" : "") + "</div>";
    });
    var can = cfg.perms.receive;
    return '<div class="wms-card"><div class="wms-banner info"><i class="fas fa-box-open" aria-hidden="true"></i><div><b>2-bosqich — qabul qilish.</b> ' + esc(T.dispatched_by || "") + (T.dispatched_at ? " · " + esc(T.dispatched_at) : "") + ' jo\'natgan. Kelgan har bir mahsulotni skanerlang — jo\'natilgan son avtomatik qabul qilingan deb belgilanmaydi.</div></div>' +
      (T.status === "partial" ? '<div class="wms-banner warn"><i class="fas fa-triangle-exclamation" aria-hidden="true"></i><div>Qisman qabul qilingan. Qolgan mahsulotlarni sanab, qabulni yakunlang.</div></div>' : "") +
      '<div class="wms-stats">' + stat("Kutilgan qatorlar", T.items.length) + stat("Kutilgan dona", sent) + stat("Skanerlandi", got, "#4f46e5") + stat("Qoldi", Math.max(0, sent - got), sent - got > 0 ? "#d97706" : "#16a34a") + stat("Tafovutli qatorlar", diffLines, diffLines ? "#dc2626" : "#16a34a") + "</div>" +
      '<div class="wms-progress" aria-hidden="true"><i style="width:' + (sent ? Math.min(100, Math.round(got * 100 / sent)) : 0) + '%"></i></div>' +
      (can ? scanBox("Kelgan mahsulotni skanerlang…") : "") + wrongBox() +
      '<div class="wms-rtable wms-scroll"><table class="wms-table"><thead><tr><th class="num">№</th><th>Mahsulot</th><th>Partiya</th><th>Yaroqlilik</th><th class="num">Jo\'natilgan</th><th>Qabul qilindi</th><th class="num">Farq</th><th>Holat</th><th>Tafovut sababi</th></tr></thead><tbody>' + rows + "</tbody></table></div>" +
      '<div class="wms-rcards">' + cards + "</div>" +
      '<div class="wms-foot"><div class="totals"><span>Jo\'natilgan <b>' + sent + "</b></span><span>Qabul <b>" + got + '</b></span><span>Farq <b class="wms-diff ' + (got === sent ? "ok" : got < sent ? "short" : "over") + '">' + (got - sent) + '</b></span><span id="wms-savestate" class="wms-muted" aria-live="polite"></span></div>' +
      (can ? '<div class="wms-toolbar"><button type="button" class="wms-btn" data-act="rsave"><i class="fas fa-floppy-disk" aria-hidden="true"></i> Saqlash</button><button type="button" class="wms-btn" data-act="rpartial"><i class="fas fa-box-open" aria-hidden="true"></i> Qisman qabul</button><button type="button" class="wms-btn success lg" data-act="rfinal"><i class="fas fa-circle-check" aria-hidden="true"></i> Ko\'rib chiqish va tasdiqlash</button></div>'
        : '<span class="wms-muted">Qabul qilish uchun «Filial qabul qiluvchi» ruxsati kerak.</span>') + "</div></div>";
  }

  // ---- APPROVE DISCREPANCY
  function approveView() {
    var rows = T.items.filter(function (i) { return i.received !== i.dispatched; }).map(function (i) {
      var d = i.received - i.dispatched;
      var opts = d < 0 ? [["write_off", "Hisobdan chiqarish (yo'lda yo'qolgan / shikastlangan)"], ["return_to_source", "Manbaga qaytarish (umuman jo'natilmagan)"]]
        : [["deduct_source", "Manbadan ayirish (hisobsiz jo'natilgan)"], ["accept", "Qabul qilish (ortiqcha topilgan)"]];
      return '<tr data-id="' + i.id + '"><td><div class="wms-prod">' + thumb(i.image_url) + "<span><b>" + esc(i.name) + "</b><small>" + esc(i.sku) + "</small></span></div></td><td>" + batchTag(i.batch, i.expiry) + allocText(i) + "</td>" +
        '<td class="num">' + i.dispatched + '</td><td class="num">' + i.received + '</td><td class="num"><span class="wms-diff ' + (d < 0 ? "short" : "over") + '">' + (d > 0 ? "+" : "") + d + '</span></td><td class="num">' + money(Math.abs(d) * Number(i.unit_cost)) + "</td>" +
        "<td>" + esc((cfg.reasons.filter(function (x) { return x[0] === i.reason; })[0] || ["", "—"])[1]) + (i.note ? '<br><small class="wms-muted">' + esc(i.note) + "</small>" : "") + "</td>" +
        "<td>" + opts.map(function (o) { return '<label class="wms-radio"><input type="radio" name="res-' + i.id + '" value="' + o[0] + '"' + (S.resolutions[i.id] === o[0] ? " checked" : "") + "> " + esc(o[1]) + "</label>"; }).join("") + "</td></tr>";
    }).join("");
    return '<div class="wms-card"><div class="wms-banner warn"><i class="fas fa-scale-unbalanced" aria-hidden="true"></i><div><b>Tafovut tasdig\'i.</b> Qabul qilingan mahsulotlar ' + esc(T.destination.name) + ' omboriga kirdi (' + esc(T.received_by || "") + '). Har bir farq bo\'yicha qaror qabul qiling — shundan so\'ng transfer yakunlanadi.</div></div>' +
      '<div class="wms-stats">' + stat("Kamomad", T.summary.shortage + " dona", "#dc2626") + stat("Ortiqcha", T.summary.excess + " dona", "#d97706") + stat("Tafovutli qatorlar", T.summary.differences) + "</div>" +
      '<div class="wms-scroll"><table class="wms-table"><thead><tr><th>Mahsulot</th><th>Partiya</th><th class="num">Jo\'natilgan</th><th class="num">Qabul</th><th class="num">Farq</th><th class="num">Qiymati</th><th>Sabab</th><th>Qaror</th></tr></thead><tbody>' + rows + "</tbody></table></div>" +
      '<div class="wms-foot"><span></span>' + (cfg.perms.approve ? '<button type="button" class="wms-btn primary lg" data-act="approve"><i class="fas fa-stamp" aria-hidden="true"></i> Tafovutni tasdiqlash</button>' : '<span class="wms-muted">Tasdiqlash uchun «Sklad menejeri» ruxsati kerak.</span>') + "</div></div>";
  }

  // ---- READ-ONLY (received / completed / cancelled): tabs
  function readonlyView() {
    var tabs = [["items", "Mahsulotlar", T.items.length], ["diff", "Tafovutlar", T.summary.differences], ["log", "Tarix", T.events.length], ["docs", "Hujjatlar", null]];
    var body;
    if (S.tab === "diff") body = diffTab();
    else if (S.tab === "log") body = logTab();
    else if (S.tab === "docs") body = docsTab();
    else body = itemsTab();
    return '<div class="wms-card">' + (T.status === "received" ? '<div class="wms-banner info"><i class="fas fa-circle-check" aria-hidden="true"></i><div>Hammasi qabul qilindi. Tekshirib, transferni yakunlang.</div></div>' : "") +
      '<div class="wms-tabs" role="tablist">' + tabs.map(function (t) { return '<button type="button" role="tab" class="wms-tab' + (S.tab === t[0] ? " on" : "") + '" aria-selected="' + (S.tab === t[0]) + '" data-tab="' + t[0] + '">' + esc(t[1]) + (t[2] != null ? " <b>" + t[2] + "</b>" : "") + "</button>"; }).join("") + "</div>" +
      body + (T.status === "received" && cfg.perms.receive ? '<div class="wms-foot"><span></span><button type="button" class="wms-btn success lg" data-act="complete"><i class="fas fa-flag-checkered" aria-hidden="true"></i> Transferni yakunlash</button></div>' : "") + "</div>";
  }
  function itemsTab() {
    var rows = T.items.map(function (i, n) {
      var d = i.received - i.dispatched;
      return "<tr><td class='num wms-muted'>" + (n + 1) + "</td><td><div class='wms-prod'>" + thumb(i.image_url) + "<span><b>" + esc(i.name) + "</b><small>" + esc(i.sku) + " · <code>" + esc(i.barcode || "—") + "</code></small></span></div></td>" +
        "<td>" + batchTag(i.batch, i.expiry) + allocText(i) + "</td><td>" + expiryTag(i.expiry) + "</td>" +
        '<td class="num">' + i.planned + '</td><td class="num">' + i.dispatched + '</td><td class="num">' + i.received + '</td><td class="num"><span class="wms-diff ' + (d === 0 ? "ok" : d < 0 ? "short" : "over") + '">' + (T.status === "cancelled" ? "—" : d === 0 ? "✓" : (d > 0 ? "+" : "") + d) + "</span></td>" +
        '<td class="num">' + money(i.unit_cost) + '</td><td class="num">' + money(Number(i.unit_cost) * (i.dispatched || i.planned)) + "</td></tr>";
    }).join("");
    return '<div class="wms-scroll"><table class="wms-table"><thead><tr><th class="num">№</th><th>Mahsulot</th><th>Partiya</th><th>Yaroqlilik</th><th class="num">Reja</th><th class="num">Jo\'natildi</th><th class="num">Qabul</th><th class="num">Farq</th><th class="num">Tannarx</th><th class="num">Summa</th></tr></thead><tbody>' + rows + "</tbody></table></div>";
  }
  function diffTab() {
    var list = T.items.filter(function (i) { return i.dispatched && i.received !== i.dispatched; });
    if (!list.length) return '<div class="wms-empty"><i class="fas fa-circle-check" aria-hidden="true" style="color:#16a34a;opacity:1"></i>Tafovut yo\'q — jo\'natilgan va qabul qilingan miqdorlar to\'liq mos.</div>';
    return '<div class="wms-scroll"><table class="wms-table"><thead><tr><th>Mahsulot</th><th>Partiya</th><th class="num">Jo\'natilgan</th><th class="num">Qabul</th><th class="num">Farq</th><th>Sabab</th><th>Qaror</th></tr></thead><tbody>' +
      list.map(function (i) {
        var d = i.received - i.dispatched;
        return "<tr><td><b>" + esc(i.name) + "</b></td><td>" + batchTag(i.batch, i.expiry) + allocText(i) + '</td><td class="num">' + i.dispatched + '</td><td class="num">' + i.received + '</td><td class="num"><span class="wms-diff ' + (d < 0 ? "short" : "over") + '">' + (d > 0 ? "+" : "") + d + "</span></td>" +
          "<td>" + esc((cfg.reasons.filter(function (x) { return x[0] === i.reason; })[0] || ["", "—"])[1]) + (i.note ? '<br><small class="wms-muted">' + esc(i.note) + "</small>" : "") + "</td><td>" + (i.resolution_label ? '<span class="wms-pill" style="--t:#64748b">' + esc(i.resolution_label) + "</span>" + (i.resolved_by ? '<br><small class="wms-muted">' + esc(i.resolved_by) + "</small>" : "") : "—") + "</td></tr>";
      }).join("") + "</tbody></table></div>";
  }
  function logTab() {
    var groups = { dispatch: [], receive: [], other: [] };
    T.events.forEach(function (e) {
      if (/^status:(ready|in_transit)|pick_mismatch|items|created|locations/.test(e.action)) groups.dispatch.push(e);
      else if (/^status:(receiving|partial|received)|discrepancy|resolved/.test(e.action)) groups.receive.push(e);
      else groups.other.push(e);
    });
    function list(title, items) { return items.length ? "<h4 class='wms-subhead'>" + esc(title) + "</h4><ul class='wms-log'>" + items.map(function (e) { return "<li><time>" + esc(e.at) + " · " + esc(e.actor || "tizim") + "</time>" + esc(e.message) + "</li>"; }).join("") + "</ul>" : ""; }
    return list("Jo'natish jurnali", groups.dispatch) + list("Qabul jurnali", groups.receive) + list("Boshqa", groups.other) || '<div class="wms-empty">Tarix bo\'sh.</div>';
  }
  function docsTab() {
    var final = ["partial", "received", "completed"].indexOf(T.status) !== -1;
    return '<div class="wms-docs"><a class="wms-doc-card" href="' + cfg.urls.xlsx + '"><i class="fas fa-file-excel" aria-hidden="true" style="color:#16a34a"></i><span><b>' + (final ? "Yakuniy nakladnoy (Excel)" : "Jo'natish nakladnoyi (Excel)") + "</b><small>" + esc(T.number) + ".xlsx · har bir partiya alohida qatorda" + (final ? ", jo'natilgan / qabul / farq" : "") + "</small></span></a>" +
      '<a class="wms-doc-card" href="' + cfg.urls.document + '" target="_blank" rel="noopener"><i class="fas fa-print" aria-hidden="true" style="color:var(--nz-primary)"></i><span><b>Chop etish / PDF</b><small>Imzo joylari bilan</small></span></a></div>';
  }

  // ---- side panel
  function side(m) {
    var s = T.summary;
    var units = s.dispatched || s.planned;
    return '<div class="wms-card wms-sum"><h3><i class="fas fa-file-lines" aria-hidden="true"></i> ' + esc(T.number) + "</h3><dl>" +
      "<dt>Holat</dt><dd><span class='wms-pill' style='--t:" + (TONE[T.status] || "#64748b") + "'>" + esc(T.status_label) + "</span></dd>" +
      "<dt>Qayerdan</dt><dd>" + esc(T.source.name) + "</dd><dt>Qayerga</dt><dd>" + esc(T.destination.name) + "</dd>" +
      "<dt>Mahsulot turlari</dt><dd>" + s.products + (s.batches > s.products ? " · " + s.batches + " partiya" : "") + "</dd><dt>Dona</dt><dd>" + units + (s.received ? " → " + s.received : "") + "</dd>" +
      "<dt>Qiymati (tannarx)</dt><dd>" + money(s.value) + " so'm</dd>" +
      "<dt>Yaratildi</dt><dd>" + esc(T.created_at) + "<br><small class='wms-muted'>" + esc(T.created_by || "—") + "</small></dd>" +
      (T.dispatched_at ? "<dt>Jo'natdi</dt><dd>" + esc(T.dispatched_at) + "<br><small class='wms-muted'>" + esc(T.dispatched_by) + "</small></dd>" : "") +
      (T.received_at ? "<dt>Qabul qildi</dt><dd>" + esc(T.received_at) + "<br><small class='wms-muted'>" + esc(T.received_by) + "</small></dd>" : "") +
      (T.notes ? "<dt>Izoh</dt><dd>" + esc(T.notes) + "</dd>" : "") + "</dl>" +
      '<div class="wms-actions"><a class="wms-btn" href="' + cfg.urls.xlsx + '"><i class="fas fa-file-excel" aria-hidden="true"></i> Excel nakladnoy</a><a class="wms-btn" href="' + cfg.urls.document + '" target="_blank" rel="noopener"><i class="fas fa-print" aria-hidden="true"></i> Chop etish</a><a class="wms-btn ghost" href="' + cfg.urls.list + '"><i class="fas fa-list" aria-hidden="true"></i> Barcha transferlar</a></div></div>' +
      (m === "done" ? "" : '<div class="wms-card"><h3><i class="fas fa-clock-rotate-left" aria-hidden="true"></i> Tarix (audit)</h3><ul class="wms-log">' +
      T.events.map(function (e) { return "<li><time>" + esc(e.at) + " · " + esc(e.actor || "tizim") + "</time>" + esc(e.message) + "</li>"; }).join("") + "</ul></div>") +
      (m === "done" || m === "received" || m === "approve" ? "" : '<div class="wms-card wms-help"><h3><i class="fas fa-keyboard" aria-hidden="true"></i> Skaner</h3><ul><li>Bitta skaner = <b>× soni</b> dona (quti uchun × ni oshiring)</li><li>Tasodifiy ikki marta skan — «Bekor qilish (−N)»</li><li>Skaner sahifaning istalgan joyida ishlaydi</li></ul></div>');
  }

  // ---------------------------------------------------------------- behaviour
  function focusScan() {
    var el = document.getElementById("wms-scan");
    var a = document.activeElement;
    if (el && modal.hidden && (!a || a === document.body || a.id === "wms-scan")) el.focus();
  }
  function setSaveState(t) { var el = document.getElementById("wms-savestate"); if (el) el.textContent = t; }
  function flash(ok) { var box = app.querySelector(".wms-scan"); if (box) { box.classList.remove("flash-ok", "flash-bad"); void box.offsetWidth; box.classList.add(ok ? "flash-ok" : "flash-bad"); } beep(ok); }
  function note(ok, title, text, undo) { S.last = { ok: ok, title: title, text: text, undo: undo || null }; flash(ok); }
  function multiplier() { var el = document.getElementById("wms-mult"); var n = parseInt(el ? el.value : S.mult, 10); S.mult = n > 0 && n < 1000 ? n : 1; return S.mult; }

  function scheduleSave(kind) {
    S.dirty = true;
    setSaveState("saqlanmoqda…");
    clearTimeout(saveTimer);
    saveTimer = setTimeout(function () { save(kind, true).catch(function () {}); }, 900);
  }
  function linesPayload() { return S.lines.map(function (l) { return { variant_id: l.variant_id, quantity: Number(l.qty) || 0, batch: l.batch || "", expiry: l.expiry || null }; }); }
  function reasonsPayload() {
    var out = {};
    Object.keys(S.reasons).forEach(function (k) { if (S.reasons[k].reason || S.reasons[k].note) out[k] = S.reasons[k]; });
    return out;
  }
  function saveKind() { var m = mode(); return m === "draft" ? "draft" : m === "pick" ? "pick" : "receive"; }
  function save(kind, quiet) {
    clearTimeout(saveTimer);
    var p;
    if (kind === "draft") p = api(actionUrl("save_draft"), { lines: linesPayload(), notes: (document.getElementById("wms-notes") || {}).value });
    else if (kind === "pick") p = api(actionUrl("pick"), { picked: S.pick });
    else p = api(actionUrl("receive_save"), { counts: S.recv, reasons: reasonsPayload() });
    S.saving = true;
    return p.then(function (data) {
      S.saving = false; S.dirty = false;
      var wasFailed = S.failed;
      S.failed = false; clearTimeout(retryTimer);
      if (kind === "receive" && T.status === "in_transit") { adopt(data); }
      else {
        T = data;
        if (kind === "draft") T.items.forEach(function (i) { S.lines.forEach(function (l) { if (l.key === lineKey(i.variant_id, i.batch, i.expiry)) { l.unit_cost = Number(i.unit_cost) || 0; l.cost_source = i.cost_source; } }); });
        if (wasFailed) render();
        else { var aside = app.querySelector(".wms-side"); if (aside) aside.innerHTML = side(mode()); }
      }
      setSaveState("✓ saqlandi");
      if (!quiet) toast("ok", "Saqlandi");
      return data;
    }).catch(function (e) {
      S.saving = false;
      setSaveState("");
      if (e.code === "NETWORK" || e.status >= 500) {
        S.failed = true;
        clearTimeout(retryTimer);
        retryTimer = setTimeout(function () { if (S.dirty) save(kind, true).catch(function () {}); }, 5000);
        if (!app.querySelector(".wms-banner.err")) render();
      } else {
        toast("err", explain(e));
        if (kind === "draft" && e.code === "INSUFFICIENT_STOCK") markShortages(e.details.shortages || []);
        if (e.code === "NOT_EDITABLE" || e.code === "NOT_READY" || e.code === "NOT_RECEIVABLE" || e.code === "INVALID_TRANSITION") { toast("info", "Transfer holati o'zgargan — yangilanmoqda"); load(); }
      }
      throw e;
    });
  }
  function markShortages(list) { list.forEach(function (s) { toast("err", s.name + ": so'ralgan " + s.requested + ", mavjud " + s.available); }); }

  // ---- scanning
  var lastCode = "", lastAt = 0;
  var unitCodes = {}; // DataMatrix ("Asl belgisi") codes carry a per-unit serial: the same unit must not count twice
  function onScan(raw) {
    // 2D scanners send GS1 DataMatrix with GS (\x1d) separators and an optional "]d2" prefix -- keep the printable part
    var code = (raw || "").replace(/[\u0000-\u001f\u007f]/g, "").trim();
    if (!code) return;
    var now = Date.now();
    if (code === lastCode && now - lastAt < 150) return; // one physical scan delivered twice (CR+LF / double trigger)
    lastCode = code; lastAt = now;
    if (code.length > 160) { note(false, "Noto'g'ri shtrix-kod", "skaner ma'lumoti buzilgan — qayta skanerlang"); render(); return; }
    var unit = /^(\]d2)?01\d{14}21/.test(code) && code.length > 24;
    if (unit && unitCodes[code]) { wrong("Takroriy skan", "bu dona (markirovka kodi) allaqachon skanerlangan — boshqa donani skanerlang"); return; }
    if (unit) unitCodes[code] = true;
    var m = mode(), n = multiplier();
    if (m === "draft") {
      api(cfg.urls.lookup + "?code=" + encodeURIComponent(code) + "&location=" + T.source.id).then(function (p) { offerLine(p, n); })
        .catch(function (e) { if (e.code === "NETWORK") { note(false, "Tarmoq yo'q", "skanerlash saqlanmadi"); render(); } else search(code, true); });
      return;
    }
    if (m === "pick" || m === "receive") {
      var local = T.items.filter(function (i) { return i.barcode === code || (i.sku || "").toLowerCase() === code.toLowerCase(); });
      if (local.length) { countScan(m, local, n, null); return; }
      api(cfg.urls.lookup + "?code=" + encodeURIComponent(code)).then(function (p) {
        var hits = T.items.filter(function (i) { return i.variant_id === p.variant_id; });
        if (!hits.length) { wrong("Noto'g'ri mahsulot", p.name + " — bu transferda yo'q (" + code + ")"); return; }
        countScan(m, hits, n, p);
      }).catch(function (e) {
        if (e.code === "NETWORK") { note(false, "Tarmoq yo'q", "qayta skanerlang"); render(); return; }
        wrong("Topilmadi", "shtrix-kod " + code + " hech bir mahsulotga tegishli emas");
      });
    }
  }
  function wrong(kind, text) {
    if (mode() === "receive") S.wrong.unshift({ kind: kind, text: text, at: new Date().toTimeString().slice(0, 5) });
    note(false, kind, text);
    toast("err", kind + ": " + text);
    render();
  }
  function countScan(m, candidates, n, match) {
    var bag = m === "pick" ? S.pick : S.recv;
    var limitOf = function (i) { return m === "pick" ? i.planned : i.dispatched; };
    var list = candidates.slice();
    if (match && match.batch) { // an extra batch barcode names its batch
      var same = list.filter(function (i) { return i.batch === match.batch; });
      if (!same.length && list.every(function (i) { return i.batch; })) { wrong("Noto'g'ri partiya", match.name + ": skanerlangan partiya " + match.batch + " bu transferda yo'q (kutilgan: " + list.map(function (i) { return i.batch; }).join(", ") + ")"); return; }
      if (same.length) list = same;
      if (same.length && match.expiry && same[0].expiry && match.expiry !== same[0].expiry) {
        S.wrong.unshift({ kind: "Muddat mos emas", text: match.name + " " + match.batch + ": yorliqda " + fmtDate(match.expiry) + ", hujjatda " + fmtDate(same[0].expiry), at: new Date().toTimeString().slice(0, 5) });
      }
    }
    list.sort(function (a, b) { return (a.expiry || "9999") < (b.expiry || "9999") ? -1 : (a.expiry || "9999") > (b.expiry || "9999") ? 1 : 0; });
    var item = list.filter(function (i) { return (bag[i.id] || 0) < limitOf(i); })[0];
    if (!item) {
      item = list[list.length - 1];
      if (m === "pick") { note(false, item.name, "rejadagi " + item.planned + " dona allaqachon skanerlangan"); toast("err", item.name + ": rejadan ko'p bo'lmaydi"); render(); return; }
    }
    var before = bag[item.id] || 0, next = before + n;
    if (m === "pick" && next > item.planned) { note(false, item.name, "rejada " + item.planned + ", skanerlansa " + next + " bo'ladi"); toast("err", item.name + ": rejadan ko'p bo'lmaydi"); render(); return; }
    bag[item.id] = next;
    var over = m === "receive" && next > item.dispatched;
    if (over) toast("err", item.name + ": jo'natilgandan ko'p (" + next + " / " + item.dispatched + ") — ortiqcha");
    note(!over, item.name + (item.batch ? " · " + item.batch : ""), "+" + n + " → " + next + " / " + limitOf(item) + (over ? " (ortiqcha)" : ""), { id: item.id, n: n, bag: m });
    render();
    highlight(item.id);
    scheduleSave(m === "pick" ? "pick" : "receive");
  }
  function undoLast() {
    var u = S.last && S.last.undo;
    if (!u) return;
    if (u.line) { var l = S.lines.filter(function (x) { return x.key === u.line; })[0]; if (l) { l.qty = Math.max(0, (Number(l.qty) || 0) - u.n); if (!l.qty) S.lines.splice(S.lines.indexOf(l), 1); } scheduleSave("draft"); }
    else {
      var bag = u.bag === "pick" ? S.pick : S.recv;
      var item = T.items.filter(function (i) { return i.id === u.id; })[0];
      bag[u.id] = Math.max(u.bag === "receive" && item ? item.posted : 0, (bag[u.id] || 0) - u.n);
      scheduleSave(u.bag === "pick" ? "pick" : "receive");
    }
    S.last = { ok: true, title: "Bekor qilindi", text: "oxirgi skan (−" + u.n + ")", undo: null };
    render();
  }
  function highlight(id) {
    var row = app.querySelector('tr[data-id="' + id + '"], .wms-rcard[data-id="' + id + '"], tr[data-key="' + id + '"]');
    if (row) { row.classList.add("flash"); row.scrollIntoView({ block: "nearest", behavior: "smooth" }); }
  }

  // ---- draft: product → batch → line
  function offerLine(p, n) {
    if (!p.active) { note(false, p.name, "faol emas — qo'shib bo'lmaydi"); render(); return; }
    if (p.available <= 0) { note(false, p.name, T.source.name + " da sotuvga ochiq qoldiq yo'q"); toast("err", p.name + " — qoldiq yo'q"); render(); return; }
    S.batches[p.variant_id] = p.batches || [];
    var usable = (p.batches || []).filter(function (b) { return !b.expired; });
    var named = (p.batches || []).filter(function (b) { return b.batch || b.expiry; });
    if (p.batch) { // an extra batch barcode: its batch, if the source has it
      var hit = (p.batches || []).filter(function (b) { return b.batch === p.batch; })[0];
      if (!hit) { note(false, p.name, "partiya " + p.batch + " " + T.source.name + " qoldig'ida yo'q"); render(); return; }
      if (hit.expired) { note(false, p.name, "partiya " + p.batch + " muddati o'tgan — jo'natib bo'lmaydi"); render(); return; }
      addLine(p, n, hit.batch, hit.expiry); return;
    }
    if (named.length <= 1 && usable.length <= 1) { var only = usable[0]; addLine(p, n, only ? only.batch : "", only ? only.expiry : ""); return; }
    S.choose = { product: p, batches: p.batches, n: n, fefo: p.batches.indexOf(usable[0]) };
    note(true, p.name, "partiyani tanlang");
    render();
  }
  function choose(index) {
    var c = S.choose;
    if (!c) return;
    S.choose = null;
    if (index === "auto") { addLine(c.product, c.n, "", ""); return; }
    var b = c.batches[index];
    if (!b || b.expired) { render(); return; }
    addLine(c.product, c.n, b.batch, b.expiry);
  }
  function addLine(p, qty, batch, expiry) {
    var key = lineKey(p.variant_id, batch, expiry);
    var line = S.lines.filter(function (l) { return l.key === key; })[0];
    var current = line ? Number(line.qty) || 0 : 0;
    var variantTotal = sum(S.lines.filter(function (l) { return l.variant_id === p.variant_id; }), function (l) { return l.qty; });
    var batchRow = (p.batches || []).filter(function (b) { return b.batch === batch && b.expiry === (expiry || ""); })[0];
    var limit = Math.min(p.available - (variantTotal - current), batch && batchRow ? batchRow.quantity : Infinity);
    if (current + qty > limit) {
      qty = limit - current;
      if (qty <= 0) { note(false, p.name, (batch ? "partiya " + batch + ": " : "") + "mavjud faqat " + limit + " dona"); toast("err", p.name + ": qoldiq yetmaydi"); render(); return; }
      toast("err", p.name + ": faqat " + qty + " dona qo'shildi (qoldiq chegarasi)");
    }
    if (line) line.qty = current + qty;
    else S.lines.unshift({ key: key, variant_id: p.variant_id, name: p.name, sku: p.sku, barcode: p.barcode, size: p.size, image_url: p.image_url, available: p.available, qty: qty, batch: batch || "", expiry: expiry || "", unit_cost: Number(p.cost) || 0, cost_source: p.cost_source || "" });
    note(true, p.name + (batch ? " · " + batch : ""), "+" + qty + " → " + (current + qty) + " dona", { line: key, n: qty });
    render();
    var row = app.querySelector('tr[data-i="' + S.lines.findIndex(function (l) { return l.key === key; }) + '"]');
    if (row) row.classList.add("flash");
    scheduleSave("draft");
  }

  function search(q, show) {
    var box = app.querySelector(".wms-results");
    if (!box) return;
    if (!q || q.length < 2) { box.hidden = true; return; }
    api(cfg.urls.search + "?location=" + T.source.id + "&q=" + encodeURIComponent(q)).then(function (rows) {
      S.results = rows; S.hl = rows.length ? 0 : -1;
      box.innerHTML = rows.length ? rows.map(function (r, i) {
        return '<div class="wms-result' + (i === 0 ? " hl" : "") + '" data-r="' + i + '" role="option">' + thumb(r.image_url) + "<span><b>" + esc(r.name) + "</b><br><small class='wms-muted'>" + esc(r.sku) + " · " + esc(r.barcode || "—") + (r.size ? " · " + esc(r.size) : "") + '</small></span><span class="av">' + r.available + " <small class='wms-muted'>mavjud</small></span></div>";
      }).join("") : '<div class="wms-empty" style="padding:18px">«' + esc(q) + "» " + esc(T.source.name) + " qoldig'ida topilmadi</div>";
      box.hidden = false;
      if (show && !rows.length) { note(false, "Topilmadi", "«" + q + "» — na shtrix-kod, na nom bo'yicha"); flash(false); }
    }).catch(function () { box.hidden = true; });
  }
  function pickResult(r) {
    // a search hit carries no batches: look it up by its barcode / SKU to get them
    api(cfg.urls.lookup + "?code=" + encodeURIComponent(r.barcode || r.sku) + "&location=" + T.source.id).then(function (p) { offerLine(p, multiplier()); })
      .catch(function () { offerLine({ variant_id: r.variant_id, name: r.name, sku: r.sku, barcode: r.barcode, size: r.size, image_url: r.image_url, available: r.available, active: r.active, batches: [], cost: r.cost, cost_source: r.cost_source }, multiplier()); });
  }

  function bind(m) {
    var scan = document.getElementById("wms-scan");
    if (scan) {
      scan.addEventListener("keydown", function (e) {
        var box = app.querySelector(".wms-results");
        if (m === "draft" && box && !box.hidden && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
          e.preventDefault();
          S.hl = Math.max(0, Math.min(S.results.length - 1, S.hl + (e.key === "ArrowDown" ? 1 : -1)));
          box.querySelectorAll(".wms-result").forEach(function (el, i) { el.classList.toggle("hl", i === S.hl); });
          return;
        }
        if (e.key === "Enter") {
          e.preventDefault();
          if (m === "draft" && box && !box.hidden && S.hl >= 0 && S.results[S.hl] && scan.value.trim() && !/^\d{6,}$/.test(scan.value.trim())) { var r = S.results[S.hl]; scan.value = ""; box.hidden = true; pickResult(r); return; }
          clearTimeout(searchTimer); if (box) box.hidden = true;
          var v = scan.value; scan.value = ""; onScan(v);
        }
        if (e.key === "Escape") { if (box) box.hidden = true; if (S.choose) { S.choose = null; render(); } }
        if (S.choose && /^[0-9]$/.test(e.key) && !scan.value) { e.preventDefault(); choose(e.key === "0" ? "auto" : +e.key - 1); }
      });
      if (m === "draft") scan.addEventListener("input", function () { clearTimeout(searchTimer); var v = scan.value; searchTimer = setTimeout(function () { if (!/^\d{8,}$/.test(v.trim())) search(v); }, 260); });
      var results = app.querySelector(".wms-results");
      if (results) results.addEventListener("click", function (e) { var r = e.target.closest("[data-r]"); if (r) { results.hidden = true; scan.value = ""; pickResult(S.results[+r.getAttribute("data-r")]); } });
    }
    var mult = document.getElementById("wms-mult");
    if (mult) mult.addEventListener("change", function () { multiplier(); mult.value = S.mult; });
    app.querySelectorAll("[data-pick]").forEach(function (b) { b.onclick = function () { var v = b.getAttribute("data-pick"); choose(v === "auto" ? "auto" : +v); }; });

    // draft rows
    app.querySelectorAll("[data-i]").forEach(function (row) {
      var i = +row.getAttribute("data-i"), l = S.lines[i];
      var limit = function () { var bq = batchQty(l); return bq != null ? Math.min(bq, l.available) : l.available; };
      row.querySelector("[data-dec]").onclick = function () { l.qty = Math.max(1, (Number(l.qty) || 0) - 1); render(); scheduleSave("draft"); };
      row.querySelector("[data-inc]").onclick = function () { if ((Number(l.qty) || 0) >= limit()) { toast("err", "Mavjud faqat " + limit()); return; } l.qty = (Number(l.qty) || 0) + 1; render(); scheduleSave("draft"); };
      row.querySelector("[data-qty]").onchange = function (e) { l.qty = Math.max(1, parseInt(e.target.value, 10) || 1); render(); scheduleSave("draft"); };
      var sel = row.querySelector("[data-batchsel]");
      if (sel) sel.onchange = function (e) {
        var parts = e.target.value.split("|"), key = lineKey(l.variant_id, parts[0], parts[1]);
        var twin = S.lines.filter(function (x) { return x.key === key && x !== l; })[0];
        if (twin) { twin.qty = (Number(twin.qty) || 0) + (Number(l.qty) || 0); S.lines.splice(i, 1); toast("info", "Bir xil partiya qatorlari birlashtirildi"); }
        else { l.batch = parts[0]; l.expiry = parts[1] || ""; l.key = key; }
        render(); scheduleSave("draft");
      };
      row.querySelector("[data-rm]").onclick = function () { S.lines.splice(i, 1); render(); scheduleSave("draft"); };
    });
    // pick / receive rows
    app.querySelectorAll("[data-id]").forEach(function (row) {
      var id = row.getAttribute("data-id");
      var bag = m === "pick" ? S.pick : m === "receive" ? S.recv : null;
      if (!bag) return;
      var item = T.items.filter(function (x) { return x.id === id; })[0];
      var dec = row.querySelector("[data-dec]"), inc = row.querySelector("[data-inc]"), cnt = row.querySelector("[data-cnt]");
      if (dec) dec.onclick = function () { bag[id] = Math.max(m === "receive" ? item.posted : 0, (bag[id] || 0) - 1); render(); scheduleSave(m === "pick" ? "pick" : "receive"); };
      if (inc) inc.onclick = function () { if (m === "pick" && (bag[id] || 0) >= item.planned) return; bag[id] = (bag[id] || 0) + 1; render(); scheduleSave(m === "pick" ? "pick" : "receive"); };
      if (cnt) cnt.onchange = function (e) { var v = Math.max(m === "receive" ? item.posted : 0, parseInt(e.target.value, 10) || 0); if (m === "pick") v = Math.min(v, item.planned); bag[id] = v; render(); scheduleSave(m === "pick" ? "pick" : "receive"); };
      var reason = row.querySelector("[data-reason]"), noteEl = row.querySelector("[data-note]");
      if (reason) reason.onchange = function (e) { S.reasons[id] = S.reasons[id] || {}; S.reasons[id].reason = e.target.value; scheduleSave("receive"); };
      if (noteEl) noteEl.onchange = function (e) { S.reasons[id] = S.reasons[id] || {}; S.reasons[id].note = e.target.value; scheduleSave("receive"); };
    });
    app.querySelectorAll('input[type="radio"][name^="res-"]').forEach(function (r) { r.onchange = function () { S.resolutions[r.name.slice(4)] = r.value; }; });
    app.querySelectorAll("[data-tab]").forEach(function (b) { b.onclick = function () { S.tab = b.getAttribute("data-tab"); render(); }; });

    var src = document.getElementById("wms-src"), dst = document.getElementById("wms-dst");
    if (src && dst) {
      var change = function () {
        if (src.value === dst.value) { toast("err", ERR.SAME_LOCATION); render(); return; }
        var drop = S.lines.length ? dialog({ title: "Yo'nalishni o'zgartirish", html: "<p>Mahsulotlar ro'yxati tozalanadi — ular yangi manba qoldig'idan qayta qo'shiladi.</p>", ok: "O'zgartirish" }) : Promise.resolve(true);
        drop.then(function (ok) {
          if (!ok) { render(); return; }
          api(actionUrl("save_draft"), { lines: [], notes: (document.getElementById("wms-notes") || {}).value, source: src.value, destination: dst.value })
            .then(function (data) { toast("info", "Yo'nalish o'zgardi"); S.batches = {}; adopt(data); })
            .catch(function (e) { toast("err", explain(e)); render(); });
        });
      };
      src.onchange = change; dst.onchange = change;
    }
    var notes = document.getElementById("wms-notes");
    if (notes) notes.onchange = function () { scheduleSave("draft"); };

    app.querySelectorAll("[data-act]").forEach(function (b) { b.onclick = function () { act(b.getAttribute("data-act"), b); }; });
  }

  function busy(btn, on) { if (btn) { btn.disabled = on; if (on) { btn.dataset.html = btn.innerHTML; btn.innerHTML = '<i class="fas fa-circle-notch fa-spin" aria-hidden="true"></i> ' + btn.textContent.trim(); } else if (btn.dataset.html) btn.innerHTML = btn.dataset.html; } }
  function run(btn, promise, okText) {
    busy(btn, true);
    return promise.then(function (data) { toast("ok", okText); S.last = null; S.wrong = []; adopt(data); }).catch(function (e) {
      busy(btn, false);
      if (e.code === "INSUFFICIENT_STOCK" && e.details.shortages) markShortages(e.details.shortages); else toast("err", explain(e));
      throw e;
    });
  }
  function reviewTable(rows, cols) {
    return '<div class="wms-review"><table class="wms-table"><thead><tr>' + cols.map(function (c) { return "<th" + (c[1] ? ' class="num"' : "") + ">" + esc(c[0]) + "</th>"; }).join("") + "</tr></thead><tbody>" + rows.join("") + "</tbody></table></div>";
  }

  function act(name, btn) {
    if (name === "save") return save("draft").catch(function () {});
    if (name === "rsave") return save("receive").catch(function () {});
    if (name === "retry") return save(saveKind()).catch(function () {});
    if (name === "undo") return undoLast();
    if (name === "fill") {
      return dialog({ title: "Skanersiz tasdiqlash", html: "<p>Barcha qatorlar rejadagidek yig'ildi deb belgilanadi. Buni faqat mahsulotlarni qo'lda sanab chiqqan bo'lsangiz qiling.</p>", ok: "Belgilash" })
        .then(function (ok) { if (ok) { T.items.forEach(function (i) { S.pick[i.id] = i.planned; }); render(); scheduleSave("pick"); } });
    }
    if (name === "ready") {
      if (!S.lines.length) return toast("err", ERR.EMPTY_TRANSFER);
      var bad = S.lines.filter(function (l) { var bq = batchQty(l); return (Number(l.qty) || 0) > (bq != null ? bq : l.available); });
      if (bad.length) return toast("err", "Qoldiqdan ko'p: " + bad.map(function (l) { return l.name; }).join(", "));
      var value = sum(S.lines, function (l) { return l.unit_cost * (Number(l.qty) || 0); });
      var rows = S.lines.map(function (l, n) { return "<tr><td class='num'>" + (n + 1) + "</td><td>" + esc(l.name) + "</td><td>" + esc(batchName(l)) + "</td><td>" + esc(fmtDate(l.expiry) || "—") + "</td><td class='num'>" + l.qty + "</td><td class='num'>" + money(l.unit_cost * l.qty) + "</td></tr>"; });
      return dialog({
        title: "Ko'rib chiqish va band qilish",
        html: "<p><b>" + esc(T.number) + "</b>: " + esc(T.source.name) + " → " + esc(T.destination.name) + "</p>" + reviewTable(rows, [["№", 1], ["Mahsulot"], ["Partiya"], ["Muddat"], ["Soni", 1], ["Summa", 1]]) +
          "<p class='wms-muted'>" + S.lines.length + " qator, jami " + sum(S.lines, function (l) { return l.qty; }) + " dona, " + money(value) + " so'm (tannarx). Mahsulotlar " + esc(T.source.name) + " qoldig'ida band qilinadi — sotuvdan chiqadi.</p>",
        ok: "Band qilish",
      }).then(function (ok) { if (ok) return run(btn, api(actionUrl("ready"), { lines: linesPayload(), notes: (document.getElementById("wms-notes") || {}).value }), "Band qilindi. Endi yig'ib skanerlang.").catch(function () {}); });
    }
    if (name === "back") return dialog({ title: "Qoralamaga qaytarish", html: "<p>Bandlik bekor qilinadi, mahsulotlar yana sotuvga qaytadi.</p>", ok: "Qaytarish" }).then(function (ok) { if (ok) return run(btn, api(actionUrl("back_to_draft"), {}), "Qoralamaga qaytarildi").catch(function () {}); });
    if (name === "cancel") return dialog({ title: "Transferni bekor qilish", html: "<p>Bu amalni ortga qaytarib bo'lmaydi.</p><input class='wms-input' style='width:100%' placeholder='Sabab' aria-label='Sabab'>", ok: "Bekor qilish", danger: true })
      .then(function (reason) { if (reason !== null) return run(btn, api(actionUrl("cancel"), { reason: reason || "" }), "Transfer bekor qilindi").catch(function () {}); });
    if (name === "dispatch") {
      var mism = T.items.filter(function (i) { return (S.pick[i.id] || 0) !== i.planned; });
      var total = sum(T.items, function (i) { return S.pick[i.id] || 0; });
      if (!total) return toast("err", "Avval mahsulotlarni skanerlang.");
      var val = sum(T.items, function (i) { return (S.pick[i.id] || 0) * Number(i.unit_cost); });
      var rowsD = T.items.map(function (i) { var p = S.pick[i.id] || 0; return "<tr" + (p !== i.planned ? " class='is-over'" : "") + "><td>" + esc(i.name) + "</td><td>" + esc(batchName(i)) + "</td><td class='num'>" + i.planned + "</td><td class='num'><b>" + p + "</b></td></tr>"; });
      var html = "<dl class='wms-confirm'><dt>Hujjat</dt><dd>" + esc(T.number) + "</dd><dt>Jo'natuvchi</dt><dd>" + esc(T.source.name) + "</dd><dt>Qabul qiluvchi</dt><dd>" + esc(T.destination.name) + "</dd><dt>Qatorlar</dt><dd>" + T.items.length + "</dd><dt>Jami dona</dt><dd>" + total + "</dd><dt>Qiymati</dt><dd>" + money(val) + " so'm</dd></dl>" +
        reviewTable(rowsD, [["Mahsulot"], ["Partiya"], ["Reja", 1], ["Jo'natiladi", 1]]) +
        (mism.length ? "<div class='wms-banner warn'><i class='fas fa-triangle-exclamation' aria-hidden='true'></i><div><b>Rejadan farq bor.</b> Faqat skanerlangan miqdor jo'natiladi, farq jurnalga yoziladi.</div></div>" : "<p class='wms-muted'>Jo'natilgandan keyin ro'yxatni o'zgartirib bo'lmaydi.</p>");
      return dialog({ title: mism.length ? "Farq bilan jo'natish" : "Transferni jo'natish", html: html, ok: mism.length ? "Baribir jo'natish" : "Jo'natish" })
        .then(function (ok) { if (ok) return run(btn, api(actionUrl("dispatch"), { picked: S.pick, confirm: mism.length > 0 }), "Jo'natildi — transfer yo'lda").catch(function () {}); });
    }
    if (name === "rpartial" || name === "rfinal") {
      var final = name === "rfinal";
      var diffs = T.items.filter(function (i) { return (S.recv[i.id] || 0) !== i.dispatched; });
      if (final) {
        var missing = diffs.filter(function (i) { return !(S.reasons[i.id] || {}).reason; });
        if (missing.length) { toast("err", ERR.DISCREPANCY_REASON_REQUIRED + " (" + missing.map(function (i) { return i.name; }).join(", ") + ")"); return; }
      }
      var got = sum(T.items, function (i) { return S.recv[i.id] || 0; }), exp = sum(T.items, function (i) { return i.dispatched; });
      var rowsR = T.items.map(function (i) { var r = S.recv[i.id] || 0, d = r - i.dispatched; return "<tr" + (d ? " class='is-over'" : "") + "><td>" + esc(i.name) + "</td><td>" + esc(batchName(i)) + "</td><td class='num'>" + i.dispatched + "</td><td class='num'><b>" + r + "</b></td><td class='num'><span class='wms-diff " + (d === 0 ? "ok" : d < 0 ? "short" : "over") + "'>" + (d > 0 ? "+" : "") + d + "</span></td></tr>"; });
      return dialog({
        title: final ? "Qabulni tasdiqlash" : "Qisman qabul",
        html: "<p>Jo'natilgan <b>" + exp + "</b>, qabul qilingan <b>" + got + "</b> dona. Sanalgan mahsulotlar <b>" + esc(T.destination.name) + "</b> omboriga kiritiladi.</p>" + reviewTable(rowsR, [["Mahsulot"], ["Partiya"], ["Jo'natilgan", 1], ["Qabul", 1], ["Farq", 1]]) +
          (final && diffs.length ? "<div class='wms-banner warn'><i class='fas fa-scale-unbalanced' aria-hidden='true'></i><div>Tafovut bor — transfer menejer tasdig'iga o'tadi.</div></div>" : "") + (!final ? "<p class='wms-muted'>Qolgan qutilar kelganda qabulni davom ettirasiz.</p>" : ""),
        ok: final ? "Tasdiqlash" : "Qisman qabul qilish",
      }).then(function (ok) { if (ok) return run(btn, api(actionUrl(final ? "receive_final" : "receive_partial"), { counts: S.recv, reasons: reasonsPayload() }), final ? "Qabul tasdiqlandi" : "Qisman qabul qilindi").catch(function () {}); });
    }
    if (name === "approve") {
      var need = T.items.filter(function (i) { return i.received !== i.dispatched && !S.resolutions[i.id]; });
      if (need.length) return toast("err", ERR.RESOLUTION_REQUIRED);
      return dialog({ title: "Tafovutni tasdiqlash", html: "<p>Qarorlar qoldiqlarga qo'llanadi va audit tarixiga yoziladi.</p>", ok: "Tasdiqlash" })
        .then(function (ok) { if (ok) return run(btn, api(actionUrl("approve"), { resolutions: S.resolutions }), "Tafovut tasdiqlandi").catch(function () {}); });
    }
    if (name === "complete") return dialog({ title: "Transferni yakunlash", html: "<p>Yakunlangan transferni o'zgartirib bo'lmaydi.</p>", ok: "Yakunlash" }).then(function (ok) { if (ok) return run(btn, api(actionUrl("complete"), {}), "Transfer yakunlandi").catch(function () {}); });
  }

  // keyboard-wedge scanner anywhere on the page (focus outside inputs): fast keystrokes ending in Enter
  var buf = "", last = 0;
  document.addEventListener("keydown", function (e) {
    if (!modal.hidden) return;
    var tag = (e.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return;
    if (S.choose && /^[0-9]$/.test(e.key) && Date.now() - last > 60) { choose(e.key === "0" ? "auto" : +e.key - 1); return; }
    var now = Date.now();
    if (e.key === "Enter" && buf.length >= 4 && now - last < 120) { e.preventDefault(); var code = buf; buf = ""; onScan(code); return; }
    if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) { buf = now - last < 60 ? buf + e.key : e.key; last = now; }
  });
  window.addEventListener("beforeunload", function (e) { if (S.dirty) { e.preventDefault(); e.returnValue = ""; } });
  window.addEventListener("online", function () { if (S.dirty) save(saveKind(), true).catch(function () {}); });

  function signature(t) { return t.status + "|" + t.updated_at + "|" + t.items.map(function (i) { return i.id + ":" + i.picked + ":" + i.received + ":" + i.posted; }).join(","); }

  // another operator may work on the same transfer: pick up their changes while we have nothing unsaved
  setInterval(function () {
    if (!T || document.hidden || S.dirty || S.saving || !modal.hidden || S.choose) return;
    var a = document.activeElement;
    if (a && a.id !== "wms-scan" && /INPUT|SELECT|TEXTAREA/.test(a.tagName)) return;
    api(cfg.urls.data).then(function (data) {
      if (!data || signature(data) === signature(T) || S.dirty) return;
      if (data.status !== T.status) toast("info", "Transfer holati o'zgardi: " + data.status_label + (data.events[0] ? " (" + data.events[0].actor + ")" : ""));
      adopt(data);
    }).catch(function () { /* the next tick tries again */ });
  }, 20000);

  load();
})();
