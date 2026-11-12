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

  var AUTO = ["#result_list tbody", ".nzi-gallery", ".nzi-table", ".nzd-table"];
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
        if (added[0] && added[0].focus) { added[0].setAttribute("tabindex", "-1"); added[0].focus({ preventScroll: true }); }
        document.dispatchEvent(new CustomEvent("nz:rows-added", { detail: { container: box, rows: added } }));
      })
      .catch(function () { window.location.href = href; })
      .finally(function () { if (btn.isConnected) { btn.removeAttribute("aria-busy"); btn.classList.remove("is-loading"); btn.innerHTML = label; } });
  });
})();
