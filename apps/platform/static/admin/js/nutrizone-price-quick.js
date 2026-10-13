/*
 * NutriZone Admin -- quick price editor on the product list (Mahsulotlar).
 * The price cell is a button: it opens every variant of the product with its cost, selling price, old price, live
 * margin, stock and last purchase cost, and saves only the rows that changed through the price-list API (the same
 * validation + price history as the Narxlar ro'yxati page). Enter saves, Esc closes.
 */
(function () {
  "use strict";
  var cfgEl = document.getElementById("nzq-config");
  if (!cfgEl) return;
  var cfg = JSON.parse(cfgEl.textContent);
  var dlg, state = null;

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function num(v) { v = String(v == null ? "" : v).replace(/\s/g, "").replace(",", "."); return v === "" ? null : Number(v); }
  function money(n) { return n == null || isNaN(n) ? "" : Math.round(n).toLocaleString("ru-RU").replace(/ /g, " "); }
  function csrf() { var m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/); var i = document.querySelector("input[name=csrfmiddlewaretoken]"); return i ? i.value : m ? decodeURIComponent(m[1]) : ""; }
  function fmtInput(v) { return v == null ? "" : money(Number(v)); }

  function ensureDialog() {
    if (dlg) return dlg;
    dlg = document.createElement("dialog");
    dlg.className = "nzq-dialog";
    dlg.setAttribute("aria-labelledby", "nzq-title");
    document.body.appendChild(dlg);
    dlg.addEventListener("click", onClick);
    dlg.addEventListener("input", onInput);
    dlg.addEventListener("keydown", function (e) { if (e.key === "Enter" && e.target.matches("input")) { e.preventDefault(); save(); } });
    dlg.addEventListener("close", function () { state = null; });
    return dlg;
  }

  function open(productId, cell) {
    ensureDialog();
    state = { id: productId, cell: cell, rows: [], busy: false };
    dlg.innerHTML = '<div class="nzq-body nzq-loading"><i class="fas fa-spinner fa-spin" aria-hidden="true"></i></div>';
    dlg.showModal();
    fetch(cfg.product.replace("__", productId), { credentials: "same-origin" }).then(function (r) { return r.json(); }).then(function (j) {
      if (!j.success) throw new Error((j.error && j.error.message) || "Xatolik");
      state.product = j.data;
      state.rows = j.data.variants.map(function (v) { return { v: v, cost: v.cost == null ? null : Number(v.cost), price: v.price == null ? null : Number(v.price), old: v.old_price == null ? null : Number(v.old_price), dirty: false, err: "", ok: false }; });
      render();
    }).catch(function (e) { dlg.innerHTML = '<div class="nzq-body"><p class="nzq-err">' + esc(e.message) + '</p><button type="button" class="nzq-btn" data-close>Yopish</button></div>'; });
  }

  function margin(r) {
    if (r.price == null || r.cost == null || !r.price) return null;
    return { sum: r.price - r.cost, pct: Math.round((r.price - r.cost) * 1000 / r.price) / 10 };
  }

  function rowHtml(r, i) {
    var v = r.v, m = margin(r), discount = r.old && r.price && r.old > r.price ? Math.round((1 - r.price / r.old) * 100) : 0;
    return '<div class="nzq-row' + (r.dirty ? " is-dirty" : "") + (r.ok ? " is-ok" : "") + (r.err ? " is-err" : "") + '" data-i="' + i + '">' +
      '<div class="nzq-variant"><b>' + esc(v.label) + '</b><small>' + esc(v.sku) + ' · <span class="nzq-stock' + (v.stock > 0 ? "" : " out") + '">' + v.stock + ' dona</span>' + (v.status !== "active" ? ' · <em>' + esc(v.status) + "</em>" : "") + "</small></div>" +
      '<label class="nzq-field"><span>Tannarx</span><input inputmode="numeric" data-f="cost" value="' + fmtInput(r.cost) + '" placeholder="—">' +
        (v.last_cost ? '<button type="button" class="nzq-hint" data-fill="' + i + '" title="Oxirgi kirim narxini qo\'yish">kirim: ' + money(Number(v.last_cost)) + "</button>" : "") + "</label>" +
      '<label class="nzq-field nzq-main"><span>Sotuv narxi *</span><input inputmode="numeric" data-f="price" value="' + fmtInput(r.price) + '" placeholder="0"></label>' +
      '<label class="nzq-field"><span>Eski narx</span><input inputmode="numeric" data-f="old" value="' + fmtInput(r.old) + '" placeholder="—">' + (discount ? '<em class="nzq-badge">−' + discount + "%</em>" : "") + "</label>" +
      '<div class="nzq-margin' + (m ? (m.pct < 0 ? " neg" : m.pct < 15 ? " low" : "") : "") + '"><span>Marja</span><b>' + (m ? m.pct + "%" : "—") + "</b><small>" + (m ? money(m.sum) + " so'm" : "") + "</small></div>" +
      '<div class="nzq-state">' + (r.err ? '<i class="fas fa-circle-exclamation" title="' + esc(r.err) + '"></i>' : r.ok ? '<i class="fas fa-circle-check"></i>' : r.dirty ? '<i class="fas fa-circle"></i>' : "") + "</div>" +
      (r.err ? '<p class="nzq-row-err">' + esc(r.err) + "</p>" : "") +
    "</div>";
  }

  function render() {
    var p = state.product, dirty = state.rows.filter(function (r) { return r.dirty; }).length;
    dlg.innerHTML = '<form method="dialog" class="nzq-body">' +
      '<header class="nzq-head"><span class="nzq-icon"><i class="fas fa-tags" aria-hidden="true"></i></span><div><h3 id="nzq-title">' + esc(p.name) + '</h3><p>' + p.variants.length + ' ta variant · narxlar barcha kanallarda (sayt, kassa) darhol yangilanadi</p></div>' +
        '<button type="button" class="nzq-x" data-close aria-label="Yopish"><i class="fas fa-xmark" aria-hidden="true"></i></button></header>' +
      (p.variants.length > 1 ? '<div class="nzq-bulk"><span><i class="fas fa-wand-magic-sparkles" aria-hidden="true"></i> Hammasiga:</span><input inputmode="numeric" data-bulk placeholder="Sotuv narxi"><button type="button" class="nzq-btn nzq-ghost" data-apply>Qo\'llash</button><button type="button" class="nzq-btn nzq-ghost" data-markup="30">Tannarx +30%</button></div>' : "") +
      (state.rows.length ? '<div class="nzq-rows">' + state.rows.map(rowHtml).join("") + "</div>"
        : '<div class="nzq-none"><i class="fas fa-layer-group" aria-hidden="true"></i><b>Bu mahsulotda hali variant yo\'q</b><span>Narx variantga (hajm / ta\'m) qo\'yiladi. Avval mahsulot kartasida variant qo\'shing — keyin narxni shu yerdan bir bosishda qo\'yasiz.</span><a class="nzq-btn nzq-primary" href="' + esc(cfg.edit.replace("00000000-0000-0000-0000-000000000000", p.id)) + '#variants"><i class="fas fa-plus" aria-hidden="true"></i> Variant qo\'shish</a></div>') +
      '<footer class="nzq-foot"><a href="' + esc(cfg.edit.replace("00000000-0000-0000-0000-000000000000", p.id)) + '" class="nzq-link"><i class="fas fa-pen-to-square" aria-hidden="true"></i> Mahsulot kartasi</a>' +
        '<span class="nzq-count">' + (dirty ? dirty + " ta o'zgarish" : "O'zgarish yo'q") + '</span><button type="button" class="nzq-btn nzq-ghost" data-close>Bekor qilish</button>' +
        '<button type="button" class="nzq-btn nzq-primary" data-save' + (dirty && !state.busy ? "" : " disabled") + '>' + (state.busy ? '<i class="fas fa-spinner fa-spin"></i>' : '<i class="fas fa-check"></i>') + " Saqlash <kbd>Enter</kbd></button></footer></form>";
  }

  function refreshRow(i) {
    var el = dlg.querySelector('[data-i="' + i + '"]'), r = state.rows[i];
    var focus = document.activeElement && document.activeElement.getAttribute("data-f"), pos = document.activeElement && document.activeElement.selectionStart;
    var tmp = document.createElement("div"); tmp.innerHTML = rowHtml(r, i); el.replaceWith(tmp.firstChild);
    if (focus) { var inp = dlg.querySelector('[data-i="' + i + '"] [data-f="' + focus + '"]'); if (inp) { inp.focus(); try { inp.setSelectionRange(pos, pos); } catch (e) { /* number-ish */ } } }
    var dirty = state.rows.filter(function (x) { return x.dirty; }).length;
    dlg.querySelector(".nzq-count").textContent = dirty ? dirty + " ta o'zgarish" : "O'zgarish yo'q";
    dlg.querySelector("[data-save]").disabled = !dirty || state.busy;
  }

  function onInput(e) {
    var f = e.target.getAttribute("data-f"); if (!f) return;
    var row = e.target.closest("[data-i]"), i = Number(row.getAttribute("data-i")), r = state.rows[i];
    var raw = e.target.value.replace(/[^\d]/g, "");
    var before = e.target.value.length - e.target.selectionStart;
    e.target.value = raw ? money(Number(raw)) : "";
    try { var p = Math.max(0, e.target.value.length - before); e.target.setSelectionRange(p, p); } catch (er) { /* ignore */ }
    r[f] = raw ? Number(raw) : null; r.dirty = true; r.ok = false; r.err = "";
    refreshRow(i);
  }

  function onClick(e) {
    var b;
    if (e.target === dlg || e.target.closest("[data-close]")) { e.preventDefault(); dlg.close(); return; }
    if ((b = e.target.closest("[data-fill]"))) { var i = Number(b.getAttribute("data-fill")), r = state.rows[i]; r.cost = Number(r.v.last_cost); r.dirty = true; r.ok = false; refreshRow(i); return; }
    if (e.target.closest("[data-apply]")) {
      var val = num(dlg.querySelector("[data-bulk]").value); if (!val) return;
      state.rows.forEach(function (r) { r.price = val; r.dirty = true; r.ok = false; r.err = ""; }); render(); return;
    }
    if ((b = e.target.closest("[data-markup]"))) {
      var k = 1 + Number(b.getAttribute("data-markup")) / 100;
      state.rows.forEach(function (r) { var c = r.cost != null ? r.cost : r.v.last_cost ? Number(r.v.last_cost) : null; if (c) { r.cost = c; r.price = Math.ceil(c * k / 1000) * 1000; r.dirty = true; r.ok = false; r.err = ""; } }); render(); return;
    }
    if (e.target.closest("[data-save]")) { e.preventDefault(); save(); }
  }

  function save() {
    if (!state || state.busy) return;
    var todo = state.rows.map(function (r, i) { return { r: r, i: i }; }).filter(function (x) { return x.r.dirty; });
    if (!todo.length) return;
    var bad = todo.filter(function (x) { return !x.r.price; });
    bad.forEach(function (x) { x.r.err = "Sotuv narxini kiriting"; });
    todo = todo.filter(function (x) { return x.r.price; });
    todo.forEach(function (x) { if (x.r.old != null && x.r.old <= x.r.price) x.r.err = "Eski narx sotuv narxidan katta bo'lishi kerak"; });
    todo = todo.filter(function (x) { return !x.r.err; });
    if (!todo.length) { render(); return; }
    state.busy = true; render();
    var chain = Promise.resolve();
    todo.forEach(function (x) {
      chain = chain.then(function () {
        return fetch(cfg.save.replace("__", x.r.v.id), { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
          body: JSON.stringify({ price: x.r.price, base_price: x.r.cost, old_price: x.r.old }) })
          .then(function (res) { return res.json(); }).then(function (j) {
            if (!j.success) throw new Error((j.error && j.error.message) || "Saqlanmadi");
            x.r.dirty = false; x.r.ok = true; x.r.err = ""; x.r.v.price = String(x.r.price);
          }).catch(function (er) { x.r.err = er.message; });
      });
    });
    chain.then(function () {
      state.busy = false; render();
      updateCell();
      if (state.rows.every(function (r) { return !r.dirty && !r.err; })) { toast("✓ Narxlar saqlandi"); setTimeout(function () { if (dlg.open) dlg.close(); }, 650); }
    });
  }

  function updateCell() {
    var cell = state.cell; if (!cell) return;
    var want = cell.getAttribute("data-variant");
    var r = state.rows.filter(function (x) { return x.v.id === want; })[0] || state.rows.filter(function (x) { return x.v.price; })[0];
    if (!r || r.price == null) return;
    cell.className = "nzq-cell nzc-price nzq-flash";
    cell.setAttribute("data-variant", r.v.id);
    cell.innerHTML = "<b>" + money(r.price) + "</b> <small>so'm</small><i class=\"fas fa-pen\"></i>";
  }

  function toast(t) {
    var el = document.createElement("div"); el.className = "nzq-toast"; el.textContent = t; document.body.appendChild(el);
    setTimeout(function () { el.classList.add("out"); setTimeout(function () { el.remove(); }, 300); }, 1800);
  }

  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-nzq]"); if (!b) return;
    e.preventDefault(); e.stopPropagation();
    open(b.getAttribute("data-nzq"), b);
  }, true);
})();
