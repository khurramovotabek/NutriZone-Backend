/*
 * NutriZone WMS -- goods receipt (Kirim), templates/admin/wms/receipt_new.html.
 * Goods arriving at a location are scanned with a 2D scanner (every scan adds exactly 1 -- the stepper or typed
 * quantity handles cases), searched by name, or imported from the Excel template. Each line carries its purchase
 * cost (pre-filled from the latest receipt, else the catalog cost price), batch and expiry; the page shows the
 * selling price, margin and expected gross profit live, and warns about lines without a cost, sold at a loss or
 * expiring soon. Everything is posted in one transaction. The unsent list survives a reload (this browser only).
 */
(function () {
  "use strict";

  var cfg = JSON.parse(document.getElementById("wms-config").textContent);
  var root = document.getElementById("wms-receipt");
  var modal = document.getElementById("wms-modal");
  var KEY = "nz_wms_receipt_draft";
  var S = restore() || { location: cfg.default_location, supplier: "", invoice: "", note: "", lines: [] };
  delete S.pre; // the old "qty per scan" multiplier is gone: one scan = one unit
  var results = [], hl = -1, searchTimer = null, busy = false;
  var SOURCE = { receipt: "oxirgi kirim", catalog: "katalog", price: "", "": "" };
  var today = new Date(); today.setHours(0, 0, 0, 0);

  // ---------------------------------------------------------------- helpers
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function num(v) { var n = Number(String(v == null ? "" : v).replace(/\s/g, "").replace(",", ".")); return isFinite(n) ? n : 0; }
  function money(n) { return Math.round(Number(n) || 0).toLocaleString("ru-RU").replace(/ /g, " "); }
  function csrf() { var el = document.querySelector("[name=csrfmiddlewaretoken]"); if (el) return el.value; var m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/); return m ? decodeURIComponent(m[1]) : ""; }
  function persist() { try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) { /* storage blocked */ } }
  function restore() { try { var v = JSON.parse(localStorage.getItem(KEY) || "null"); return v && Array.isArray(v.lines) ? v : null; } catch (e) { return null; } }
  function toast(kind, text) {
    var box = document.getElementById("wms-toasts"), el = document.createElement("div");
    el.className = "wms-toast " + kind;
    el.innerHTML = '<i class="fas ' + (kind === "ok" ? "fa-circle-check" : kind === "err" ? "fa-circle-exclamation" : "fa-circle-info") + '" aria-hidden="true"></i><span>' + esc(text) + "</span>";
    box.appendChild(el);
    setTimeout(function () { el.remove(); }, kind === "err" ? 6000 : 3000);
  }
  function beep(ok) {
    try {
      var ctx = beep.ctx || (beep.ctx = new (window.AudioContext || window.webkitAudioContext)());
      var o = ctx.createOscillator(), g = ctx.createGain();
      o.frequency.value = ok ? 1250 : 240; g.gain.value = 0.06; o.connect(g); g.connect(ctx.destination); o.start(); o.stop(ctx.currentTime + (ok ? 0.08 : 0.25));
    } catch (e) { /* no audio */ }
  }
  function getJSON(url) { return fetch(url, { credentials: "same-origin" }).then(function (r) { return r.json().then(function (j) { if (!r.ok || j.ok === false) throw new Error((j.error && j.error.message) || "Xato"); return j.data; }); }); }
  function thumb(url) { return url ? '<img class="nzf-img" src="' + esc(url) + '" alt="">' : '<span class="nzf-img ph"><i class="fas fa-box" aria-hidden="true"></i></span>'; }
  function dialog(title, html, ok) {
    return new Promise(function (resolve) {
      var d = modal.querySelector(".wms-dialog");
      d.innerHTML = "<h4>" + esc(title) + "</h4>" + html + '<div class="row-actions"><button type="button" class="wms-btn" data-x="0">Bekor qilish</button><button type="button" class="wms-btn primary" data-x="1">' + esc(ok) + "</button></div>";
      modal.hidden = false;
      d.querySelector('[data-x="1"]').focus();
      d.onclick = function (e) { var b = e.target.closest("[data-x]"); if (b) { modal.hidden = true; resolve(b.getAttribute("data-x") === "1"); } };
    });
  }

  function location() { return cfg.locations.filter(function (l) { return l.id === S.location; })[0]; }
  function supplier() { return (cfg.suppliers || []).filter(function (s) { return s.name.toLowerCase() === (S.supplier || "").trim().toLowerCase(); })[0]; }
  function daysLeft(iso) { if (!iso) return null; var d = new Date(iso + "T00:00:00"); return isNaN(d) ? null : Math.round((d - today) / 864e5); }
  // Yorliqdagi muddat: "03/2027", "03.27", "2027-03" -> oy oxiri; "15.03.2027", "15/03/27", ISO -> o'sha kun.
  // Server (stock_service._parse_date) aynan shu qoidalar bilan o'qiydi.
  function lastDay(y, m) { return new Date(y, m, 0).getDate(); }
  function iso(y, m, d) {
    if (m < 1 || m > 12 || d < 1 || d > lastDay(y, m)) return null;
    return y + "-" + String(m).padStart(2, "0") + "-" + String(d).padStart(2, "0");
  }
  function parseExpiry(raw) {
    var t = String(raw || "").trim().toUpperCase().replace(/^EXP[\s:.]*/, "").replace(/\s+/g, "");
    if (!t) return "";
    var m;
    if ((m = t.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/))) return iso(+m[1], +m[2], +m[3]);
    if ((m = t.match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{4}|\d{2})$/))) return iso(+m[3] < 100 ? 2000 + +m[3] : +m[3], +m[2], +m[1]);
    if ((m = t.match(/^(\d{4})[./-](\d{1,2})$/))) return iso(+m[1], +m[2], lastDay(+m[1], +m[2]));
    if ((m = t.match(/^(\d{1,2})[./-](\d{4}|\d{2})$/))) { var y = +m[2] < 100 ? 2000 + +m[2] : +m[2]; return iso(y, +m[1], lastDay(y, +m[1])); }
    if ((m = t.match(/^(\d{2})(\d{2})(\d{4})$/))) return iso(+m[3], +m[2], +m[1]);   // 15032027
    if ((m = t.match(/^(\d{2})(\d{4})$/))) return iso(+m[2], +m[1], lastDay(+m[2], +m[1])); // 032027
    return null;
  }
  // server bilan bir xil chegaralar: 2 yildan eski yoki 15 yildan uzoq sana — xato yozilgan yil
  function expiryProblem(isoDate) {
    var d = daysLeft(isoDate);
    if (d === null) return "";
    if (d < -730 || new Date(isoDate).getFullYear() > today.getFullYear() + 15) return "Yilni tekshiring";
    return "";
  }
  function showDate(isoDate) { var p = (isoDate || "").split("-"); return p.length === 3 ? p[2] + "." + p[1] + "." + p[0] : ""; }

  function margin(l) { var c = num(l.unit_cost), p = num(l.price); return c > 0 && p > 0 ? Math.round((p - c) * 1000 / p) / 10 : null; }

  function totals() {
    return S.lines.reduce(function (t, l) {
      var q = num(l.quantity), c = num(l.unit_cost), p = num(l.price), m = margin(l), d = daysLeft(l.expiry);
      t.units += q; t.value += q * c;
      if (c > 0 && p > 0) { t.revenue += q * p; t.costed += q * c; }
      if (!(c > 0)) t.nocost += 1;
      if (m !== null && m < 0) t.loss += 1;
      if (d !== null && d <= 90) t.expiring += 1;
      return t;
    }, { units: 0, value: 0, revenue: 0, costed: 0, nocost: 0, loss: 0, expiring: 0 });
  }

  // ---------------------------------------------------------------- render
  function marginChip(l) {
    var m = margin(l);
    if (m === null) return num(l.price) > 0 ? '<span class="nzf-chip mute">tannarx yo\'q</span>' : '<span class="nzf-chip mute">narx yo\'q</span>';
    var tone = m < 0 ? "bad" : m < 15 ? "warn" : "ok";
    return '<span class="nzf-chip ' + tone + '">' + (m < 0 ? "zarar " : "") + m + "%</span>";
  }
  function expiryChip(l) {
    if (l.expiry_bad) return '<span class="nzf-chip bad">sana noto\'g\'ri</span>';
    var problem = expiryProblem(l.expiry);
    if (problem) return '<span class="nzf-chip bad">' + problem + "</span>";
    var d = daysLeft(l.expiry);
    if (d === null) return "";
    if (d < 0) return '<span class="nzf-chip bad">muddati o\'tgan</span>';
    if (d <= 90) return '<span class="nzf-chip warn">' + d + " kun qoldi</span>";
    return "";
  }

  function lineRow(l, i) {
    var src = SOURCE[l.cost_source || ""] || "";
    var costHint = l.cost_origin === "typed" ? "" : src && num(l.unit_cost) > 0 ? '<small class="nzf-src">' + src + "</small>" : "";
    return '<tr data-i="' + i + '"><td><div class="nzf-prod">' + thumb(l.image_url) + "<span><b>" + esc(l.name) + "</b><small>" + esc(l.sku) + (l.size ? " · " + esc(l.size) : "") + (l.barcode ? ' · <code>' + esc(l.barcode) + "</code>" : "") + "</small></span></div></td>" +
      '<td><div class="nzf-stepper"><button type="button" data-dec aria-label="Kamaytirish">−</button><input data-q inputmode="numeric" value="' + esc(l.quantity) + '" aria-label="Soni"><button type="button" data-inc aria-label="Ko\'paytirish">+</button></div></td>' +
      '<td><div class="nzf-cost' + (num(l.unit_cost) > 0 ? "" : " empty") + '"><input data-c inputmode="decimal" value="' + esc(l.unit_cost ? money(l.unit_cost) : "") + '" placeholder="tannarx" aria-label="Tannarx">' + costHint + "</div></td>" +
      '<td class="num">' + (num(l.price) > 0 ? money(l.price) : "—") + "<div>" + marginChip(l) + "</div></td>" +
      '<td><div class="nzf-batch"><input class="nzf-in" data-b value="' + esc(l.batch || "") + '" placeholder="LOT-…" aria-label="Partiya"><input class="nzf-in nzf-exp' + (l.expiry_bad || expiryProblem(l.expiry) ? " bad" : "") + '" data-e inputmode="numeric" autocomplete="off" value="' + esc(l.expiry_bad || showDate(l.expiry)) + '" placeholder="03/2027" title="Muddat: 03/2027 (oy oxiri), 15.03.2027 yoki 2027-03-15" aria-label="Yaroqlilik muddati"></div><span data-chip>' + expiryChip(l) + "</span></td>" +
      '<td class="num"><b>' + (num(l.unit_cost) > 0 ? money(num(l.unit_cost) * num(l.quantity)) : "—") + "</b></td>" +
      '<td><button type="button" class="nzf-x" data-rm aria-label="O\'chirish"><i class="fas fa-xmark" aria-hidden="true"></i></button></td></tr>';
  }

  // which field had focus (row + field), so a re-render after a change keeps the cursor where the user tabbed to
  function focusKey() {
    var a = document.activeElement, row = a && a.closest && a.closest("tr[data-i]");
    if (!a || !root.contains(a)) return null;
    if (a.id) return "#" + a.id;
    if (!row) return null;
    var attr = ["data-q", "data-c", "data-b", "data-e"].filter(function (n) { return a.hasAttribute(n); })[0];
    return attr ? 'tr[data-i="' + row.getAttribute("data-i") + '"] [' + attr + "]" : null;
  }

  function render() {
    var keep = focusKey();
    var loc = location(), t = totals(), sup = supplier();
    var profit = t.revenue - t.costed, pm = t.revenue ? Math.round(profit * 1000 / t.revenue) / 10 : null;
    root.innerHTML =
      '<div class="nzf-grid"><div class="nzf-main">' +
      // document header
      '<section class="nzp-card nzf-doc"><div class="nzf-fields">' +
      '<label class="nzf-field"><span>Qabul qiluvchi joy</span><select id="r-loc">' + cfg.locations.map(function (l) { return '<option value="' + l.id + '"' + (l.id === S.location ? " selected" : "") + ">" + esc(l.name) + (l.kind === "warehouse" ? " — sklad" : " — filial") + "</option>"; }).join("") + "</select></label>" +
      '<label class="nzf-field"><span>Yetkazib beruvchi</span><input id="r-sup" list="r-sup-list" autocomplete="off" value="' + esc(S.supplier) + '" placeholder="Tanlang yoki yangi nom yozing"><datalist id="r-sup-list">' +
        (cfg.suppliers || []).map(function (s) { return '<option value="' + esc(s.name) + '">' + (s.terms ? s.terms + " kun to'lov muddati" : "") + "</option>"; }).join("") + "</datalist>" +
        '<small class="nzf-hint">' + (sup ? '<i class="fas fa-circle-check ok" aria-hidden="true"></i> ' + (sup.terms ? sup.terms + " kun to'lov muddati — qarz avtomatik yoziladi" : "ro'yxatdagi yetkazib beruvchi") : S.supplier ? '<i class="fas fa-circle-plus" aria-hidden="true"></i> yangi yetkazib beruvchi sifatida qo\'shiladi' : "ixtiyoriy — qarzni kuzatish uchun tavsiya etiladi") + "</small></label>" +
      '<label class="nzf-field"><span>Hisob-faktura №</span><input id="r-inv" value="' + esc(S.invoice) + '" placeholder="INV-2026-0931"></label>' +
      '<label class="nzf-field"><span>Izoh</span><input id="r-note" value="' + esc(S.note) + '" placeholder="ixtiyoriy"></label></div></section>' +
      // scanner
      '<section class="nzp-card nzf-scanbox"><div class="nzf-scan"><i class="fas fa-barcode" aria-hidden="true"></i><input id="r-scan" autocomplete="off" placeholder="Shtrix-kodni skanerlang yoki mahsulot nomini yozing…" aria-label="Shtrix-kod yoki nom">' +
      '<span class="nzf-kbd">+1 har skaner</span><div class="nzf-results" hidden></div></div>' +
      '<div class="nzf-tools"><label class="nzp-btn nzp-btn-ghost nzp-btn-sm"><i class="fas fa-file-arrow-up" aria-hidden="true"></i> Excel\'dan yuklash<input type="file" id="r-file" accept=".xlsx" hidden></label>' +
      '<a class="nzp-btn nzp-btn-ghost nzp-btn-sm" href="' + cfg.urls.template + '"><i class="fas fa-file-excel" aria-hidden="true"></i> Shablon (barcha mahsulotlar)</a>' +
      (t.nocost && S.lines.length ? '<button type="button" class="nzp-btn nzp-btn-ghost nzp-btn-sm" id="r-fillcost"><i class="fas fa-coins" aria-hidden="true"></i> Tannarxsiz qatorlarga narx berish</button>' : "") +
      (S.lines.length ? '<button type="button" class="nzp-btn nzp-btn-ghost nzp-btn-sm nzf-danger" id="r-clear"><i class="fas fa-eraser" aria-hidden="true"></i> Tozalash</button>' : "") + "</div></section>" +
      // lines
      (S.lines.length
        ? '<section class="nzp-card nzf-lines"><div class="nzf-scroll"><table><thead><tr><th>Mahsulot</th><th>Soni</th><th>Tannarx (dona)</th><th class="num">Sotuv narxi · marja</th><th>Partiya · yaroqlilik muddati</th><th class="num">Summa</th><th></th></tr></thead><tbody>' +
          S.lines.map(lineRow).join("") + "</tbody></table></div></section>"
        : '<section class="nzp-card nzf-empty"><i class="fas fa-dolly" aria-hidden="true"></i><h3>Kelgan tovarlarni skanerlang</h3><p>Har bir skaner sonni 1 taga oshiradi; qutilab kelgan bo\'lsa sonni qo\'lda yozing. Yoki Excel shablonni to\'ldirib yuklang — tannarx, partiya va muddat ham o\'qiladi.</p></section>') +
      "</div>" +
      // side summary
      '<aside class="nzf-side"><section class="nzp-card nzf-sum">' +
      '<header><span class="nzf-loc-dot" style="--c:' + esc(loc ? loc.color : "#64748b") + '"><i class="fas ' + (loc && loc.kind === "warehouse" ? "fa-warehouse" : "fa-store") + '" aria-hidden="true"></i></span><div><small>Qabul qiluvchi</small><b>' + esc(loc ? loc.name : "—") + "</b></div></header>" +
      '<dl><div><dt>Mahsulot turlari</dt><dd>' + S.lines.length + "</dd></div><div><dt>Jami dona</dt><dd>" + t.units + "</dd></div>" +
      '<div class="big"><dt>Tannarx bo\'yicha qiymat</dt><dd>' + money(t.value) + " <small>so'm</small></dd></div>" +
      (t.revenue ? '<div><dt>Sotuv narxida</dt><dd>' + money(t.revenue) + " <small>so'm</small></dd></div>" +
        '<div><dt>Kutilayotgan yalpi foyda</dt><dd class="' + (profit < 0 ? "bad" : "ok") + '">' + money(profit) + " <small>so'm · " + pm + "%</small></dd></div>" : "") +
      "</dl>" +
      (t.nocost || t.loss || t.expiring ? '<ul class="nzf-warns">' +
        (t.nocost ? '<li class="warn"><i class="fas fa-coins" aria-hidden="true"></i> ' + t.nocost + " qatorda tannarx yo'q — ombor qiymati va marja hisoblanmaydi</li>" : "") +
        (t.loss ? '<li class="bad"><i class="fas fa-arrow-trend-down" aria-hidden="true"></i> ' + t.loss + " ta mahsulot tannarxdan arzon sotilyapti</li>" : "") +
        (t.expiring ? '<li class="warn"><i class="fas fa-calendar-xmark" aria-hidden="true"></i> ' + t.expiring + " ta partiyaning muddati 90 kundan kam</li>" : "") + "</ul>" : "") +
      '<button type="button" class="nzp-btn nzp-btn-primary nzf-post" id="r-post"' + (S.lines.length ? "" : " disabled") + '><i class="fas fa-circle-check" aria-hidden="true"></i> Kirimni tasdiqlash</button>' +
      '<p class="nzf-fine">Tasdiqlangach tovar <b>' + esc(loc ? loc.name : "") + "</b> qoldig'iga qo'shiladi, har bir qator Ombor tarixiga «Kirim» bo'lib yoziladi. Tannarx keyingi kirimlarda va hisobotlarda avtomatik ishlatiladi.</p></section>" +
      '<section class="nzp-card nzf-tips"><b><i class="fas fa-lightbulb" aria-hidden="true"></i> Maslahatlar</b><ul><li>2D skaner sahifaning istalgan joyida ishlaydi.</li><li>Qidiruvda ↑ ↓ va Enter bilan tanlang.</li><li>Notanish shtrix-kod — mavjud mahsulotga partiya kodi sifatida biriktiriladi.</li><li>Ro\'yxat sahifa yangilansa ham saqlanadi.</li></ul>' +
      '<a class="nzf-link" href="' + cfg.urls.list + '"><i class="fas fa-list" aria-hidden="true"></i> Barcha kirimlar</a></section></aside></div>';
    bind();
    var again = keep && root.querySelector(keep), scan = document.getElementById("r-scan");
    if (again) again.focus();
    else if (scan && modal.hidden) scan.focus();
    persist();
  }

  function flash(ok) { var box = root.querySelector(".nzf-scan"); if (!box) return; box.classList.remove("flash-ok", "flash-bad"); void box.offsetWidth; box.classList.add(ok ? "flash-ok" : "flash-bad"); beep(ok); }

  function fromProduct(p, qty) {
    return { variant_id: p.variant_id, name: p.name, sku: p.sku, barcode: p.matched || p.barcode, size: p.size, image_url: p.image_url, price: p.price || "",
      quantity: qty, unit_cost: p.prefill_cost ? String(Math.round(num(p.prefill_cost))) : "", cost_source: p.prefill_cost ? p.cost_source : "", batch: p.batch || "", expiry: p.expiry || "" };
  }

  function add(p, qty) {
    qty = qty || 1;
    if (!p.active) { flash(false); toast("err", p.name + " — faol emas"); return; }
    // one row per product + batch: a batch barcode (partiya kodi) brings its own batch number / expiry
    var batch = p.batch || "", expiry = p.expiry || "";
    // partiya = LOT + muddat (serverdagi StockBatch kabi)
    var line = S.lines.filter(function (l) { return l.variant_id === p.variant_id && (l.batch || "") === batch && (!expiry || (l.expiry || "") === expiry); })[0];
    if (line) line.quantity = num(line.quantity) + qty;
    else S.lines.unshift(fromProduct(p, qty));
    flash(true);
    toast("ok", "✓ " + p.name + (batch ? " · partiya " + batch : "") + " — " + (line ? line.quantity : qty) + " dona");
    var target = line || S.lines[0];
    render();
    var row = root.querySelector('tr[data-i="' + S.lines.indexOf(target) + '"]');
    if (row) { row.classList.add("flash"); row.scrollIntoView({ block: "nearest" }); }
  }

  function scan(code) {
    code = (code || "").trim();
    if (!code || busy) return;
    busy = true; // a scanner can fire Enter twice (CR+LF): never count one scan twice
    getJSON(cfg.urls.lookup + "?code=" + encodeURIComponent(code) + "&location=" + S.location).then(function (p) { add(p, 1); })
      .catch(function () {
        if (/^[0-9A-Za-z-]{6,32}$/.test(code) && /\d{6,}/.test(code) && cfg.urls.attach) attachFlow(code);
        else search(code, true);
      })
      .then(function () { setTimeout(function () { busy = false; }, 120); });
  }

  // An unknown barcode during receiving is usually a new batch of a product we already sell: pick the product
  // once, the barcode is attached to it (as an extra "partiya" barcode) and every later scan just works.
  function attachFlow(code) {
    flash(false);
    var d = modal.querySelector(".wms-dialog"), picked = null, rows = [], t = null;
    d.innerHTML =
      '<h4><i class="fas fa-barcode" aria-hidden="true"></i> Yangi shtrix-kod: <code>' + esc(code) + "</code></h4>" +
      '<p class="wms-muted" style="margin:4px 0 12px">Bu kod katalogda yo\'q. Agar bu mavjud mahsulotning yangi partiyasi bo\'lsa — mahsulotni tanlang, kod unga biriktiriladi va kirimga 1 dona qo\'shiladi.</p>' +
      '<div class="wms-field"><label for="ab-q">Mahsulot</label><input class="wms-input" id="ab-q" placeholder="Nomi yoki SKU…" autocomplete="off"></div>' +
      '<div class="wms-attach-list" id="ab-list"></div>' +
      '<div class="wms-grid2" style="margin-top:10px"><div class="wms-field"><label for="ab-batch">Partiya raqami (ixtiyoriy)</label><input class="wms-input" id="ab-batch" placeholder="LOT-2026-03"></div>' +
      '<div class="wms-field"><label for="ab-exp">Yaroqlilik (ixtiyoriy)</label><input class="wms-input" id="ab-exp" type="date"></div></div>' +
      '<div class="row-actions"><button type="button" class="wms-btn" data-x="0">Bekor qilish</button><button type="button" class="wms-btn primary" data-x="1" disabled><i class="fas fa-link" aria-hidden="true"></i> Biriktirish va qo\'shish</button></div>';
    modal.hidden = false;
    var q = d.querySelector("#ab-q"), list = d.querySelector("#ab-list"), ok = d.querySelector('[data-x="1"]');
    q.focus();
    function draw() {
      list.innerHTML = rows.length ? rows.slice(0, 8).map(function (r, i) {
        return '<button type="button" class="wms-result' + (picked === r ? " hl" : "") + '" data-i="' + i + '">' + thumb(r.image_url) + "<span><b>" + esc(r.name) + "</b><br><small class='wms-muted'>" + esc(r.sku) + (r.size ? " · " + esc(r.size) : "") + "</small></span></button>";
      }).join("") : (q.value.trim().length >= 2 ? '<div class="wms-empty" style="padding:12px">Topilmadi</div>' : "");
    }
    q.oninput = function () {
      clearTimeout(t);
      var v = q.value.trim();
      if (v.length < 2) { rows = []; draw(); return; }
      t = setTimeout(function () { getJSON(cfg.urls.search + "?all=1&location=" + S.location + "&q=" + encodeURIComponent(v)).then(function (r) { rows = r; draw(); }); }, 220);
    };
    list.onclick = function (e) { var b = e.target.closest("[data-i]"); if (!b) return; picked = rows[+b.getAttribute("data-i")]; ok.disabled = false; draw(); };
    d.onclick = function (e) {
      var b = e.target.closest("[data-x]");
      if (!b) return;
      if (b.getAttribute("data-x") === "0") { modal.hidden = true; document.getElementById("r-scan").focus(); return; }
      if (!picked) return;
      ok.disabled = true;
      fetch(cfg.urls.attach, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
        body: JSON.stringify({ code: code, variant_id: picked.variant_id, batch: d.querySelector("#ab-batch").value.trim(), expiry: d.querySelector("#ab-exp").value || null }) })
        .then(function (r) { return r.json().then(function (j) { if (!r.ok || !j.ok) throw new Error((j.error && j.error.message) || "Xato"); return j; }); })
        .then(function () {
          modal.hidden = true;
          toast("ok", "Shtrix-kod " + code + " → " + picked.name + " ga biriktirildi");
          return getJSON(cfg.urls.lookup + "?code=" + encodeURIComponent(code) + "&location=" + S.location).then(function (p) { add(p, 1); });
        })
        .catch(function (err) { ok.disabled = false; toast("err", err.message); })
        .then(function () { var sc = document.getElementById("r-scan"); if (sc) sc.focus(); });
    };
  }

  function search(q, fromScan) {
    var box = root.querySelector(".nzf-results");
    if (!box) return;
    if (!q || q.length < 2) { box.hidden = true; return; }
    getJSON(cfg.urls.search + "?all=1&location=" + S.location + "&q=" + encodeURIComponent(q)).then(function (rows) {
      results = rows; hl = rows.length ? 0 : -1;
      box.innerHTML = rows.length ? rows.map(function (r, i) {
        return '<div class="nzf-result' + (i === 0 ? " hl" : "") + '" data-r="' + i + '">' + thumb(r.image_url) + "<span><b>" + esc(r.name) + "</b><small>" + esc(r.sku) + " · " + esc(r.barcode || "—") + (r.size ? " · " + esc(r.size) : "") +
          (r.prefill_cost ? " · tannarx " + money(r.prefill_cost) : "") + '</small></span><span class="av"><b>' + r.available + "</b><small>bu yerda</small></span></div>";
      }).join("") : '<div class="nzf-result-empty">Katalogda topilmadi. Mahsulot avval «Mahsulotlar» bo\'limida yaratilishi kerak.</div>';
      box.hidden = false;
      if (fromScan && !rows.length) { flash(false); toast("err", "Bu shtrix-kod bo'yicha mahsulot topilmadi: " + q); }
    });
  }

  // ---------------------------------------------------------------- events
  function bind() {
    var scanEl = document.getElementById("r-scan"), box = root.querySelector(".nzf-results");
    scanEl.addEventListener("keydown", function (e) {
      if (!box.hidden && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
        e.preventDefault(); hl = Math.max(0, Math.min(results.length - 1, hl + (e.key === "ArrowDown" ? 1 : -1)));
        box.querySelectorAll(".nzf-result").forEach(function (el, i) { el.classList.toggle("hl", i === hl); }); return;
      }
      if (e.key === "Enter") {
        e.preventDefault();
        var v = scanEl.value.trim();
        if (!box.hidden && hl >= 0 && results[hl] && v && !/^\d{6,}$/.test(v)) { add(results[hl], 1); return; }
        clearTimeout(searchTimer); box.hidden = true;
        scanEl.value = ""; scan(v);
      }
      if (e.key === "Escape") box.hidden = true;
    });
    scanEl.addEventListener("input", function () { clearTimeout(searchTimer); var v = scanEl.value; searchTimer = setTimeout(function () { search(v); }, 260); });
    box.addEventListener("click", function (e) { var r = e.target.closest("[data-r]"); if (r) add(results[+r.getAttribute("data-r")], 1); });
    document.getElementById("r-loc").onchange = function (e) { S.location = e.target.value; render(); };
    document.getElementById("r-sup").onchange = function (e) { S.supplier = e.target.value.trim(); render(); };
    document.getElementById("r-inv").onchange = function (e) { S.invoice = e.target.value.trim(); persist(); };
    document.getElementById("r-note").onchange = function (e) { S.note = e.target.value; persist(); };
    root.querySelectorAll("tr[data-i]").forEach(function (row) {
      var l = S.lines[+row.getAttribute("data-i")];
      row.querySelector("[data-dec]").onclick = function () { l.quantity = Math.max(1, num(l.quantity) - 1); render(); };
      row.querySelector("[data-inc]").onclick = function () { l.quantity = num(l.quantity) + 1; render(); };
      row.querySelector("[data-q]").onchange = function (e) { l.quantity = Math.max(1, parseInt(e.target.value, 10) || 1); render(); };
      row.querySelector("[data-c]").onchange = function (e) { var v = num(e.target.value); l.unit_cost = v > 0 ? String(v) : ""; l.cost_origin = "typed"; render(); };
      row.querySelector("[data-b]").onchange = function (e) { l.batch = e.target.value.trim(); persist(); };
      var exp = row.querySelector("[data-e]");
      // yozish paytida jadval qayta chizilmaydi (fokus va kiritilgan raqamlar yo'qolmasin) — faqat chip yangilanadi
      exp.oninput = function () {
        var v = parseExpiry(exp.value);
        exp.classList.toggle("bad", v === null && exp.value.trim().length >= 5);
      };
      exp.onchange = function () {
        var v = parseExpiry(exp.value);
        if (v === null) { l.expiry = ""; l.expiry_bad = exp.value.trim(); }
        else { l.expiry = v; l.expiry_bad = ""; }
        render();
      };
      exp.onkeydown = function (e) { if (e.key === "Enter") { e.preventDefault(); exp.blur(); } };
      row.querySelector("[data-rm]").onclick = function () { S.lines.splice(S.lines.indexOf(l), 1); render(); };
    });
    var clear = document.getElementById("r-clear");
    if (clear) clear.onclick = function () { dialog("Ro'yxatni tozalash", "<p>Barcha qatorlar o'chiriladi.</p>", "Tozalash").then(function (ok) { if (ok) { S.lines = []; render(); } }); };
    var fill = document.getElementById("r-fillcost");
    if (fill) fill.onclick = function () { var first = root.querySelector(".nzf-cost.empty input"); if (first) { first.focus(); first.scrollIntoView({ block: "center" }); } };
    document.getElementById("r-file").onchange = upload;
    document.getElementById("r-post").onclick = post;
  }

  function upload(e) {
    var file = e.target.files[0];
    if (!file) return;
    var fd = new FormData();
    fd.append("file", file);
    toast("info", "Fayl o'qilmoqda…");
    fetch(cfg.urls.excel, { method: "POST", credentials: "same-origin", headers: { "X-CSRFToken": csrf() }, body: fd })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (!j.ok) throw new Error(j.error.message);
        j.data.lines.forEach(function (l) {
          S.lines.push({ variant_id: l.variant_id, name: l.name, sku: l.sku, barcode: l.barcode, size: l.size, image_url: l.image_url, price: l.price || "", quantity: l.quantity,
            unit_cost: l.unit_cost || "", cost_source: l.unit_cost && l.unit_cost === l.prefill_cost ? l.cost_source : "", batch: l.batch || "", expiry: l.expiry || "" });
        });
        render();
        toast("ok", j.data.lines.length + " ta qator qo'shildi — tekshirib «Kirimni tasdiqlash»ni bosing");
        if (j.data.problems.length) dialog("Excel: ba'zi qatorlar o'tkazib yuborildi", "<ul>" + j.data.problems.slice(0, 30).map(function (p) { return "<li>" + esc(p) + "</li>"; }).join("") + "</ul>", "Tushunarli");
      })
      .catch(function (err) { toast("err", err.message); })
      .then(function () { e.target.value = ""; });
  }

  function post() {
    var t = totals(), loc = location();
    var bad = S.lines.filter(function (l) { return l.expiry_bad || expiryProblem(l.expiry); });
    if (bad.length) {
      toast("err", bad.length + " qatorda yaroqlilik muddati noto'g'ri — qizil maydonlarni tuzating");
      var first = root.querySelector(".nzf-exp.bad"); if (first) { first.focus(); first.scrollIntoView({ block: "center" }); }
      return;
    }
    var expired = S.lines.filter(function (l) { var d = daysLeft(l.expiry); return d !== null && d < 0; }).length;
    var undated = S.lines.filter(function (l) { return !l.expiry; }).length;
    var warn = (expired ? '<li class="bad">' + expired + " ta partiyaning muddati allaqachon o'tgan — rostdan qabul qilasizmi?</li>" : "") +
      (undated ? "<li>" + undated + " qatorda yaroqlilik muddati kiritilmagan — FEFO va muddat ogohlantirishlari ishlamaydi</li>" : "") + (t.nocost ? "<li>" + t.nocost + " qatorda tannarx kiritilmagan</li>" : "") + (t.loss ? "<li>" + t.loss + " ta mahsulot zarariga sotilyapti</li>" : "") + (!S.supplier ? "<li>Yetkazib beruvchi ko'rsatilmagan — qarz kuzatilmaydi</li>" : "");
    dialog("Kirimni tasdiqlash", "<p><b>" + esc(loc.name) + "</b> qoldig'iga " + S.lines.length + " xil mahsulot, jami <b>" + t.units + "</b> dona" + (t.value ? " (" + money(t.value) + " so'm)" : "") + " qo'shiladi.</p>" +
      (warn ? '<ul class="nzf-dlg-warn">' + warn + "</ul>" : ""), expired ? "Baribir qabul qilish" : "Tasdiqlash").then(function (ok) {
      if (!ok) return;
      var btn = document.getElementById("r-post");
      btn.disabled = true; btn.innerHTML = '<i class="fas fa-circle-notch fa-spin" aria-hidden="true"></i> Saqlanmoqda…';
      fetch(cfg.urls.post, {
        method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
        body: JSON.stringify({ location: S.location, supplier: S.supplier, invoice: S.invoice, note: S.note, lines: S.lines.map(function (l) { return { variant_id: l.variant_id, quantity: num(l.quantity), unit_cost: num(l.unit_cost) > 0 ? String(num(l.unit_cost)) : null, batch: l.batch, expiry: l.expiry || null }; }) }),
      }).then(function (r) { return r.json(); }).then(function (j) {
        if (!j.ok) throw new Error(j.error.message);
        S.lines = []; S.supplier = ""; S.invoice = ""; S.note = "";
        persist();
        root.innerHTML = '<section class="nzp-card nzf-done"><i class="fas fa-circle-check" aria-hidden="true"></i><h2>' + esc(j.data.number) + " qabul qilindi</h2><p>" + j.data.units + " dona " + esc(loc.name) + " qoldig'iga qo'shildi" + (num(j.data.value) ? " · " + money(j.data.value) + " so'm" : "") + ".</p>" +
          '<div class="nzf-done-actions"><a class="nzp-btn nzp-btn-ghost" href="' + j.data.url + '"><i class="fas fa-file-lines" aria-hidden="true"></i> Kirim hujjati</a>' +
          (loc.kind === "warehouse" && cfg.urls.transfer ? '<a class="nzp-btn nzp-btn-ghost" href="' + cfg.urls.transfer + "?source=" + loc.id + '"><i class="fas fa-right-left" aria-hidden="true"></i> Filiallarga transfer</a>' : "") +
          '<a class="nzp-btn nzp-btn-primary" href="?"><i class="fas fa-plus" aria-hidden="true"></i> Yangi kirim</a></div></section>';
      }).catch(function (err) { toast("err", err.message); btn.disabled = false; btn.innerHTML = '<i class="fas fa-circle-check" aria-hidden="true"></i> Kirimni tasdiqlash'; });
    });
  }

  // 2D scanner anywhere on the page
  var buf = "", last = 0;
  document.addEventListener("keydown", function (e) {
    if (!modal.hidden) return;
    var tag = (e.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return;
    var now = Date.now();
    if (e.key === "Enter" && buf.length >= 4 && now - last < 120) { e.preventDefault(); var c = buf; buf = ""; scan(c); return; }
    if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) { buf = now - last < 60 ? buf + e.key : e.key; last = now; }
  });
  document.addEventListener("click", function (e) { var box = root.querySelector(".nzf-results"); if (box && !e.target.closest(".nzf-scan")) box.hidden = true; });

  if (!cfg.locations.length) { root.innerHTML = '<section class="nzp-card nzf-empty"><i class="fas fa-warehouse" aria-hidden="true"></i><h3>Joy yo\'q</h3><p>Avval «Do\'konlar» bo\'limida «Sklad» turidagi joy yarating.</p></section>'; return; }
  if (!location()) S.location = cfg.default_location;
  render();
})();
