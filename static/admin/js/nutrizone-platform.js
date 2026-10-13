/*
 * NutriZone Admin -- Platform section pages (templates/admin/platform/*):
 *   - Banner gallery: live on/off switch, drag-to-reorder (saved via JSON endpoints), bulk selection.
 *   - Banner editor: live slide preview, character counters, quick-fill chips, image drop zone, dirty guard.
 *   - Contact inbox / reader: bulk selection, avatar colours, copy buttons, j/k navigation, dirty guard.
 */
(function () {
  "use strict";

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function csrfToken() {
    var input = $("input[name=csrfmiddlewaretoken]");
    if (input) return input.value;
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  function postJSON(url, body) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRFToken": csrfToken(), "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
      body: body ? JSON.stringify(body) : "{}",
    }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }

  var toastTimer;
  function toast(text, isError) {
    var el = $("[data-nzp-toast]");
    if (!el) return;
    el.textContent = text;
    el.classList.toggle("is-error", !!isError);
    el.hidden = false;
    el.style.animation = "none"; void el.offsetWidth; el.style.animation = "";
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.hidden = true; }, 2400);
  }

  /* ---------- shared: bulk selection on a changelist ---------- */
  function initBulk(root) {
    var form = $("[data-nzp-bulk]", root);
    if (!form) return;
    var checks = $$("[data-nzp-row-check]", form);
    var all = $("[data-nzp-select-all]", form);
    var bar = $("[data-nzp-bulkbar]", form);
    var go = $("[data-nzp-bulk-go]", form);
    var label = $("[data-nzp-selected-label]", form);
    var labelDefault = label ? label.textContent : "";
    var select = $("select[name=action]", form);
    if (!checks.length) return;

    function sync() {
      var n = checks.filter(function (c) { return c.checked; }).length;
      checks.forEach(function (c) {
        var card = c.closest(".nzp-banner, .nzp-mail");
        if (card) card.classList.toggle("is-selected", c.checked);
      });
      if (bar) bar.hidden = n === 0 && !bar.hasAttribute("data-always");
      if (all) { all.checked = n === checks.length; all.indeterminate = n > 0 && n < checks.length; }
      if (label) label.textContent = n ? n + " / " + checks.length : labelDefault;
      if (go) go.disabled = n === 0 || (select && !select.value);
    }
    checks.forEach(function (c) { c.addEventListener("change", sync); });
    if (all) all.addEventListener("change", function () { checks.forEach(function (c) { c.checked = all.checked; }); sync(); });
    if (select) select.addEventListener("change", sync);
    sync();
  }

  /* ---------- Banner gallery ---------- */
  function initBannerGallery(root) {
    var activeEl = $("[data-nzp-active-count]", root);
    var hiddenEl = $("[data-nzp-hidden-count]", root);

    $$("[data-nzp-toggle]", root).forEach(function (btn) {
      btn.addEventListener("click", function () {
        var card = btn.closest(".nzp-banner");
        btn.classList.add("is-busy");
        postJSON(btn.getAttribute("data-nzp-toggle")).then(function (data) {
          var on = !!data.is_active;
          btn.classList.toggle("on", on);
          btn.setAttribute("aria-checked", on ? "true" : "false");
          card.classList.toggle("is-off", !on);
          var pill = $("[data-nzp-pill]", card);
          if (pill) { pill.classList.toggle("on", on); pill.classList.toggle("off", !on); }
          if (activeEl && typeof data.active_count === "number") {
            var total = parseInt(activeEl.textContent, 10) + parseInt(hiddenEl.textContent, 10);
            activeEl.textContent = data.active_count;
            hiddenEl.textContent = total - data.active_count;
          }
          toast(on ? root.getAttribute("data-msg-shown") : root.getAttribute("data-msg-hidden"));
          relabelPills();
        }).catch(function () {
          toast(root.getAttribute("data-msg-error"), true);
        }).then(function () { btn.classList.remove("is-busy"); });
      });
    });

    // Pill labels: read the localized words from the first rendered "on"/"off" pills.
    var onWord = null, offWord = null;
    $$("[data-nzp-pill]", root).forEach(function (p) {
      if (p.classList.contains("on") && !onWord) onWord = p.textContent.trim();
      if (p.classList.contains("off") && !offWord) offWord = p.textContent.trim();
    });
    var tabs = $$(".nzp-tab", root);
    // Fallback to the filter tab labels ("Shown"/"Hidden") when only one state is on the page.
    if (!onWord && tabs[1]) onWord = tabs[1].firstChild.textContent.trim();
    if (!offWord && tabs[2]) offWord = tabs[2].firstChild.textContent.trim();
    function relabelPills() {
      $$("[data-nzp-pill]", root).forEach(function (p) { p.textContent = p.classList.contains("on") ? onWord : offWord; });
    }

    // Drag-to-reorder (HTML5 DnD on the handle; whole card is the drop target).
    var grid = $("[data-nzp-grid][data-sortable]", root);
    if (!grid) return;
    var dragged = null;
    function cards() { return $$(".nzp-banner", grid); }
    cards().forEach(function (card) {
      var handle = $(".nzp-drag", card);
      if (!handle) return;
      handle.addEventListener("mousedown", function () { card.setAttribute("draggable", "true"); });
      handle.addEventListener("touchstart", function () { card.setAttribute("draggable", "true"); }, { passive: true });
      card.addEventListener("dragstart", function (e) {
        dragged = card; card.classList.add("is-dragging");
        e.dataTransfer.effectAllowed = "move";
        try { e.dataTransfer.setData("text/plain", card.getAttribute("data-id")); } catch (err) { /* old browsers */ }
      });
      card.addEventListener("dragend", function () {
        card.classList.remove("is-dragging"); card.removeAttribute("draggable");
        cards().forEach(function (c) { c.classList.remove("is-drop-target"); });
        if (dragged) saveOrder();
        dragged = null;
      });
      card.addEventListener("dragover", function (e) {
        if (!dragged || dragged === card) return;
        e.preventDefault();
        var rect = card.getBoundingClientRect();
        // Cards flow left-to-right in rows: the pointer's side of the hovered card decides before/after; a single-column (phone) grid uses the vertical half instead.
        var singleColumn = grid.clientWidth < rect.width * 1.5;
        var after = singleColumn ? e.clientY > rect.top + rect.height / 2 : e.clientX > rect.left + rect.width / 2;
        cards().forEach(function (c) { c.classList.toggle("is-drop-target", c === card); });
        grid.insertBefore(dragged, after ? card.nextSibling : card);
      });
      card.addEventListener("drop", function (e) { e.preventDefault(); });
    });
    document.addEventListener("mouseup", function () { cards().forEach(function (c) { if (c !== dragged) c.removeAttribute("draggable"); }); });

    var lastOrder = cards().map(function (c) { return c.getAttribute("data-id"); }).join(",");
    function saveOrder() {
      var ids = cards().map(function (c) { return c.getAttribute("data-id"); });
      cards().forEach(function (c, i) { var pos = $("[data-nzp-pos]", c); if (pos) pos.textContent = "#" + (i + 1); });
      if (ids.join(",") === lastOrder) return;
      postJSON(root.getAttribute("data-reorder-url"), { ids: ids }).then(function () {
        lastOrder = ids.join(",");
        toast(root.getAttribute("data-msg-saved"));
      }).catch(function () { toast(root.getAttribute("data-msg-error"), true); });
    }
  }

  /* ---------- shared: unsaved-changes guard for a form ---------- */
  function initDirtyGuard(root) {
    var form = $("[data-nzp-form]", root);
    var hint = $("[data-nzp-dirty]", root);
    if (!form) return;
    var dirty = false, submitting = false;
    function mark() { dirty = true; if (hint) hint.hidden = false; }
    form.addEventListener("input", mark);
    form.addEventListener("change", mark);
    form.addEventListener("submit", function () { submitting = true; });
    window.addEventListener("beforeunload", function (e) {
      if (dirty && !submitting) { e.preventDefault(); e.returnValue = ""; }
    });
    // Ctrl/Cmd+S saves and keeps editing.
    document.addEventListener("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        var btn = form.querySelector("button[name=_continue]") || form.querySelector("button[type=submit]");
        if (btn) { e.preventDefault(); btn.click(); }
      }
    });
    return { mark: mark };
  }

  /* ---------- Banner editor ---------- */
  function initBannerEditor(root) {
    var guard = initDirtyGuard(root) || { mark: function () {} };
    var form = $("[data-nzp-form]", root);
    var byName = function (n) { return form.querySelector("[name=" + n + "]"); };
    var title = byName("title"), subtitle = byName("subtitle"), ctaText = byName("cta_text"), ctaUrl = byName("cta_url");
    var duration = byName("duration_seconds"), active = byName("is_active");
    var pTitle = $("[data-nzp-prev-title]", root), pSub = $("[data-nzp-prev-subtitle]", root), pCta = $("[data-nzp-prev-cta]", root);
    var pDur = $("[data-nzp-prev-duration]", root), pBar = $("[data-nzp-prev-bar]", root), pStatus = $("[data-nzp-prev-status]", root);
    var range = $("[data-nzp-range-for]", root);
    if (pTitle && title) pTitle.setAttribute("data-placeholder", title.closest(".nzp-field").querySelector("label").firstChild.textContent.trim());

    function render() {
      if (pTitle && title) pTitle.textContent = title.value;
      if (pSub && subtitle) pSub.textContent = subtitle.value;
      if (pCta) pCta.textContent = ctaText && ctaUrl && ctaText.value.trim() && ctaUrl.value.trim() ? ctaText.value : "";
      var d = parseInt(duration && duration.value, 10) || 45;
      if (pDur) pDur.textContent = d;
      if (pBar) pBar.style.animationDuration = Math.max(3, Math.min(d, 300)) + "s";
      if (pStatus && active) {
        pStatus.textContent = active.checked ? pStatus.getAttribute("data-on") : pStatus.getAttribute("data-off");
        pStatus.className = active.checked ? "on" : "off";
      }
    }
    [title, subtitle, ctaText, ctaUrl, duration].forEach(function (el) { if (el) el.addEventListener("input", render); });
    if (active) active.addEventListener("change", render);

    if (range && duration) {
      range.addEventListener("input", function () { duration.value = range.value; render(); });
      duration.addEventListener("input", function () { var v = parseInt(duration.value, 10); if (v >= 3) range.value = Math.min(v, 120); });
    }

    // Character counters
    $$("[data-nzp-count-for]", root).forEach(function (counter) {
      var input = document.getElementById(counter.getAttribute("data-nzp-count-for"));
      var max = parseInt(counter.getAttribute("data-max"), 10);
      if (!input) return;
      function upd() { var n = input.value.length; counter.textContent = n + " / " + max; counter.classList.toggle("is-near", n > max * 0.85); }
      input.addEventListener("input", upd); upd();
    });

    // Quick-fill chips
    $$("[data-nzp-chips-for]", root).forEach(function (wrap) {
      var input = document.getElementById(wrap.getAttribute("data-nzp-chips-for"));
      $$("button", wrap).forEach(function (b) {
        b.addEventListener("click", function () {
          if (!input) return;
          input.value = b.getAttribute("data-value") || b.textContent.trim();
          input.dispatchEvent(new Event("input", { bubbles: true }));
          input.focus();
        });
      });
    });

    // Device toggle
    var wrap = $("[data-nzp-slide-wrap]", root);
    $$("[data-nzp-device]", root).forEach(function (b, _, all) {
      b.addEventListener("click", function () {
        all.forEach(function (x) { x.classList.toggle("on", x === b); });
        if (wrap) wrap.classList.toggle("is-mobile", b.getAttribute("data-nzp-device") === "mobile");
      });
    });

    // Image: instant preview + drag & drop
    var file = $("[data-nzp-image-input]", root);
    var drop = $("[data-nzp-drop]", root);
    var prevImg = $("[data-nzp-prev-img]", root);
    var thumb = $("[data-nzp-drop-thumb]", root);
    var nameEl = $("[data-nzp-drop-name]", root);
    function showFile() {
      var f = file.files && file.files[0];
      if (!f) return;
      var url = URL.createObjectURL(f);
      if (prevImg) { prevImg.src = url; prevImg.hidden = false; }
      if (thumb) thumb.innerHTML = '<img src="' + url + '" alt="">';
      if (nameEl) nameEl.textContent = f.name + " · " + Math.round(f.size / 1024) + " KB";
      guard.mark();
    }
    if (file) file.addEventListener("change", showFile);
    if (drop && file) {
      ["dragenter", "dragover"].forEach(function (ev) { drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add("is-over"); }); });
      ["dragleave", "drop"].forEach(function (ev) { drop.addEventListener(ev, function () { drop.classList.remove("is-over"); }); });
      drop.addEventListener("drop", function (e) {
        e.preventDefault();
        if (e.dataTransfer && e.dataTransfer.files.length) { file.files = e.dataTransfer.files; showFile(); }
      });
    }
    render();
  }

  /* ---------- Avatars: stable colour per sender ---------- */
  var PALETTE = ["#6366f1", "#0ea5e9", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#14b8a6", "#ec4899", "#f97316", "#3b82f6"];
  function paintAvatars(root) {
    $$(".nzp-avatar[data-seed]", root).forEach(function (el) {
      var s = el.getAttribute("data-seed") || "", h = 0;
      for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
      el.style.setProperty("--av", PALETTE[h % PALETTE.length]);
    });
  }

  /* ---------- Contact reader ---------- */
  function initReader(root) {
    initDirtyGuard(root);
    $$("[data-nzp-copy]", root).forEach(function (btn) {
      btn.addEventListener("click", function () {
        var text = btn.getAttribute("data-nzp-copy");
        var done = function () {
          var old = btn.getAttribute("title");
          btn.classList.add("is-copied");
          btn.setAttribute("title", root.getAttribute("data-msg-copied"));
          var icon = btn.querySelector("i");
          if (icon) { icon.className = "fas fa-check"; setTimeout(function () { icon.className = "fas fa-copy"; if (old) btn.setAttribute("title", old); }, 1400); }
        };
        if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(done);
        else {
          var ta = document.createElement("textarea"); ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
          document.body.appendChild(ta); ta.select(); try { document.execCommand("copy"); done(); } catch (e) { /* ignore */ } ta.remove();
        }
      });
    });
    var reply = $("[data-nzp-reply]", root);
    var hint = $("[data-nzp-reply-hint]", root);
    if (reply && hint) reply.addEventListener("click", function () { hint.hidden = false; });
    // j / k jump to older / newer message (ignored while typing).
    document.addEventListener("keydown", function (e) {
      if (e.ctrlKey || e.metaKey || e.altKey || /^(INPUT|TEXTAREA|SELECT)$/.test((e.target || {}).tagName)) return;
      var link = $('[data-nzp-key="' + e.key + '"]', root);
      if (link) link.click();
    });
  }

  function init() {
    var gallery = $("[data-nzp-banners]");
    if (gallery) { initBulk(gallery); initBannerGallery(gallery); }
    var editor = $("[data-nzp-banner-editor]");
    if (editor) initBannerEditor(editor);
    var inbox = $("[data-nzp-inbox]");
    if (inbox) { initBulk(inbox); paintAvatars(inbox); }
    var reader = $("[data-nzp-reader]");
    if (reader) { paintAvatars(reader); initReader(reader); }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
