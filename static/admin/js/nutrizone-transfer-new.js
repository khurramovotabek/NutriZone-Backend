/*
 * NutriZone WMS -- new transfer (templates/admin/wms/transfer_new.html). Source / destination cards, then the
 * "smart fill-up" list: what the destination is short of (under its minimum, or selling without a rule) that the
 * source can send. Ticked lines go into the draft as hidden JSON `lines`; the workspace takes over from there.
 */
(function () {
  "use strict";

  var form = document.getElementById("nzf-new");
  if (!form) return;
  var box = document.getElementById("nzf-suggest"), body = document.getElementById("nzf-sg-body"), all = document.getElementById("nzf-sg-all");
  var btn = document.getElementById("nzf-create"), hidden = document.getElementById("nzf-lines");
  var rows = [], picked = {}, req = 0;

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function money(n) { return Math.round(Number(n) || 0).toLocaleString("ru-RU").replace(/ /g, " "); }
  function checked(name) { return form.querySelector('input[name="' + name + '"]:checked'); }
  function nameOf(input) { return input ? input.closest(".nzf-loc").querySelector(".nzf-loc-main b").textContent : ""; }

  function sync() {
    var src = checked("source");
    form.querySelectorAll(".nzf-loc").forEach(function (l) {
      var input = l.querySelector("input");
      if (input.name === "destination") {
        var same = !!src && input.value === src.value;
        l.classList.toggle("off", same);
        input.disabled = same;
        if (same && input.checked) input.checked = false;
      }
      l.classList.toggle("on", input.checked);
    });
    var dst = checked("destination");
    document.getElementById("nzf-route-text").textContent = src && dst ? nameOf(src) + " → " + nameOf(dst) : src ? nameOf(src) + " → ?" : "Yo'nalishni tanlang";
    btn.disabled = !(src && dst);
    load(src, dst);
  }

  var lastKey = "";
  function load(src, dst) {
    var key = src && dst ? src.value + ">" + dst.value : "";
    if (key === lastKey) return;
    lastKey = key; rows = []; picked = {};
    if (!key) { box.hidden = true; summary(); return; }
    box.hidden = false;
    body.innerHTML = '<div class="nzf-sg-empty"><i class="fas fa-circle-notch fa-spin" aria-hidden="true"></i> Tahlil qilinmoqda…</div>';
    var mine = ++req;
    fetch(form.getAttribute("data-suggest") + "?source=" + src.value + "&destination=" + dst.value, { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (mine !== req) return;
        rows = (j.data && j.data.lines) || [];
        rows.forEach(function (r) { if (r.out) picked[r.variant_id] = r.suggest; }); // out of stock lines come ticked
        draw();
      })
      .catch(function () { if (mine === req) body.innerHTML = '<div class="nzf-sg-empty">Takliflarni yuklab bo\'lmadi — mahsulotlarni keyingi qadamda qo\'shing.</div>'; });
  }

  function draw() {
    if (!rows.length) {
      body.innerHTML = '<div class="nzf-sg-empty"><i class="fas fa-circle-check" aria-hidden="true"></i> Qabul qiluvchida shoshilinch kamomad yo\'q. Mahsulotlarni keyingi qadamda skaner yoki qidiruv bilan qo\'shasiz.' +
        '<small>Takliflar «To\'ldirish (minimal qoldiq)» qoidalari va 30 kunlik sotuvdan hisoblanadi.</small></div>';
      all.parentNode.hidden = true;
      summary();
      return;
    }
    all.parentNode.hidden = false;
    body.innerHTML = '<div class="nzf-sg-table" role="table"><div class="nzf-sg-tr nzf-sg-th" role="row"><span></span><span>Mahsulot</span><span class="r">Qabul qiluvchida</span><span class="r">Min → maqsad</span><span class="r">30 kun sotuv</span><span class="r">Manbada</span><span class="r">Yuboriladi</span></div>' +
      rows.map(function (r, i) {
        var on = r.variant_id in picked;
        return '<div class="nzf-sg-tr' + (on ? " on" : "") + (r.out ? " out" : "") + '" role="row" data-i="' + i + '">' +
          '<span><input type="checkbox" data-pick' + (on ? " checked" : "") + ' aria-label="' + esc(r.name) + '"></span>' +
          '<span class="nzf-sg-prod">' + (r.image_url ? '<img src="' + esc(r.image_url) + '" alt="">' : '<i class="fas fa-box" aria-hidden="true"></i>') +
          "<span><b>" + esc(r.name) + "</b><small>" + esc(r.sku) + (r.size ? " · " + esc(r.size) : "") + ' · <em class="' + r.why + '">' + (r.why === "rule" ? "minimal qoldiq qoidasi" : "sotuv bo'yicha") + "</em></small></span></span>" +
          '<span class="r"><b class="' + (r.out ? "bad" : "warn") + '">' + r.available + "</b>" + (r.incoming ? "<small>+" + r.incoming + " yo'lda</small>" : "") + (r.days_cover != null ? "<small>~" + r.days_cover + " kunga</small>" : "") + "</span>" +
          '<span class="r">' + r.min + " → " + r.target + "</span>" +
          '<span class="r">' + (r.sold || "—") + "</span>" +
          '<span class="r">' + r.source_available + (r.want > r.source_available ? '<small class="warn">yetmaydi: ' + r.want + " kerak</small>" : "") + "</span>" +
          '<span class="r"><input type="number" min="1" max="' + r.source_available + '" value="' + (picked[r.variant_id] || r.suggest) + '" data-qty aria-label="Miqdor"></span></div>';
      }).join("") + "</div>";
    summary();
  }

  function summary() {
    var ids = Object.keys(picked), units = 0, value = 0;
    var lines = ids.map(function (id) {
      var r = rows.filter(function (x) { return x.variant_id === id; })[0];
      units += picked[id]; value += picked[id] * (Number(r && r.cost) || 0);
      return { variant_id: id, quantity: picked[id] };
    });
    hidden.value = JSON.stringify(lines);
    all.checked = rows.length > 0 && ids.length === rows.length;
    document.getElementById("nzf-picked").innerHTML = ids.length ? '<i class="fas fa-boxes-stacked" aria-hidden="true"></i> <b>' + ids.length + "</b> xil · <b>" + units + "</b> dona" + (value ? " · ~" + money(value) + " so'm" : "") : "";
    btn.querySelector("span").textContent = ids.length ? "Transfer yaratish (" + ids.length + " xil, " + units + " dona)" : "Davom etish: mahsulot qo'shish";
  }

  body.addEventListener("change", function (e) {
    var row = e.target.closest("[data-i]");
    if (!row) return;
    var r = rows[+row.getAttribute("data-i")], qty = row.querySelector("[data-qty]");
    if (e.target.hasAttribute("data-qty")) {
      var n = Math.max(1, Math.min(r.source_available, parseInt(qty.value, 10) || 1));
      qty.value = n;
      picked[r.variant_id] = n;
      row.querySelector("[data-pick]").checked = true;
    } else if (e.target.checked) picked[r.variant_id] = parseInt(qty.value, 10) || r.suggest;
    else delete picked[r.variant_id];
    row.classList.toggle("on", r.variant_id in picked);
    summary();
  });
  // a click anywhere on a row (except its inputs) ticks it
  body.addEventListener("click", function (e) {
    var row = e.target.closest("[data-i]");
    if (!row || e.target.closest("input")) return;
    var cb = row.querySelector("[data-pick]");
    cb.checked = !cb.checked;
    cb.dispatchEvent(new Event("change", { bubbles: true }));
  });
  all.addEventListener("change", function () {
    picked = {};
    if (all.checked) rows.forEach(function (r) { picked[r.variant_id] = r.suggest; });
    draw();
  });
  form.addEventListener("change", function (e) { if (e.target.name === "source" || e.target.name === "destination") sync(); });
  form.addEventListener("submit", function () { btn.disabled = true; btn.querySelector("span").textContent = "Yaratilmoqda…"; });
  sync();
})();
