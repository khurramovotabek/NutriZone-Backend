/*
 * NutriZone Admin -- branch-to-branch stock transfers (templates/admin/stock_transfers.html).
 * Route (from -> to), product search (smart search / barcode), a transfer list with
 * quantity steppers capped at the sender's stock, a confirm dialog, then one atomic POST.
 */
(function () {
  "use strict";

  var root = document.getElementById("nz-transfers");
  if (!root || !document.getElementById("nz-tr-source")) return;

  var T = JSON.parse(document.getElementById("nz-tr-i18n").textContent);
  var productsUrl = root.getAttribute("data-products-url");
  var createUrl = root.getAttribute("data-create-url");

  var $ = function (sel) { return root.querySelector(sel); };
  var sourceSel = $("#nz-tr-source");
  var destSel = $("#nz-tr-destination");
  var search = $("#nz-tr-search");
  var results = $('[data-role="results"]');
  var pager = $('[data-role="pager"]');
  var spinner = $('[data-role="spinner"]');
  var linesEl = $('[data-role="lines"]');
  var note = $("#nz-tr-note");
  var feedback = $('[data-role="feedback"]');
  var submitBtn = $('[data-action="review"]');
  var modal = $('[data-role="modal"]');
  var success = $('[data-role="success"]');

  var state = { lines: [], page: 1, query: "", reqId: 0, submitting: false };
  var lastRows = {};

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function fmt(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, " "); }
  function branchName(sel) { return sel.value ? sel.options[sel.selectedIndex].text : ""; }
  function csrf() {
    if (window.NZ_CSRF_TOKEN) return window.NZ_CSRF_TOKEN;
    var m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : "";
  }
  function routeReady() { return sourceSel.value && destSel.value && sourceSel.value !== destSel.value; }

  // ------------------------------------------------------------------ route
  function syncBranchMeta() {
    [[sourceSel, "source"], [destSel, "destination"]].forEach(function (pair) {
      var sel = pair[0];
      var meta = $('[data-role="' + pair[1] + '-meta"]');
      var opt = sel.options[sel.selectedIndex];
      meta.textContent = sel.value ? fmt(opt.getAttribute("data-units") || 0) + " " + T.units + " " + T.inStock : " ";
      $('[data-role="' + pair[1] + '-card"]').classList.toggle("is-set", !!sel.value);
    });
    // a branch can't be both sender and receiver
    Array.prototype.forEach.call(destSel.options, function (o) { o.disabled = !!o.value && o.value === sourceSel.value; });
    Array.prototype.forEach.call(sourceSel.options, function (o) { o.disabled = !!o.value && o.value === destSel.value; });

    var err = $('[data-role="route-error"]');
    var same = sourceSel.value && sourceSel.value === destSel.value;
    err.hidden = !same;
    err.textContent = same ? T.sameBranch : "";

    var pill = $('[data-role="route-pill"]');
    if (routeReady()) {
      pill.hidden = false;
      pill.innerHTML = "<span>" + esc(branchName(sourceSel)) + '</span><i class="fas fa-arrow-right" aria-hidden="true"></i><span>' + esc(branchName(destSel)) + "</span>";
    } else {
      pill.hidden = true;
    }
    search.disabled = !routeReady();
  }

  function onRouteChange(changedSource) {
    // stock caps belong to the sender -- a new sender empties the list
    if (changedSource && state.lines.length) state.lines = [];
    syncBranchMeta();
    renderLines();
    state.page = 1;
    if (routeReady()) { load(); if (!changedSource) search.focus(); }
    else results.innerHTML = placeholder("fa-route", T.chooseBranches);
  }

  sourceSel.addEventListener("change", function () { onRouteChange(true); });
  destSel.addEventListener("change", function () { onRouteChange(false); });
  $('[data-action="swap"]').addEventListener("click", function () {
    var s = sourceSel.value;
    sourceSel.value = destSel.value;
    destSel.value = s;
    onRouteChange(true);
  });

  // ------------------------------------------------------------------ search
  function placeholder(icon, text) {
    return '<div class="nz-tr-placeholder"><i class="fas ' + icon + '" aria-hidden="true"></i><p>' + esc(text) + "</p></div>";
  }

  function load() {
    if (!routeReady()) return;
    var id = ++state.reqId;
    spinner.hidden = false;
    var params = new URLSearchParams({ source: sourceSel.value, destination: destSel.value, q: state.query, page: state.page });
    fetch(productsUrl + "?" + params.toString(), { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) { return r.json(); })
      .then(function (body) {
        if (id !== state.reqId) return;
        spinner.hidden = true;
        renderResults(body.data || {});
      })
      .catch(function () {
        if (id !== state.reqId) return;
        spinner.hidden = true;
        results.innerHTML = placeholder("fa-triangle-exclamation", T.searchFailed);
      });
  }

  var debounce;
  search.addEventListener("input", function () {
    clearTimeout(debounce);
    debounce = setTimeout(function () { state.query = search.value.trim(); state.page = 1; load(); }, 220);
  });
  // a scanner "types" the barcode and presses Enter: add the exact match straight away
  search.addEventListener("keydown", function (e) {
    if (e.key !== "Enter") return;
    e.preventDefault();
    clearTimeout(debounce);
    state.query = search.value.trim();
    state.page = 1;
    var id = ++state.reqId;
    var params = new URLSearchParams({ source: sourceSel.value, destination: destSel.value, q: state.query, page: 1 });
    fetch(productsUrl + "?" + params.toString(), { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (body) {
        if (id !== state.reqId) return;
        var data = body.data || {};
        renderResults(data);
        if (data.mode === "exact" && data.results.length && data.results[0].source_available > 0) {
          addLine(data.results[0].variant_id);
          search.select();
        }
      });
  });

  function renderResults(data) {
    var rows = data.results || [];
    lastRows = {};
    rows.forEach(function (r) { lastRows[r.variant_id] = r; });
    $('[data-role="results-title"]').textContent = data.mode === "browse" ? T.atSource : T.searchResults;
    $('[data-role="results-count"]').textContent = data.total_count ? fmt(data.total_count) + " " + T.products : "";

    if (!rows.length) {
      results.innerHTML = placeholder(state.query ? "fa-magnifying-glass" : "fa-box-open", state.query ? T.noResults : T.emptyBranch);
      pager.hidden = true;
      return;
    }
    results.innerHTML = rows.map(function (r) {
      var inList = state.lines.some(function (l) { return l.variant_id === r.variant_id; });
      var out = r.source_available <= 0;
      var img = r.image_url
        ? '<img src="' + esc(r.image_url) + '" alt="" loading="lazy">'
        : '<span class="nz-tr-noimg"><i class="fas fa-image" aria-hidden="true"></i></span>';
      var meta = [r.brand, r.size].filter(Boolean).map(esc).join(" · ");
      return (
        '<article class="nz-tr-product' + (out ? " is-out" : "") + (inList ? " is-added" : "") + '" data-variant="' + esc(r.variant_id) + '">' +
          '<div class="nz-tr-product-img">' + img + (data.mode === "exact" ? '<span class="nz-tr-exact">' + esc(T.exactMatch) + "</span>" : "") + "</div>" +
          '<div class="nz-tr-product-body">' +
            '<h4 title="' + esc(r.name) + '">' + esc(r.name) + "</h4>" +
            (meta ? '<p class="nz-tr-product-meta">' + meta + "</p>" : "") +
            '<p class="nz-tr-product-code"><i class="fas fa-barcode" aria-hidden="true"></i> ' + esc(r.barcode || r.sku) + "</p>" +
            '<div class="nz-tr-stock-row">' +
              '<span class="nz-tr-stock ' + (out ? "is-zero" : "is-ok") + '">' + (out ? esc(T.outOfStock) : fmt(r.source_available) + " " + esc(T.inStock)) + "</span>" +
              '<span class="nz-tr-stock is-dest"><i class="fas fa-arrow-right" aria-hidden="true"></i> ' + fmt(r.destination_available) + " " + esc(T.atDestination) + "</span>" +
            "</div>" +
          "</div>" +
          '<button type="button" class="nz-tr-add" data-add="' + esc(r.variant_id) + '"' + (out ? " disabled" : "") + ">" +
            (inList ? '<i class="fas fa-check" aria-hidden="true"></i> ' + esc(T.added) : '<i class="fas fa-plus" aria-hidden="true"></i> ' + esc(T.add)) +
          "</button>" +
        "</article>"
      );
    }).join("");

    if (data.mode === "browse" && data.num_pages > 1) {
      pager.hidden = false;
      pager.innerHTML =
        '<button type="button" data-page="' + (data.page - 1) + '"' + (data.page <= 1 ? " disabled" : "") + ' aria-label="' + esc(T.prev) + '"><i class="fas fa-chevron-left"></i></button>' +
        "<span>" + esc(T.page) + " " + data.page + " / " + data.num_pages + "</span>" +
        '<button type="button" data-page="' + (data.page + 1) + '"' + (data.page >= data.num_pages ? " disabled" : "") + ' aria-label="' + esc(T.next) + '"><i class="fas fa-chevron-right"></i></button>';
    } else {
      pager.hidden = true;
    }
  }

  pager.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-page]");
    if (!btn || btn.disabled) return;
    state.page = parseInt(btn.getAttribute("data-page"), 10);
    load();
    results.scrollIntoView({ block: "nearest", behavior: "smooth" });
  });

  results.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-add]");
    if (btn && !btn.disabled) addLine(btn.getAttribute("data-add"));
  });

  // ------------------------------------------------------------------ transfer list
  function addLine(variantId) {
    var row = lastRows[variantId];
    if (!row || row.source_available <= 0) return;
    var existing = state.lines.find(function (l) { return l.variant_id === variantId; });
    if (existing) {
      existing.quantity = Math.min(existing.quantity + 1, existing.max);
    } else {
      state.lines.push({ variant_id: variantId, name: row.name, meta: [row.brand, row.size].filter(Boolean).join(" · "), image_url: row.image_url, max: row.source_available, quantity: 1 });
    }
    renderLines(variantId);
    markAdded(variantId);
  }

  function markAdded(variantId) {
    var card = results.querySelector('[data-variant="' + variantId + '"]');
    if (!card) return;
    card.classList.add("is-added");
    var btn = card.querySelector("[data-add]");
    if (btn) btn.innerHTML = '<i class="fas fa-check" aria-hidden="true"></i> ' + esc(T.added);
  }

  function renderLines(flashId) {
    $('[data-role="basket-empty"]').hidden = state.lines.length > 0;
    $('[data-action="clear"]').hidden = state.lines.length === 0;
    linesEl.innerHTML = state.lines.map(function (l) {
      var img = l.image_url ? '<img src="' + esc(l.image_url) + '" alt="">' : '<span class="nz-tr-noimg"><i class="fas fa-image" aria-hidden="true"></i></span>';
      return (
        '<li class="nz-tr-line' + (l.variant_id === flashId ? " is-flash" : "") + '" data-line="' + esc(l.variant_id) + '">' +
          '<div class="nz-tr-line-img">' + img + "</div>" +
          '<div class="nz-tr-line-body">' +
            '<p class="nz-tr-line-name" title="' + esc(l.name) + '">' + esc(l.name) + "</p>" +
            '<p class="nz-tr-line-meta">' + (l.meta ? esc(l.meta) + " · " : "") + fmt(l.max) + " " + esc(T.inStock) + "</p>" +
            '<p class="nz-tr-line-warn" data-role="warn" hidden></p>' +
          "</div>" +
          '<div class="nz-tr-qty">' +
            '<button type="button" data-step="-1" aria-label="-"' + (l.quantity <= 1 ? " disabled" : "") + '><i class="fas fa-minus"></i></button>' +
            '<input type="number" inputmode="numeric" min="1" max="' + l.max + '" value="' + l.quantity + '" aria-label="qty">' +
            '<button type="button" data-step="1" aria-label="+"' + (l.quantity >= l.max ? " disabled" : "") + '><i class="fas fa-plus"></i></button>' +
          "</div>" +
          '<button type="button" class="nz-tr-remove" data-remove aria-label="remove"><i class="fas fa-xmark"></i></button>' +
        "</li>"
      );
    }).join("");
    updateSummary();
  }

  function updateSummary() {
    var units = state.lines.reduce(function (s, l) { return s + (l.quantity || 0); }, 0);
    $('[data-role="sum-lines"]').textContent = fmt(state.lines.length);
    $('[data-role="sum-units"]').textContent = fmt(units);
    var valid = routeReady() && state.lines.length > 0 && state.lines.every(function (l) { return l.quantity >= 1 && l.quantity <= l.max; });
    submitBtn.disabled = !valid || state.submitting;
  }

  linesEl.addEventListener("click", function (e) {
    var li = e.target.closest("[data-line]");
    if (!li) return;
    var line = state.lines.find(function (l) { return l.variant_id === li.getAttribute("data-line"); });
    if (e.target.closest("[data-remove]")) {
      state.lines = state.lines.filter(function (l) { return l !== line; });
      var card = results.querySelector('[data-variant="' + line.variant_id + '"]');
      if (card) {
        card.classList.remove("is-added");
        var b = card.querySelector("[data-add]");
        if (b) b.innerHTML = '<i class="fas fa-plus" aria-hidden="true"></i> ' + esc(T.add);
      }
      renderLines();
      return;
    }
    var step = e.target.closest("[data-step]");
    if (step && !step.disabled) {
      line.quantity = Math.max(1, Math.min(line.max, line.quantity + parseInt(step.getAttribute("data-step"), 10)));
      renderLines();
    }
  });

  linesEl.addEventListener("input", function (e) {
    if (e.target.tagName !== "INPUT") return;
    var li = e.target.closest("[data-line]");
    var line = state.lines.find(function (l) { return l.variant_id === li.getAttribute("data-line"); });
    var v = parseInt(e.target.value, 10);
    var warn = li.querySelector('[data-role="warn"]');
    if (!isNaN(v) && v > line.max) {
      warn.hidden = false;
      warn.textContent = T.maxReached.replace("%(n)s", fmt(line.max));
      v = line.max;
      e.target.value = v;
    } else {
      warn.hidden = true;
    }
    line.quantity = isNaN(v) ? 0 : Math.max(0, v);
    li.querySelector('[data-step="-1"]').disabled = line.quantity <= 1;
    li.querySelector('[data-step="1"]').disabled = line.quantity >= line.max;
    updateSummary();
  });
  linesEl.addEventListener("change", function (e) {
    if (e.target.tagName !== "INPUT") return;
    var li = e.target.closest("[data-line]");
    var line = state.lines.find(function (l) { return l.variant_id === li.getAttribute("data-line"); });
    if (!line.quantity || line.quantity < 1) { line.quantity = 1; renderLines(); }
  });

  $('[data-action="clear"]').addEventListener("click", function () {
    state.lines = [];
    renderLines();
    if (routeReady()) load();
  });

  // ------------------------------------------------------------------ confirm + submit
  function openModal(el) { el.hidden = false; document.body.classList.add("nz-tr-modal-open"); }
  function closeModal(el) { el.hidden = true; document.body.classList.remove("nz-tr-modal-open"); }

  submitBtn.addEventListener("click", function () {
    if (submitBtn.disabled) return;
    feedback.hidden = true;
    var units = state.lines.reduce(function (s, l) { return s + l.quantity; }, 0);
    $('[data-role="modal-route"]').innerHTML =
      '<div><small>' + esc($('label[for="nz-tr-source"]').textContent.trim()) + "</small><b>" + esc(branchName(sourceSel)) + "</b></div>" +
      '<i class="fas fa-arrow-right" aria-hidden="true"></i>' +
      '<div><small>' + esc($('label[for="nz-tr-destination"]').textContent.trim()) + "</small><b>" + esc(branchName(destSel)) + "</b></div>";
    $('[data-role="modal-lines"]').innerHTML = state.lines.map(function (l) {
      return "<li><span>" + esc(l.name) + (l.meta ? ' <small>' + esc(l.meta) + "</small>" : "") + "</span><b>" + fmt(l.quantity) + " " + esc(T.units) + "</b></li>";
    }).join("");
    $('[data-role="modal-total"]').innerHTML = "<span>" + fmt(state.lines.length) + " " + esc(T.products) + "</span><b>" + fmt(units) + " " + esc(T.units) + "</b>";
    openModal(modal);
    modal.querySelector('[data-action="confirm"]').focus();
  });

  modal.addEventListener("click", function (e) {
    if (e.target === modal || e.target.closest('[data-action="cancel"]')) closeModal(modal);
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !modal.hidden && !state.submitting) closeModal(modal);
  });

  modal.querySelector('[data-action="confirm"]').addEventListener("click", function () {
    if (state.submitting) return;
    state.submitting = true;
    var btn = this;
    var label = btn.querySelector("span");
    var original = label.textContent;
    btn.disabled = true;
    label.textContent = T.sending;

    fetch(createUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf(), Accept: "application/json" },
      body: JSON.stringify({
        source: sourceSel.value,
        destination: destSel.value,
        note: note.value,
        lines: state.lines.map(function (l) { return { variant_id: l.variant_id, quantity: l.quantity }; }),
      }),
    })
      .then(function (r) { return r.json().then(function (body) { return { ok: r.ok, body: body }; }); })
      .then(function (res) {
        closeModal(modal);
        if (res.ok && res.body.success) {
          var d = res.body.data;
          $('[data-role="success-text"]').innerHTML =
            "<b>" + esc(d.number) + "</b> · " + fmt(d.total_units) + " " + esc(T.units) + "<br>" +
            esc(branchName(sourceSel)) + ' <i class="fas fa-arrow-right" aria-hidden="true"></i> ' + esc(branchName(destSel));
          $('[data-role="success-link"]').setAttribute("href", d.url);
          openModal(success);
        } else {
          showError(res.body && res.body.error);
        }
      })
      .catch(function () { closeModal(modal); showError(null); })
      .then(function () {
        state.submitting = false;
        btn.disabled = false;
        label.textContent = original;
        updateSummary();
      });
  });

  function showError(error) {
    var html = '<i class="fas fa-circle-exclamation" aria-hidden="true"></i> <span>' + esc((error && error.message) || T.failed) + "</span>";
    if (error && error.shortages && error.shortages.length) {
      html += "<ul>" + error.shortages.map(function (s) {
        return "<li><b>" + esc(s.name) + "</b>: " + esc(T.requested) + " " + fmt(s.requested) + ", " + esc(T.available) + " " + fmt(s.available) + "</li>";
      }).join("") + "</ul>";
      // cap each line at what is really there now
      error.shortages.forEach(function (s) {
        var line = state.lines.find(function (l) { return l.variant_id === s.variant_id; });
        if (line) { line.max = s.available; line.quantity = Math.min(line.quantity, Math.max(s.available, 0)); }
      });
      state.lines = state.lines.filter(function (l) { return l.max > 0; });
      renderLines();
      load();
    }
    feedback.innerHTML = html;
    feedback.hidden = false;
  }

  // after success: fresh transfer on the same route (several batches often go the same way); the reload refreshes history + branch totals
  function restart() {
    try { sessionStorage.setItem("nzTransferRoute", JSON.stringify({ s: sourceSel.value, d: destSel.value })); } catch (e) { /* storage blocked */ }
    window.location.reload();
  }
  success.querySelector('[data-action="new"]').addEventListener("click", restart);
  success.addEventListener("click", function (e) { if (e.target === success) restart(); });

  try {
    var saved = JSON.parse(sessionStorage.getItem("nzTransferRoute") || "null");
    sessionStorage.removeItem("nzTransferRoute");
    if (saved) { sourceSel.value = saved.s || ""; destSel.value = saved.d || ""; }
  } catch (e) { /* storage blocked */ }

  syncBranchMeta();
  renderLines();
  if (routeReady()) load();
})();
