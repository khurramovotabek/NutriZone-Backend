/*
 * "Yana ko'rsatish" (load more) for every Dashboard list pager.
 *
 * A link marked [data-nz-more] inside a pager marked [data-nz-pager] fetches the next page (the same URL its "next" arrow
 * opens, so filters, search and ordering are kept), appends that page's rows under the rows already shown and swaps the
 * pager for the fetched one -- whose button then points one page further. The counter keeps the first row number
 * ("1–100 / 253"). Without JS -- or when the fetch fails -- the link is an ordinary link to the next page.
 *
 * The rows container is the list right above the pager: [data-nz-rows="<selector>"] on the pager names it, otherwise the
 * nearest preceding top-level #result_list tbody / .nzi-gallery / .nzi-table / .nzd-table. Header rows stay put.
 * Page scripts that bind per row listen to `nz:rows-added` (detail: {container, rows}).
 */
(function () {
  "use strict";
  if (window.__nzLoadMore) return;
  window.__nzLoadMore = true;

  var AUTO = ["#result_list tbody", ".nzi-gallery", ".nzi-table", ".nzd-table", ".nzp-banner-grid", ".nzp-mail-list"];
  var HEAD = ".nzi-th, .nzd-th, .nzp-empty";
  var t = function (s) { return (window.nzTranslate || String)(s); };

  function precedes(el, pager) {
    return !el.contains(pager) && !!(el.compareDocumentPosition(pager) & Node.DOCUMENT_POSITION_FOLLOWING);
  }

  function rowsContainer(doc, pager) {
    var named = pager.getAttribute("data-nz-rows");
    var sels = named ? [named] : AUTO;
    var all = [];
    sels.forEach(function (sel) { Array.prototype.forEach.call(doc.querySelectorAll(sel), function (el) { all.push(el); }); });
    // a variants panel inside a product row is a table too -- only top-level lists count
    var top = all.filter(function (el) { return !all.some(function (o) { return o !== el && o.contains(el); }); });
    var best = null;
    top.forEach(function (el) { if (precedes(el, pager) && (!best || precedes(best, el))) best = el; });
    return best;
  }

  function keepFrom(root, from) {
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT), node;
    while ((node = walker.nextNode())) {
      if (node.parentElement && node.parentElement.closest("[data-nz-more]")) continue;
      if (/\d[\d\s ]*–\s*\d/.test(node.nodeValue)) { node.nodeValue = node.nodeValue.replace(/\d[\d\s ]*(?=–)/, from); return; }
    }
  }

  /* The bar under "1–200 / 253" shows how much of the list is on screen now; once every row is loaded the pager says so. */
  function progress(pager) {
    var from = parseInt(pager.getAttribute("data-nz-from"), 10) || 1;
    var end = parseInt(pager.getAttribute("data-nz-end"), 10) || 0;
    var count = parseInt(pager.getAttribute("data-nz-count"), 10) || 0;
    if (!count) return;
    var pct = Math.min(100, Math.round(((end - from + 1) * 100) / count));
    var bar = pager.querySelector(".nz-pager-bar");
    if (bar) { bar.setAttribute("aria-valuenow", pct); if (bar.firstElementChild) bar.firstElementChild.style.width = pct + "%"; }
    var done = pager.querySelector(".nz-pager-done");
    if (from === 1 && end >= count) {
      // the whole list is on screen: page numbers and "show all" have nothing left to offer
      if (done) done.innerHTML = '<i class="fas fa-circle-check" aria-hidden="true"></i> ' + t("Hammasi ko'rsatildi") + " · " + count;
      Array.prototype.forEach.call(pager.querySelectorAll(".nz-pager-list, .nz-pager-all"), function (el) { el.hidden = true; });
    }
    toTop();
  }

  /* "Tepaga": a round button once a grown list is long -- the page scrolls inside Jazzmin's wrapper or the window. */
  var topBtn = null;
  function scroller() {
    var el = document.querySelector("[data-nz-pager]");
    for (var p = el && el.parentElement; p && p !== document.body; p = p.parentElement) {
      var oy = getComputedStyle(p).overflowY;
      if ((oy === "auto" || oy === "scroll") && p.scrollHeight > p.clientHeight + 4) return p;
    }
    return null;
  }
  function toTop() {
    if (topBtn) return;
    var box = scroller(), target = box || window;
    topBtn = document.createElement("button");
    topBtn.type = "button";
    topBtn.className = "nz-totop";
    topBtn.setAttribute("aria-label", t("Tepaga"));
    topBtn.innerHTML = '<i class="fas fa-arrow-up" aria-hidden="true"></i><span>' + t("Tepaga") + "</span>";
    topBtn.hidden = true;
    document.body.appendChild(topBtn);
    var pos = function () { return box ? box.scrollTop : (window.scrollY || document.documentElement.scrollTop); };
    var sync = function () { topBtn.hidden = pos() < 900; };
    target.addEventListener("scroll", sync, { passive: true });
    topBtn.addEventListener("click", function () { (box || window).scrollTo({ top: 0, behavior: "smooth" }); });
    sync();
  }

  function pagerIndex(pager) {
    return Array.prototype.indexOf.call(document.querySelectorAll("[data-nz-pager]"), pager);
  }

  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-nz-more]");
    if (!btn || e.ctrlKey || e.metaKey || e.shiftKey || btn.getAttribute("aria-busy") === "true") return;
    var pager = btn.closest("[data-nz-pager]");
    var box = pager && rowsContainer(document, pager);
    if (!box) return; // no list to grow: the link just opens the next page
    e.preventDefault();
    var href = btn.getAttribute("href"), idx = pagerIndex(pager), label = btn.innerHTML;
    btn.setAttribute("aria-busy", "true");
    btn.classList.add("is-loading");
    btn.innerHTML = '<i class="fas fa-circle-notch fa-spin" aria-hidden="true"></i> ' + t("Yuklanmoqda…");

    fetch(href, { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, "text/html");
        var nextPager = doc.querySelectorAll("[data-nz-pager]")[idx];
        var nextBox = nextPager && rowsContainer(doc, nextPager);
        if (!nextBox) throw new Error("no rows");
        var added = [];
        Array.prototype.forEach.call(nextBox.children, function (row) {
          if (row.matches && row.matches(HEAD)) return;
          var copy = document.importNode(row, true);
          box.appendChild(copy);
          added.push(copy);
        });
        var fresh = document.importNode(nextPager, true);
        var from = pager.getAttribute("data-nz-from"), freshFrom = fresh.querySelector("[data-nz-from-cell]");
        if (from) {
          fresh.setAttribute("data-nz-from", from);
          if (freshFrom) freshFrom.textContent = from;
          else keepFrom(fresh, from); // "Showing 51–100 of 253" written by a translated sentence → "Showing 1–100 of 253"
        }
        pager.replaceWith(fresh);
        progress(fresh);
        if (added[0] && added[0].focus) { added[0].setAttribute("tabindex", "-1"); added[0].focus({ preventScroll: true }); }
        document.dispatchEvent(new CustomEvent("nz:rows-added", { detail: { container: box, rows: added } }));
      })
      .catch(function () { window.location.href = href; })
      .finally(function () { if (btn.isConnected) { btn.removeAttribute("aria-busy"); btn.classList.remove("is-loading"); btn.innerHTML = label; } });
  });

  /* "№ → " jump-to-page box (templates/admin/pagination.html): the URL keeps filters, search and ordering. */
  document.addEventListener("submit", function (e) {
    var form = e.target.closest && e.target.closest("[data-nz-jump]");
    if (!form) return;
    e.preventDefault();
    var input = form.querySelector("input"), total = parseInt(form.getAttribute("data-nz-total"), 10) || 1;
    var n = parseInt(input.value, 10);
    if (!n || n < 1 || n > total) { input.classList.add("is-bad"); input.focus(); return; }
    window.location.href = form.getAttribute("data-nz-jump").replace("__P__", String(n));
  });
  document.addEventListener("input", function (e) {
    if (e.target.closest && e.target.closest("[data-nz-jump]")) e.target.classList.remove("is-bad");
  });
})();
