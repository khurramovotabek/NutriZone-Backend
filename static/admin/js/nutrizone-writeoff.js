/*
 * NutriZone Admin -- new write-off (templates/admin/wms/writeoff_new.html).
 * Pick the location, scan (one scan = one unit) or search its available stock, set quantity / reason / batch per line,
 * then send for approval (units are reserved) or -- with the approve permission -- write off at once.
 * The location is locked while the list has lines, so lines always belong to the location they were checked against.
 */
(function () {
  "use strict";
  var app = document.getElementById("wx-writeoff");
  if (!app) return;
  var cfg = JSON.parse(document.getElementById("wx-config").textContent);
  var L = JSON.parse(document.getElementById("wx-i18n").textContent);
  var S = { loc: cfg.location, lines: cfg.lines || [], reason: (cfg.lines[0] && cfg.lines[0].reason) || "damaged", note: "", busy: false, results: [], timer: null };
  var reasons = {};
  cfg.reasons.forEach(function (r) { reasons[r.key] = r; });

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function csrf() { var i = document.querySelector("input[name=csrfmiddlewaretoken]"); return i ? i.value : ""; }
  function money(n) { return Math.round(Number(n) || 0).toLocaleString("ru-RU").replace(/ /g, " "); }
  function api(url, body) {
    var opts = { credentials: "same-origin", headers: { "X-CSRFToken": csrf(), "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" } };
    if (body !== undefined) { opts.method = "POST"; opts.body = JSON.stringify(body); }
    return fetch(url, opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok || j.ok === false) { var e = new Error((j.error && j.error.message) || L.error); e.status = r.status; throw e; } return j; });
    });
  }
  function toast(text, bad) {
    var el = document.querySelector("[data-nzp-toast]");
    el.textContent = text; el.classList.toggle("is-error", !!bad); el.hidden = false;
    clearTimeout(toast.t); toast.t = setTimeout(function () { el.hidden = true; }, bad ? 4500 : 2200);
  }
  function beep(ok) {
    try { var c = new (window.AudioContext || window.webkitAudioContext)(), o = c.createOscillator(), g = c.createGain(); o.frequency.value = ok ? 880 : 220; g.gain.value = 0.05; o.connect(g); g.connect(c.destination); o.start(); setTimeout(function () { o.stop(); c.close(); }, ok ? 90 : 260); } catch (e) { /* no audio */ }
  }
  function thumb(url) { return url ? '<img src="' + esc(url) + '" alt="">' : '<span class="ph"><i class="fas fa-box" aria-hidden="true"></i></span>'; }

  /* ---------------- render ---------------- */
  function render() {
    var locked = S.lines.length > 0;
    app.innerHTML =
      '<section class="nzp-card"><header class="nzp-card-head nzp-card-head-sm"><span class="nzp-card-icon" style="--c:#ef4444"><i class="fas fa-location-dot" aria-hidden="true"></i></span><div><h3>' + esc(L.where) + "</h3></div></header>" +
      '<div class="wx-locs" role="radiogroup">' + cfg.locations.map(function (l) {
        var on = l.id === S.loc, off = locked && !on;
        return '<label class="wx-loc' + (off ? " is-busy" : "") + '" style="--c:' + esc(l.color) + '"><input type="radio" name="wx-loc" value="' + l.id + '"' + (on ? " checked" : "") + (off ? " disabled" : "") + ">" +
          '<span class="wx-loc-body"><span class="wx-loc-icon"><i class="fas ' + (l.kind === "warehouse" ? "fa-warehouse" : "fa-store") + '" aria-hidden="true"></i></span><span class="wx-loc-text"><b>' + esc(l.name) + "</b><small>" + l.units + " " + esc(L.pcs) + "</small></span></span></label>";
      }).join("") + "</div></section>" +
      '<section class="nzp-card">' +
      '<div class="wx-wo-reasons"><span>' + esc(L.defaultReason) + ':</span>' + cfg.reasons.map(function (r) {
        return '<button type="button" class="wx-chip' + (r.key === S.reason ? " on" : "") + '" data-reason="' + r.key + '" style="--c:' + r.color + '"><i class="fas ' + r.icon + '" aria-hidden="true"></i> ' + esc(r.label) + "</button>";
      }).join("") + "</div>" +
      '<div class="wx-wo-scan"><label class="wx-scan"><i class="fas fa-barcode" aria-hidden="true"></i><input data-scan autocomplete="off" placeholder="' + esc(L.scanPh) + '" aria-label="' + esc(L.scanPh) + '"><span>' + esc(L.scanHint) + "</span></label>" +
      '<ul class="wx-results wx-wo-results" data-results hidden></ul></div>' +
      '<div data-lines></div></section>' +
      '<section class="nzp-card wx-wo-foot"><div class="wx-wo-totals" data-totals></div>' +
      '<input class="nzd-input" data-note maxlength="255" placeholder="' + esc(L.notePh) + '" value="' + esc(S.note) + '">' +
      '<div class="wx-wo-buttons"><a class="nzp-btn nzp-btn-ghost" href="' + cfg.urls.list + '">' + esc(L.cancel) + "</a>" +
      '<button type="button" class="nzp-btn nzp-btn-primary" data-submit="0"><i class="fas fa-paper-plane" aria-hidden="true"></i> ' + esc(L.submit) + "</button>" +
      (cfg.can_approve ? '<button type="button" class="nzp-btn nzp-btn-danger" data-submit="1"><i class="fas fa-check-double" aria-hidden="true"></i> ' + esc(L.approveNow) + "</button>" : "") +
      "</div></section>";
    renderLines(); renderTotals();
    var scan = app.querySelector("[data-scan]");
    if (scan) scan.focus();
  }

  function renderLines() {
    var box = app.querySelector("[data-lines]");
    if (!S.lines.length) { box.innerHTML = '<div class="nzp-empty wx-wo-empty"><span class="nzp-empty-icon" style="--c:#ef4444"><i class="fas fa-box-open" aria-hidden="true"></i></span><p>' + esc(L.empty) + "</p></div>"; return; }
    box.innerHTML = '<div class="wx-table wx-wo-table"><div class="wx-tr wx-th"><span>' + esc(L.product) + '</span><span class="r">' + esc(L.available) + "</span><span>" + esc(L.qty) + "</span><span>" + esc(L.reason) + "</span><span>" + esc(L.batch) + "</span><span></span></div>" +
      S.lines.map(function (l, n) {
        var over = Number(l.quantity) > l.available;
        return '<div class="wx-tr' + (over ? " is-short" : "") + '" data-n="' + n + '"><span class="wx-prod">' + thumb(l.image_url) + "<span><b>" + esc(l.name) + "</b><small>" + esc(l.sku) + (l.size ? " · " + esc(l.size) : "") + (Number(l.cost) ? " · " + money(l.cost) + " " + esc(L.som) : " · " + esc(L.noCost)) + "</small></span></span>" +
          '<span class="r"><b class="wx-num">' + l.available + "</b>" + (over ? "<small class=\"wx-minus\">" + esc(L.tooMany.replace("%s", l.available)) + "</small>" : "") + "</span>" +
          '<span><span class="wx-stepper"><button type="button" data-step="-1" aria-label="−">−</button><input data-qty inputmode="numeric" value="' + esc(l.quantity) + '" aria-label="' + esc(L.qty) + '"><button type="button" data-step="1" aria-label="+">+</button></span></span>' +
          '<span><select class="nzp-select" data-line-reason aria-label="' + esc(L.reason) + '">' + cfg.reasons.map(function (r) { return '<option value="' + r.key + '"' + (r.key === l.reason ? " selected" : "") + ">" + esc(r.label) + "</option>"; }).join("") + "</select></span>" +
          '<span class="wx-wo-batch"><input class="nzd-input" data-batch maxlength="48" placeholder="LOT" value="' + esc(l.batch) + '" aria-label="LOT"><input class="nzd-input" type="date" data-expiry value="' + esc(l.expiry) + '" aria-label="' + esc(L.batch) + '"></span>' +
          '<span class="r"><button type="button" class="nzp-icon-btn" data-remove aria-label="' + esc(L.remove) + '" title="' + esc(L.remove) + '"><i class="fas fa-xmark" aria-hidden="true"></i></button></span></div>';
      }).join("") + "</div>";
  }

  function renderTotals() {
    var units = 0, value = 0, bad = false;
    S.lines.forEach(function (l) { var q = Number(l.quantity) || 0; units += q; value += q * (Number(l.cost) || 0); if (q > l.available || q <= 0) bad = true; });
    app.querySelector("[data-totals]").innerHTML = "<span>" + esc(L.lines) + " <b>" + S.lines.length + "</b></span><span>" + esc(L.units) + ' <b class="wx-minus">−' + units + "</b></span><span>" + esc(L.value) + " <b>" + money(value) + " " + esc(L.som) + "</b></span>";
    app.querySelectorAll("[data-submit]").forEach(function (b) { b.disabled = !S.lines.length || bad || S.busy; });
  }

  /* ---------------- adding ---------------- */
  function add(p) {
    if (!p.available || p.available <= 0) { beep(false); toast(p.name + " — " + L.noStock, true); return; }
    var batch = p.batch || "";
    var line = S.lines.filter(function (l) { return l.variant_id === p.variant_id && (l.batch || "") === batch && l.reason === S.reason; })[0];
    if (line) line.quantity = (Number(line.quantity) || 0) + 1;
    else S.lines.unshift({ variant_id: p.variant_id, name: p.name, sku: p.sku, size: p.size, image_url: p.image_url, available: p.available, cost: p.cost || "0", quantity: 1, reason: S.reason, batch: batch, expiry: p.expiry || "", note: "" });
    beep(true);
    toast("✓ " + p.name + " — " + (line ? line.quantity : 1) + " " + L.pcs);
    if (S.lines.length === 1 && !line) render(); else { renderLines(); renderTotals(); }
    var row = app.querySelector('.wx-wo-table [data-n="' + S.lines.indexOf(line || S.lines[0]) + '"]');
    if (row) row.classList.add("flash");
  }

  function lookup(code) {
    if (S.busy) return;
    S.busy = true; // a scanner can send Enter twice: one scan, one unit
    api(cfg.urls.lookup + "?code=" + encodeURIComponent(code) + "&location=" + encodeURIComponent(S.loc)).then(function (j) { add(j.data); })
      .catch(function (e) { if (e.status === 404) search(code, true); else toast(e.message, true); })
      .then(function () { setTimeout(function () { S.busy = false; }, 120); });
  }

  function search(q, fromScan) {
    var box = app.querySelector("[data-results]");
    api(cfg.urls.search + "?location=" + encodeURIComponent(S.loc) + "&q=" + encodeURIComponent(q)).then(function (j) {
      S.results = j.data || [];
      if (fromScan && S.results.length === 1) { add(S.results[0]); box.hidden = true; return; }
      if (fromScan && !S.results.length) { beep(false); toast(L.notFound, true); }
      box.hidden = !S.results.length && !fromScan;
      box.innerHTML = S.results.length ? S.results.map(function (p, n) {
        return '<li><button type="button" data-pick="' + n + '">' + thumb(p.image_url) + "<span><b>" + esc(p.name) + "</b><small>" + esc(p.sku) + (p.size ? " · " + esc(p.size) : "") + "</small></span><em>" + p.available + "</em></button></li>";
      }).join("") : '<li class="wx-muted">' + esc(L.nothing) + "</li>";
    }).catch(function (e) { toast(e.message, true); });
  }

  /* ---------------- events ---------------- */
  app.addEventListener("change", function (e) {
    var t = e.target;
    if (t.name === "wx-loc") { S.loc = t.value; render(); return; }
    var row = t.closest("[data-n]");
    if (!row) return;
    var l = S.lines[Number(row.getAttribute("data-n"))];
    if (t.matches("[data-line-reason]")) l.reason = t.value;
    if (t.matches("[data-expiry]")) l.expiry = t.value;
  });
  app.addEventListener("input", function (e) {
    var t = e.target;
    if (t.matches("[data-note]")) { S.note = t.value; return; }
    if (t.matches("[data-scan]")) {
      clearTimeout(S.timer);
      var q = t.value.trim(), box = app.querySelector("[data-results]");
      if (q.length < 2 || /^\d{6,}$/.test(q)) { box.hidden = true; return; } // digits only: a scanner is typing -- wait for Enter
      S.timer = setTimeout(function () { search(q, false); }, 250);
      return;
    }
    var row = t.closest("[data-n]");
    if (!row) return;
    var l = S.lines[Number(row.getAttribute("data-n"))];
    if (t.matches("[data-qty]")) { l.quantity = t.value.replace(/\D/g, ""); row.classList.toggle("is-short", Number(l.quantity) > l.available); renderTotals(); }
    if (t.matches("[data-batch]")) l.batch = t.value;
  });
  app.addEventListener("keydown", function (e) {
    if (e.target.matches("[data-scan]") && e.key === "Enter") {
      e.preventDefault();
      var code = e.target.value.trim();
      e.target.value = "";
      app.querySelector("[data-results]").hidden = true;
      if (code) lookup(code);
    }
  });
  app.addEventListener("click", function (e) {
    var b;
    if ((b = e.target.closest("[data-reason]"))) {
      S.reason = b.getAttribute("data-reason");
      app.querySelectorAll("[data-reason]").forEach(function (x) { x.classList.toggle("on", x === b); });
      app.querySelector("[data-scan]").focus();
      return;
    }
    if ((b = e.target.closest("[data-pick]"))) {
      add(S.results[Number(b.getAttribute("data-pick"))]);
      var box = app.querySelector("[data-results]"); box.hidden = true;
      var scan = app.querySelector("[data-scan]"); scan.value = ""; scan.focus();
      return;
    }
    var row = e.target.closest("[data-n]");
    if (row && (b = e.target.closest("[data-step]"))) {
      var l = S.lines[Number(row.getAttribute("data-n"))];
      l.quantity = Math.max(1, (Number(l.quantity) || 0) + Number(b.getAttribute("data-step")));
      row.querySelector("[data-qty]").value = l.quantity;
      row.classList.toggle("is-short", l.quantity > l.available);
      renderTotals();
      return;
    }
    if (row && e.target.closest("[data-remove]")) {
      S.lines.splice(Number(row.getAttribute("data-n")), 1);
      if (!S.lines.length) render(); else { renderLines(); renderTotals(); }
      return;
    }
    if ((b = e.target.closest("[data-submit]"))) submit(b.getAttribute("data-submit") === "1");
  });

  function submit(approve) {
    if (S.busy || !S.lines.length) return;
    S.busy = true; renderTotals();
    api(cfg.urls.post, {
      location: S.loc, note: S.note, approve: approve,
      lines: S.lines.map(function (l) { return { variant_id: l.variant_id, quantity: Number(l.quantity), reason: l.reason, batch: l.batch, expiry: l.expiry || null, note: l.note }; }),
    }).then(function (j) { S.lines = []; window.location.href = j.data.url; })
      .catch(function (e) { S.busy = false; renderTotals(); toast(e.message, true); });
  }

  window.addEventListener("beforeunload", function (e) { if (S.lines.length && !S.busy) { e.preventDefault(); e.returnValue = ""; } });
  render();
})();
