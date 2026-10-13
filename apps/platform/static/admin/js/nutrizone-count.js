/*
 * NutriZone Admin -- stock count workspace (templates/admin/wms/count_workspace.html).
 * Counting: scan a barcode (one scan = one unit) or type a count; counts autosave as absolute numbers.
 * Review: a reason for every difference, then post (managers). Posted: the report (print / Excel).
 */
(function () {
  "use strict";
  var app = document.getElementById("wx-count");
  if (!app) return;
  var cfg = JSON.parse(document.getElementById("wx-config").textContent);
  var L = JSON.parse(document.getElementById("wx-i18n").textContent);
  var dlg = document.getElementById("wx-dialog");
  var T = null;
  var S = { tab: "all", q: "", pending: {}, reasons: {}, last: null, saveTimer: null, reasonTimer: null, busy: false };

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function csrf() { var i = document.querySelector("input[name=csrfmiddlewaretoken]"); return i ? i.value : ""; }
  function api(url, body) {
    var opts = { credentials: "same-origin", headers: { "X-CSRFToken": csrf(), "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" } };
    if (body !== undefined) { opts.method = "POST"; opts.body = JSON.stringify(body); }
    return fetch(url, opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok || j.ok === false) { var e = new Error((j.error && j.error.message) || L.error); e.code = j.error && j.error.code; e.details = j.error && j.error.details; throw e; } return j; });
    });
  }
  function act(name, body) { return api(cfg.urls.action.replace("__", name), body || {}); }
  function toast(text, bad) {
    var el = document.querySelector("[data-nzp-toast]");
    el.textContent = text; el.classList.toggle("is-error", !!bad); el.hidden = false;
    clearTimeout(toast.t); toast.t = setTimeout(function () { el.hidden = true; }, bad ? 4500 : 2200);
  }
  function beep(ok) {
    try { var c = new (window.AudioContext || window.webkitAudioContext)(), o = c.createOscillator(), g = c.createGain(); o.frequency.value = ok ? 880 : 220; g.gain.value = 0.05; o.connect(g); g.connect(c.destination); o.start(); setTimeout(function () { o.stop(); c.close(); }, ok ? 90 : 260); } catch (e) { /* no audio */ }
  }
  function item(id) { return T.items.filter(function (i) { return i.id === id; })[0]; }
  function diffOf(i) { return i.counted == null || i.expected == null ? null : i.counted - i.expected; }

  /* ---------------- data ---------------- */
  function adopt(data) {
    T = data;
    // keep unsaved local counts on top of what the server sent
    Object.keys(S.pending).forEach(function (id) { var i = item(id); if (i) i.counted = S.pending[id]; });
    T.items.forEach(function (i) { if (!S.reasons[i.id]) S.reasons[i.id] = { reason: i.reason || "", note: i.note || "" }; });
    render();
  }
  function load() { return api(cfg.urls.data).then(function (j) { adopt(j.data); }).catch(function (e) { app.innerHTML = '<div class="nzp-alert nzp-alert-error"><i class="fas fa-circle-exclamation"></i><div>' + esc(e.message) + "</div></div>"; }); }

  function scheduleSave() {
    setSave(L.saving);
    clearTimeout(S.saveTimer);
    S.saveTimer = setTimeout(saveNow, 700);
  }
  function saveNow() {
    var batch = S.pending; S.pending = {};
    if (!Object.keys(batch).length) return Promise.resolve();
    return act("save_counts", { counts: batch }).then(function (j) { T = j.data; Object.keys(S.pending).forEach(function (id) { var i = item(id); if (i) i.counted = S.pending[id]; }); setSave(L.saved); renderSummary(); renderDiffCells(); })
      .catch(function (e) { Object.keys(batch).forEach(function (k) { if (!(k in S.pending)) S.pending[k] = batch[k]; }); setSave(""); toast(e.message, true); });
  }
  function setSave(t) { var el = app.querySelector("[data-wx-save]"); if (el) el.textContent = t; }
  function setCount(i, qty) {
    i.counted = qty; S.pending[i.id] = qty; scheduleSave();
  }

  /* ---------------- render ---------------- */
  function render() {
    app.innerHTML = '<div data-wx-head></div><div data-wx-summary></div><div data-wx-body></div>';
    renderHead(); renderSummary(); renderBody();
  }

  function renderHead() {
    var st = T.status, p = cfg.perms, actions = "";
    if (st === "counting" && p.count) actions = '<button class="nzp-btn nzp-btn-danger-ghost" data-do="cancel"><i class="fas fa-ban"></i> ' + esc(L.cancel) + '</button><button class="nzp-btn nzp-btn-primary" data-do="submit"><i class="fas fa-paper-plane"></i> ' + esc(L.submit) + "</button>";
    if (st === "review") actions = (p.count ? '<button class="nzp-btn nzp-btn-danger-ghost" data-do="cancel"><i class="fas fa-ban"></i> ' + esc(L.cancel) + '</button><button class="nzp-btn nzp-btn-ghost" data-do="recount"><i class="fas fa-rotate-left"></i> ' + esc(L.recount) + "</button>" : "") + (p.post ? '<button class="nzp-btn nzp-btn-primary" data-do="post"><i class="fas fa-check-double"></i> ' + esc(L.post) + "</button>" : "");
    if (st === "posted" || st === "review") actions += '<a class="nzp-btn nzp-btn-ghost" href="' + cfg.urls.act + '" target="_blank" rel="noopener"><i class="fas fa-print"></i> ' + esc(L.act) + '</a><a class="nzp-btn nzp-btn-ghost" href="' + cfg.urls.export + '"><i class="fas fa-file-excel"></i> Excel</a>';
    var meta = [T.created_at + " · " + esc(T.created_by)];
    if (T.posted_at) meta.push(L.postedAt + " " + T.posted_at + " · " + esc(T.posted_by));
    app.querySelector("[data-wx-head]").innerHTML =
      '<header class="nzp-hero"><div class="nzp-hero-main"><a class="nzp-back" href="' + cfg.urls.list + '" aria-label="' + esc(L.back) + '"><i class="fas fa-arrow-left"></i></a><div>' +
      '<h2 class="nzd-number">' + esc(T.number) + ' <span class="nzd-pill" style="--t:' + T.color + '"><i class="fas ' + T.icon + '"></i> ' + esc(T.status_label) + "</span></h2>" +
      '<p><span><i class="fas ' + (T.store.kind === "warehouse" ? "fa-warehouse" : "fa-store") + '" style="color:' + esc(T.store.color) + '"></i> ' + esc(T.store.name) + "</span><span>" + esc(T.scope_label) + "</span>" + (T.blind ? '<span><i class="fas fa-eye-slash"></i> ' + esc(L.blind) + "</span>" : "") + "<span>" + meta.join(" · ") + "</span></p></div></div>" +
      '<div class="nzp-hero-actions">' + actions + "</div></header>" +
      (T.status === "cancelled" ? '<div class="nzp-alert nzp-alert-error"><i class="fas fa-ban"></i><div>' + esc(L.cancelledAt) + " " + esc(T.cancelled_at || "") + (T.cancel_reason ? " — " + esc(T.cancel_reason) : "") + "</div></div>" : "") +
      (T.hidden ? '<div class="nzp-note nzp-note-info"><i class="fas fa-eye-slash"></i> ' + esc(L.blindNote) + "</div>" : "");
  }

  function renderSummary() {
    var s = T.summary, box = app.querySelector("[data-wx-summary]");
    if (!box) return;
    var cards = '<div class="nzp-stat" style="--c:#0ea5e9"><i class="fas fa-list-check"></i><div><b>' + s.counted + " / " + s.lines + "</b><span>" + esc(L.counted) + "</span></div></div>";
    if (!T.hidden) {
      cards += '<div class="nzp-stat" style="--c:#10b981"><i class="fas fa-bullseye"></i><div><b>' + s.accuracy + "%</b><span>" + esc(L.accuracy) + " · " + s.matched + " " + esc(L.matched) + "</span></div></div>" +
        '<div class="nzp-stat" style="--c:#e11d48"><i class="fas fa-arrow-trend-down"></i><div><b>−' + s.shortage_units + ' <small>' + esc(L.units) + "</small></b><span>" + esc(L.shortage) + " · " + s.shortage_value + " " + esc(L.som) + "</span></div></div>" +
        '<div class="nzp-stat" style="--c:#6366f1"><i class="fas fa-arrow-trend-up"></i><div><b>+' + s.excess_units + ' <small>' + esc(L.units) + "</small></b><span>" + esc(L.excess) + " · " + s.excess_value + " " + esc(L.som) + "</span></div></div>";
    } else {
      cards += '<div class="nzp-stat" style="--c:#6366f1"><i class="fas fa-cubes"></i><div><b>' + s.counted_units + "</b><span>" + esc(L.unitsCounted) + "</span></div></div>";
    }
    box.innerHTML = '<div class="wx-progress-card"><div class="wx-progress lg"><i style="width:' + s.progress + '%"></i></div><span>' + s.progress + "% " + esc(L.done) + '</span><em data-wx-save></em></div><div class="nzp-stats">' + cards + "</div>";
  }

  function rowsFiltered() {
    var q = S.q.toLowerCase();
    return T.items.filter(function (i) {
      var d = diffOf(i);
      if (S.tab === "uncounted" && i.counted != null) return false;
      if (S.tab === "diff" && !(d)) return false;
      if (S.tab === "match" && d !== 0) return false;
      if (!q) return true;
      return (i.name || "").toLowerCase().indexOf(q) !== -1 || (i.sku || "").toLowerCase().indexOf(q) !== -1 || (i.barcode || "").indexOf(q) !== -1;
    }).sort(function (a, b) {
      if (T.status !== "counting") { var da = Math.abs(diffOf(a) || 0), db = Math.abs(diffOf(b) || 0); if (da !== db) return db - da; }
      return 0;
    });
  }

  function tabsHtml() {
    var n = { all: T.items.length, uncounted: 0, diff: 0, match: 0 };
    T.items.forEach(function (i) { var d = diffOf(i); if (i.counted == null) n.uncounted++; else if (d) n.diff++; else if (d === 0) n.match++; });
    var defs = [["all", L.tabAll, "#64748b"], ["uncounted", L.tabUncounted, "#0ea5e9"]];
    if (!T.hidden) defs.push(["diff", L.tabDiff, "#e11d48"], ["match", L.tabMatch, "#10b981"]);
    return '<nav class="nzp-tabs">' + defs.map(function (d) { return '<button type="button" class="nzp-tab' + (S.tab === d[0] ? " on" : "") + '" style="--t:' + d[2] + '" data-tab="' + d[0] + '">' + esc(d[1]) + " <b>" + n[d[0]] + "</b></button>"; }).join("") + "</nav>";
  }

  function renderBody() {
    var body = app.querySelector("[data-wx-body]");
    var counting = T.status === "counting" && cfg.perms.count;
    var review = T.status === "review";
    var scan = counting ? (
      '<section class="nzp-card wx-scanbox"><div class="wx-scan"><i class="fas fa-barcode"></i><input id="wx-scan" autocomplete="off" placeholder="' + esc(L.scanPh) + '" aria-label="' + esc(L.scanPh) + '"><span>' + esc(L.scanHint) + "</span></div>" +
      '<div class="wx-last" data-wx-last>' + lastHtml() + "</div></section>") : "";
    var head = '<div class="wx-tr wx-th"><span>' + esc(L.product) + "</span>" + (T.hidden ? "" : '<span class="r">' + esc(L.system) + "</span>") + '<span class="c">' + esc(L.counted) + "</span>" + (T.hidden ? "" : '<span class="r">' + esc(L.diff) + "</span>") + (review || T.status === "posted" ? "<span>" + esc(L.reason) + "</span>" : "") + "</div>";
    var rows = rowsFiltered().map(function (i) { return rowHtml(i, counting, review); }).join("");
    body.innerHTML = scan +
      '<section class="nzp-card wx-list"><div class="wx-list-tools">' + tabsHtml() + '<label class="nzp-search"><i class="fas fa-magnifying-glass"></i><input type="search" data-wx-q value="' + esc(S.q) + '" placeholder="' + esc(L.searchPh) + '"></label></div>' +
      '<div class="wx-table' + (T.hidden ? " is-hidden" : "") + (review || T.status === "posted" ? " has-reason" : "") + '">' + head + (rows || '<p class="nzb-empty">' + esc(L.nothing) + "</p>") + "</div></section>";
    var s = document.getElementById("wx-scan"); if (s) s.focus();
  }

  function rowHtml(i, counting, review) {
    var d = diffOf(i);
    var dcls = d == null ? "" : d < 0 ? "is-short" : d > 0 ? "is-excess" : "is-ok";
    var counted = counting
      ? '<span class="wx-stepper"><button type="button" data-dec aria-label="−">−</button><input type="number" min="0" inputmode="numeric" data-qty value="' + (i.counted == null ? "" : i.counted) + '" placeholder="—" aria-label="' + esc(L.counted) + '"><button type="button" data-inc aria-label="+">+</button></span>'
      : '<b class="wx-num">' + (i.counted == null ? "—" : i.counted) + "</b>";
    var reason = "";
    if (review || T.status === "posted") {
      if (d) {
        var r = S.reasons[i.id] || {};
        reason = review && cfg.perms.count
          ? '<span class="wx-reason"><select data-reason class="nzp-select' + (r.reason ? "" : " is-missing") + '"><option value="">' + esc(L.chooseReason) + "</option>" + cfg.reasons.map(function (o) { return '<option value="' + o[0] + '"' + (r.reason === o[0] ? " selected" : "") + ">" + esc(o[1]) + "</option>"; }).join("") + '</select><input class="nzd-input" data-note value="' + esc(r.note || "") + '" placeholder="' + esc(L.notePh) + '"></span>'
          : "<span class='wx-reason-text'>" + esc((cfg.reasons.filter(function (o) { return o[0] === i.reason; })[0] || ["", "—"])[1]) + (i.note ? "<small>" + esc(i.note) + "</small>" : "") + (T.status === "posted" && i.adjusted !== d ? "<small>" + esc(L.clamped) + " " + i.adjusted + "</small>" : "") + "</span>";
      } else reason = "<span></span>";
    }
    return '<div class="wx-tr ' + dcls + (i.counted == null ? " is-uncounted" : "") + '" data-id="' + i.id + '">' +
      '<span class="wx-prod">' + (i.image_url ? '<img src="' + esc(i.image_url) + '" alt="" loading="lazy">' : '<span class="ph"><i class="fas fa-box"></i></span>') + "<span><b>" + esc(i.name) + "</b><small>" + esc(i.sku) + (i.barcode ? " · " + esc(i.barcode) : "") + (i.size ? " · " + esc(i.size) : "") + (i.added ? ' · <em class="wx-added">' + esc(L.added) + "</em>" : "") + "</small></span></span>" +
      (T.hidden ? "" : '<span class="r wx-num">' + (i.expected == null ? "—" : i.expected) + "</span>") +
      '<span class="c">' + counted + "</span>" +
      (T.hidden ? "" : '<span class="r" data-diff>' + diffHtml(i) + "</span>") +
      reason + "</div>";
  }
  function diffHtml(i) {
    var d = diffOf(i);
    if (d == null) return '<span class="wx-muted">—</span>';
    if (d === 0) return '<span class="wx-badge ok"><i class="fas fa-check"></i></span>';
    return '<span class="wx-badge ' + (d < 0 ? "short" : "excess") + '">' + (d > 0 ? "+" : "−") + Math.abs(d) + "</span>" + (i.value && i.value !== "0" ? "<small>" + esc(i.value) + " " + esc(L.som) + "</small>" : "");
  }
  function renderTabs() {
    var nav = app.querySelector(".wx-list-tools .nzp-tabs");
    if (nav) nav.outerHTML = tabsHtml();
  }
  function renderDiffCells() {
    renderTabs();
    app.querySelectorAll(".wx-tr[data-id]").forEach(function (row) {
      var i = item(row.getAttribute("data-id"));
      if (!i) return;
      var cell = row.querySelector("[data-diff]");
      if (cell) cell.innerHTML = diffHtml(i);
      var d = diffOf(i);
      row.classList.toggle("is-uncounted", i.counted == null);
      row.classList.toggle("is-short", d != null && d < 0);
      row.classList.toggle("is-excess", d != null && d > 0);
      row.classList.toggle("is-ok", d === 0);
    });
  }
  function lastHtml() {
    var i = S.last && item(S.last);
    if (!i) return '<p class="wx-muted"><i class="fas fa-hand-pointer"></i> ' + esc(L.lastEmpty) + "</p>";
    return (i.image_url ? '<img src="' + esc(i.image_url) + '" alt="">' : '<span class="ph"><i class="fas fa-box"></i></span>') +
      "<span><small>" + esc(L.lastScanned) + "</small><b>" + esc(i.name) + "</b><em>" + esc(i.sku) + "</em></span>" +
      '<strong class="wx-last-count">' + (i.counted == null ? 0 : i.counted) + "</strong>";
  }

  /* ---------------- scanning ---------------- */
  var scanLock = false;
  function onScan(raw) {
    var code = (raw || "").trim();
    if (!code || scanLock) return;
    scanLock = true; setTimeout(function () { scanLock = false; }, 120); // CR+LF scanners: one scan, one unit
    var low = code.toLowerCase();
    var hit = T.items.filter(function (i) { return i.barcode === code || (i.sku || "").toLowerCase() === low; })[0];
    if (hit) return countOne(hit);
    act("scan", { code: code }).then(function (j) {
      adopt(j.data);
      var i = T.items.filter(function (x) { return x.variant_id === j.variant_id; })[0];
      if (i) { if (j.added) toast(L.addedToast + ": " + i.name); countOne(i); }
    }).catch(function (e) { beep(false); toast(e.message + " (" + code + ")", true); });
  }
  function countOne(i) {
    setCount(i, (i.counted || 0) + 1);
    S.last = i.id; beep(true);
    var last = app.querySelector("[data-wx-last]"); if (last) last.innerHTML = lastHtml();
    var row = app.querySelector('.wx-tr[data-id="' + i.id + '"]');
    if (row) { var inp = row.querySelector("[data-qty]"); if (inp) inp.value = i.counted; row.classList.remove("flash"); void row.offsetWidth; row.classList.add("flash"); row.scrollIntoView({ block: "nearest" }); }
    renderDiffCells(); renderSummaryLite();
  }
  function renderSummaryLite() { var save = app.querySelector("[data-wx-save]"); var txt = save ? save.textContent : ""; renderSummary(); setSave(txt); }

  /* ---------------- events ---------------- */
  app.addEventListener("keydown", function (e) {
    if (e.target.id === "wx-scan" && e.key === "Enter") { e.preventDefault(); var v = e.target.value; e.target.value = ""; onScan(v); }
  });
  app.addEventListener("input", function (e) {
    if (e.target.matches("[data-wx-q]")) { S.q = e.target.value.trim(); var pos = e.target.selectionStart; renderBody(); var q = app.querySelector("[data-wx-q]"); q.focus(); q.setSelectionRange(pos, pos); }
  });
  app.addEventListener("change", function (e) {
    var row = e.target.closest(".wx-tr[data-id]"); var i = row && item(row.getAttribute("data-id"));
    if (e.target.matches("[data-qty]") && i) { var v = e.target.value.trim(); setCount(i, v === "" ? null : Math.max(0, parseInt(v, 10) || 0)); renderDiffCells(); renderSummaryLite(); }
    if ((e.target.matches("[data-reason]") || e.target.matches("[data-note]")) && i) {
      var r = S.reasons[i.id] = S.reasons[i.id] || {};
      if (e.target.matches("[data-reason]")) { r.reason = e.target.value; e.target.classList.toggle("is-missing", !r.reason); } else r.note = e.target.value;
      clearTimeout(S.reasonTimer); S.reasonTimer = setTimeout(function () { var m = {}; m[i.id] = r; act("save_reasons", { reasons: m }).catch(function (err) { toast(err.message, true); }); }, 400);
    }
  });
  app.addEventListener("click", function (e) {
    var tab = e.target.closest("[data-tab]"); if (tab) { S.tab = tab.getAttribute("data-tab"); renderBody(); return; }
    var row = e.target.closest(".wx-tr[data-id]"); var i = row && item(row.getAttribute("data-id"));
    if (i && e.target.closest("[data-inc]")) { setCount(i, (i.counted || 0) + 1); row.querySelector("[data-qty]").value = i.counted; renderDiffCells(); renderSummaryLite(); return; }
    if (i && e.target.closest("[data-dec]")) { setCount(i, Math.max(0, (i.counted || 0) - 1)); row.querySelector("[data-qty]").value = i.counted; renderDiffCells(); renderSummaryLite(); return; }
    var btn = e.target.closest("[data-do]"); if (btn) doAction(btn.getAttribute("data-do"), btn);
  });

  /* ---------------- dialogs + actions ---------------- */
  function ask(html, okLabel, danger) {
    return new Promise(function (resolve) {
      var form = dlg.querySelector("[data-wx-dialog]");
      form.innerHTML = html + '<footer><button type="button" class="nzp-btn nzp-btn-ghost" data-x>' + esc(L.back) + '</button><button type="submit" class="nzp-btn ' + (danger ? "nzd-btn-danger" : "nzp-btn-primary") + '">' + esc(okLabel) + "</button></footer>";
      function done(v) { form.onsubmit = null; dlg.close(); resolve(v); }
      form.querySelector("[data-x]").onclick = function () { done(null); };
      form.onsubmit = function (ev) { ev.preventDefault(); var data = {}; form.querySelectorAll("input,textarea,select").forEach(function (f) { data[f.name] = f.type === "checkbox" ? f.checked : f.value; }); done(data); };
      dlg.showModal();
    });
  }
  function run(name, body, okText) {
    if (S.busy) return Promise.resolve();
    S.busy = true;
    return saveNow().then(function () { return act(name, body); }).then(function (j) { S.busy = false; S.tab = "all"; adopt(j.data); toast(okText); })
      .catch(function (e) { S.busy = false; var extra = e.details && e.details.names ? ": " + e.details.names.slice(0, 5).join(", ") : e.details && e.details.products ? ": " + e.details.products.slice(0, 5).join(", ") : ""; toast(e.message + extra, true); });
  }
  function doAction(name) {
    var s = T.summary;
    if (name === "submit") {
      var unc = s.lines - s.counted;
      return ask('<header><span class="nzd-dialog-icon is-ok"><i class="fas fa-paper-plane"></i></span><div><h3>' + esc(L.submitTitle) + "</h3><p>" + esc(L.submitText) + "</p></div></header>" +
        (unc ? '<label class="nzd-check is-warn"><input type="checkbox" name="zero"' + (T.scope === "full" ? " checked" : "") + "><span><b>" + esc(L.zeroTitle.replace("%s", unc)) + "</b><small>" + esc(L.zeroText) + "</small></span></label>" : ""), L.submit)
        .then(function (d) { if (d) run("submit", { uncounted_as_zero: !!d.zero }, L.submittedToast); });
    }
    if (name === "recount") return run("recount", {}, L.recountToast);
    if (name === "post") {
      var missing = T.items.filter(function (i) { var d = diffOf(i); return d && !((S.reasons[i.id] || {}).reason); }).length;
      return ask('<header><span class="nzd-dialog-icon is-ok"><i class="fas fa-check-double"></i></span><div><h3>' + esc(L.postTitle) + "</h3><p>" + esc(L.postText) + "</p></div></header>" +
        '<ul class="nzp-facts"><li><span>' + esc(L.shortage) + "</span><b class='wx-minus'>−" + s.shortage_units + " · " + s.shortage_value + " " + esc(L.som) + "</b></li><li><span>" + esc(L.excess) + "</span><b class='wx-plus'>+" + s.excess_units + " · " + s.excess_value + " " + esc(L.som) + "</b></li><li><span>" + esc(L.accuracy) + "</span><b>" + s.accuracy + "%</b></li></ul>" +
        (missing ? '<p class="nzd-ship-warn"><i class="fas fa-triangle-exclamation"></i> ' + esc(L.missingReasons.replace("%s", missing)) + "</p>" : ""), L.post)
        .then(function (d) { if (d) run("post", { reasons: S.reasons }, L.postedToast); });
    }
    if (name === "cancel") {
      return ask('<header><span class="nzd-dialog-icon"><i class="fas fa-ban"></i></span><div><h3>' + esc(L.cancelTitle) + "</h3><p>" + esc(L.cancelText) + '</p></div></header><label class="nzd-field-label">' + esc(L.reason) + '</label><input class="nzd-input" name="reason" maxlength="255">', L.cancel, true)
        .then(function (d) { if (d) run("cancel", { reason: d.reason || "" }, L.cancelledToast); });
    }
  }

  // keyboard-wedge scanner while focus is outside inputs
  var buf = "", lastKey = 0;
  document.addEventListener("keydown", function (e) {
    if (dlg.open || !T || T.status !== "counting") return;
    var tag = (e.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return;
    var now = Date.now();
    if (e.key === "Enter" && buf.length >= 4 && now - lastKey < 120) { e.preventDefault(); var code = buf; buf = ""; onScan(code); return; }
    if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) { buf = now - lastKey < 60 ? buf + e.key : e.key; lastKey = now; }
  });
  window.addEventListener("beforeunload", function (e) { if (Object.keys(S.pending).length) { e.preventDefault(); e.returnValue = ""; } });

  load();
})();
