/*
 * NutriZone Admin -- dispatcher board (templates/admin/ordering/ordermodel/board.html).
 * Renders board/data/ as Kanban columns; a card moves one step forward by drag & drop or its button
 * (POST board/<id>/move/); dropping onto "With the courier" first asks where the parcel leaves from.
 * Auto-refreshes every 30 s while the tab is visible and nothing is being dragged.
 */
(function () {
  "use strict";

  var root = document.querySelector("[data-nzb]");
  if (!root) return;
  var T = JSON.parse((document.getElementById("nzb-i18n") || {}).textContent || "{}");
  var boardEl = root.querySelector("[data-nzb-board]");
  var canChange = root.getAttribute("data-can-change") === "1";
  var ZERO = "00000000-0000-0000-0000-000000000000";
  var state = { data: null, q: "", city: "", late: false, dragging: null, busy: false };
  var REFRESH_MS = 30000;
  var timer = null;

  function csrf() { var i = root.querySelector("input[name=csrfmiddlewaretoken]"); return i ? i.value : ""; }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function url(attr, id) { return root.getAttribute(attr).replace(ZERO, id); }

  function toast(text, isError) {
    var el = root.querySelector("[data-nzp-toast]");
    if (!el) return;
    el.textContent = text; el.classList.toggle("is-error", !!isError); el.hidden = false;
    clearTimeout(toast.t); toast.t = setTimeout(function () { el.hidden = true; }, 2600);
  }

  function age(min) {
    if (min < 60) return min + " " + T.min;
    if (min < 1440) return Math.floor(min / 60) + " " + T.h;
    return Math.floor(min / 1440) + " " + T.d;
  }

  /* ---------------- data ---------------- */
  function load(quiet) {
    if (state.busy) return Promise.resolve();
    return fetch(root.getAttribute("data-url-data"), { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (data) {
        state.data = data;
        fillSummary(data);
        fillCities(data.cities || []);
        render();
        var u = root.querySelector("[data-nzb-updated]"); if (u) u.textContent = data.updated;
        root.querySelector("[data-nzb-live]").classList.remove("is-error");
      })
      .catch(function () { if (!quiet) toast(T.error, true); root.querySelector("[data-nzb-live]").classList.add("is-error"); });
  }

  function fillSummary(data) {
    Object.keys(data.summary || {}).forEach(function (k) {
      var el = root.querySelector('[data-nzb-sum="' + k + '"]');
      if (el) el.textContent = data.summary[k];
    });
  }

  function fillCities(cities) {
    var sel = root.querySelector("[data-nzb-city]");
    var current = sel.value;
    var known = Array.prototype.map.call(sel.options, function (o) { return o.value; });
    cities.forEach(function (c) { if (known.indexOf(c) === -1) { var o = document.createElement("option"); o.value = c; o.textContent = c; sel.appendChild(o); } });
    sel.value = current;
  }

  function matches(card) {
    if (state.late && card.sla !== "late") return false;
    if (state.city && card.city.indexOf(state.city) !== 0) return false;
    if (!state.q) return true;
    var q = state.q.toLowerCase(), digits = q.replace(/\D/g, "");
    return card.number.toLowerCase().indexOf(q) !== -1 || card.customer.toLowerCase().indexOf(q) !== -1 ||
      (digits.length >= 3 && card.phone.replace(/\D/g, "").indexOf(digits) !== -1);
  }

  /* ---------------- render ---------------- */
  function cardHtml(c, col) {
    var thumbs = c.thumbs.map(function (src) { return src ? '<img src="' + esc(src) + '" alt="" loading="lazy">' : '<span class="ph"><i class="fas fa-box"></i></span>'; }).join("") + (c.more ? '<span class="ph">+' + c.more + "</span>" : "");
    var flags = "";
    if (c.short) flags += '<span class="nzb-flag is-short" title="' + esc(T.short) + '"><i class="fas fa-triangle-exclamation"></i> ' + c.short + "</span>";
    if (c.requests) flags += '<span class="nzb-flag is-req" title="' + esc(T.requests) + '"><i class="fas fa-rotate-left"></i></span>';
    if (c.comment) flags += '<span class="nzb-flag" title="' + esc(T.comment) + '"><i class="fas fa-comment-dots"></i></span>';
    if (c.note) flags += '<span class="nzb-flag" title="' + esc(T.note) + '"><i class="fas fa-note-sticky"></i></span>';
    if (c.coins) flags += '<span class="nzb-flag is-coin" title="' + esc(T.coins) + '"><i class="fas fa-coins"></i></span>';
    var next = col.next && canChange ? '<button type="button" class="nzb-next" data-next="' + col.next + '"><i class="fas fa-arrow-right"></i> ' + esc(T.next[col.next]) + "</button>" : "";
    return (
      '<article class="nzb-card sla-' + c.sla + '" draggable="' + (col.next && canChange ? "true" : "false") + '" data-id="' + c.id + '" data-col="' + col.key + '" data-number="' + esc(c.number) + '" tabindex="0">' +
        '<header><a class="nzb-num" href="' + esc(c.url) + '">' + esc(c.number) + '</a><span class="nzb-age" title="' + esc(c.placed) + '"><i class="fas fa-clock"></i> ' + age(c.minutes) + "</span></header>" +
        '<div class="nzb-who"><b>' + esc(c.customer) + "</b>" + (c.phone ? '<a href="tel:' + esc(c.phone) + '">' + esc(c.phone) + "</a>" : "") + "</div>" +
        (c.city ? '<div class="nzb-city"><i class="fas fa-location-dot"></i> ' + esc(c.city) + (c.has_map ? ' <i class="fas fa-map-pin nzb-pin"></i>' : "") + "</div>" : "") +
        '<div class="nzb-items"><span class="nzb-thumbs">' + thumbs + '</span><span class="nzb-first" title="' + esc(c.first_item) + '">' + esc(c.first_item) + "</span></div>" +
        '<footer><span class="nzb-total"><b>' + esc(c.total) + "</b> <small>· " + c.units + " " + esc(T.items) + "</small></span>" + (flags ? '<span class="nzb-flags">' + flags + "</span>" : "") + "</footer>" +
        next +
      "</article>"
    );
  }

  function render() {
    var data = state.data;
    if (!data) return;
    var filtered = state.q || state.city || state.late;
    boardEl.innerHTML = data.columns.map(function (col) {
      var cards = col.cards.filter(matches);
      var empty = col.cards.length === 0 ? (col.key === "delivered" ? T.emptyDelivered : T.empty) : T.noFilter;
      return (
        '<section class="nzb-col" style="--c:' + col.color + '" data-col="' + col.key + '" aria-label="' + esc(col.label) + '">' +
          '<header class="nzb-col-head"><span class="nzb-col-icon"><i class="fas ' + col.icon + '"></i></span>' +
            '<div><h3>' + esc(col.label) + ' <b class="nzb-count">' + (filtered ? cards.length + "/" : "") + col.count + "</b></h3><small>" + esc(col.hint) + "</small></div>" +
            '<span class="nzb-col-sum">' + esc(col.sum) + (col.late ? ' <em title="' + esc(T.late) + '"><i class="fas fa-fire"></i> ' + col.late + "</em>" : "") + "</span>" +
          "</header>" +
          '<div class="nzb-drop" data-drop="' + col.key + '">' +
            (cards.length ? cards.map(function (c) { return cardHtml(c, col); }).join("") : '<p class="nzb-empty">' + esc(empty) + "</p>") +
          "</div>" +
        "</section>"
      );
    }).join("");
  }

  /* ---------------- moves ---------------- */
  var ORDER = ["pending_payment", "confirmed", "processing", "shipped", "delivered"];
  function nextCol(col) { var i = ORDER.indexOf(col); return i >= 0 && i < ORDER.length - 1 ? ORDER[i + 1] : null; }
  function colDef(key) { return state.data.columns.filter(function (c) { return c.key === key; })[0]; }

  function post(id, body) {
    state.busy = true;
    return fetch(url("data-url-move", id), {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf(), "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify(body),
    }).then(function (r) { return r.json().catch(function () { return { ok: false }; }); })
      .then(function (res) {
        state.busy = false;
        if (res.ok) toast(res.message); else toast(res.error || T.error, true);
        return load(true);
      })
      .catch(function () { state.busy = false; toast(T.error, true); return load(true); });
  }

  function move(card) {
    var col = card.getAttribute("data-col");
    var action = (colDef(col) || {}).next;
    if (!action) return;
    if (action === "ship") { openShip(card); return; }
    card.classList.add("is-moving");
    post(card.getAttribute("data-id"), { action: action });
  }

  /* ship-from dialog */
  var dlg = document.getElementById("nzb-ship");
  var shipFor = null;
  function openShip(card) {
    shipFor = card.getAttribute("data-id");
    dlg.querySelector("[data-nzb-ship-number]").textContent = card.getAttribute("data-number");
    var box = dlg.querySelector("[data-nzb-ship-locs]");
    box.innerHTML = '<p class="nzb-loading"><i class="fas fa-spinner fa-spin"></i></p>';
    if (dlg.showModal) dlg.showModal();
    fetch(url("data-url-ship", shipFor), { credentials: "same-origin" }).then(function (r) { return r.json(); }).then(function (res) {
      var locs = res.locations || [];
      if (!locs.length) { box.innerHTML = '<p class="nzp-muted">' + esc(T.noLocations) + "</p>"; return; }
      box.innerHTML = locs.map(function (l) {
        var miss = l.missing.map(function (m) { return esc(m.name) + " " + m.have + "/" + m.need; }).join("; ");
        return '<label class="nzd-loc' + (l.ok ? "" : " is-short") + '"><input type="radio" name="store_id" value="' + l.id + '" data-ok="' + (l.ok ? 1 : 0) + '"' + (l.default ? " checked" : "") + ">" +
          '<span class="nzd-loc-body"><span class="nzd-loc-name"><i class="fas ' + (l.is_warehouse ? "fa-warehouse" : "fa-store") + '"></i> ' + esc(l.name) + (l.reserved_here ? " <em>" + esc(T.reserved) + "</em>" : "") + "</span>" +
          (l.ok ? '<span class="nzd-loc-ok"><i class="fas fa-circle-check"></i> ' + esc(T.allIn) + "</span>" : '<span class="nzd-loc-bad"><i class="fas fa-triangle-exclamation"></i> ' + l.missing.length + " " + esc(T.short_n) + '</span><span class="nzd-loc-miss">' + miss + "</span>") +
          "</span></label>";
      }).join("");
      syncShipWarn();
    });
  }
  function syncShipWarn() {
    var chosen = dlg.querySelector("input[name=store_id]:checked");
    dlg.querySelector("[data-nzb-ship-warn]").hidden = !chosen || chosen.getAttribute("data-ok") === "1";
  }
  dlg.addEventListener("change", syncShipWarn);
  dlg.querySelector("[data-nzb-ship-cancel]").addEventListener("click", function () { dlg.close(); shipFor = null; });
  dlg.addEventListener("click", function (e) { if (e.target === dlg) dlg.close(); });
  dlg.querySelector("[data-nzb-ship-form]").addEventListener("submit", function (e) {
    e.preventDefault();
    var chosen = dlg.querySelector("input[name=store_id]:checked");
    var id = shipFor;
    dlg.close();
    if (id) post(id, { action: "ship", store_id: chosen ? chosen.value : null });
  });

  /* drag & drop */
  boardEl.addEventListener("dragstart", function (e) {
    var card = e.target.closest && e.target.closest(".nzb-card");
    if (!card || card.getAttribute("draggable") !== "true") return;
    state.dragging = card;
    card.classList.add("is-dragging");
    e.dataTransfer.effectAllowed = "move";
    try { e.dataTransfer.setData("text/plain", card.getAttribute("data-id")); } catch (err) { /* ignore */ }
    var target = boardEl.querySelector('[data-drop="' + nextCol(card.getAttribute("data-col")) + '"]');
    if (target) target.classList.add("is-target");
  });
  boardEl.addEventListener("dragend", function () {
    if (state.dragging) state.dragging.classList.remove("is-dragging");
    state.dragging = null;
    Array.prototype.forEach.call(boardEl.querySelectorAll(".is-target, .is-over"), function (el) { el.classList.remove("is-target", "is-over"); });
  });
  boardEl.addEventListener("dragover", function (e) {
    var drop = e.target.closest && e.target.closest("[data-drop]");
    if (!drop || !state.dragging) return;
    if (drop.getAttribute("data-drop") === nextCol(state.dragging.getAttribute("data-col"))) { e.preventDefault(); drop.classList.add("is-over"); }
  });
  boardEl.addEventListener("dragleave", function (e) {
    var drop = e.target.closest && e.target.closest("[data-drop]");
    if (drop && !drop.contains(e.relatedTarget)) drop.classList.remove("is-over");
  });
  boardEl.addEventListener("drop", function (e) {
    var drop = e.target.closest && e.target.closest("[data-drop]");
    var card = state.dragging;
    if (!drop || !card) return;
    e.preventDefault();
    if (drop.getAttribute("data-drop") !== nextCol(card.getAttribute("data-col"))) { toast(T.oneStep, true); return; }
    move(card);
  });

  boardEl.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest(".nzb-next");
    if (btn) { e.preventDefault(); move(btn.closest(".nzb-card")); }
  });
  boardEl.addEventListener("keydown", function (e) {
    var card = e.target.closest && e.target.closest(".nzb-card");
    if (!card || e.target !== card) return;
    if (e.key === "Enter") { var a = card.querySelector(".nzb-num"); if (a) window.location.href = a.href; }
  });

  /* filters + refresh */
  root.querySelector("[data-nzb-q]").addEventListener("input", function (e) { state.q = e.target.value.trim(); render(); });
  root.querySelector("[data-nzb-city]").addEventListener("change", function (e) { state.city = e.target.value; render(); });
  root.querySelector("[data-nzb-late]").addEventListener("change", function (e) { state.late = e.target.checked; render(); });
  root.querySelector("[data-nzb-refresh]").addEventListener("click", function () { load(); });

  function schedule() {
    clearInterval(timer);
    timer = setInterval(function () {
      if (document.hidden || state.dragging || (dlg && dlg.open)) return;
      load(true);
    }, REFRESH_MS);
  }
  document.addEventListener("visibilitychange", function () {
    root.querySelector("[data-nzb-live]").classList.toggle("is-paused", document.hidden);
    if (!document.hidden) load(true);
  });

  load();
  schedule();
})();
