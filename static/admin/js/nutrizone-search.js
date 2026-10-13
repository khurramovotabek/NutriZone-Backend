/*
 * NutriZone Admin -- global search command palette (Phase 17.1)
 * Ctrl+K / Cmd+K opens a modal that queries /django-admin/search/.
 * Debounced (250ms). Reuses the existing NZ_I18N global (set in
 * base_site.html, same pattern as nutrizone-switchers.js) for
 * translated UI strings.
 */
(function () {
  "use strict";

  var DEBOUNCE_MS = 250;
  var debounceTimer = null;
  var modal = null;
  var input = null;
  var resultsEl = null;
  var activeIndex = -1;

  function t(key, fallback) {
    return (window.NZ_I18N && window.NZ_I18N.search && window.NZ_I18N.search[key]) || fallback;
  }

  function buildModal() {
    var overlay = document.createElement("div");
    overlay.className = "nz-search-overlay";
    overlay.setAttribute("aria-hidden", "true");

    var box = document.createElement("div");
    box.className = "nz-search-modal";
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");

    box.innerHTML =
      '<div class="nz-search-input-row">' +
      '<input type="text" class="nz-search-input" placeholder="' + t("placeholder", "Search products, orders, customers...") + '" autocomplete="off">' +
      '<kbd class="nz-search-hint">ESC</kbd>' +
      "</div>" +
      '<div class="nz-search-results" role="listbox"></div>';

    overlay.appendChild(box);
    document.body.appendChild(overlay);

    overlay.addEventListener("click", function (event) {
      if (event.target === overlay) {
        closeModal();
      }
    });

    return { overlay: overlay, input: box.querySelector(".nz-search-input"), results: box.querySelector(".nz-search-results") };
  }

  function ensureModal() {
    if (!modal) {
      var built = buildModal();
      modal = built.overlay;
      input = built.input;
      resultsEl = built.results;

      input.addEventListener("input", onInput);
      input.addEventListener("keydown", onKeydown);
    }
    return modal;
  }

  function openModal() {
    ensureModal();
    modal.classList.add("nz-search-open");
    input.value = "";
    input.focus();
    renderEmpty();
  }

  function closeModal() {
    if (modal) {
      modal.classList.remove("nz-search-open");
    }
  }

  function renderEmpty() {
    resultsEl.innerHTML = '<div class="nz-search-empty">' + t("startTyping", "Start typing to search...") + "</div>";
    activeIndex = -1;
  }

  function renderLoading() {
    resultsEl.innerHTML = '<div class="nz-search-empty">' + t("loading", "Searching...") + "</div>";
  }

  function renderNoResults() {
    resultsEl.innerHTML = '<div class="nz-search-empty">' + t("noResults", "No results found.") + "</div>";
    activeIndex = -1;
  }

  function renderResults(groups) {
    if (!groups.length) {
      renderNoResults();
      return;
    }
    var html = "";
    groups.forEach(function (group) {
      html += '<div class="nz-search-group-label">' + group.label + "</div>";
      group.results.forEach(function (item) {
        html +=
          '<a class="nz-search-result" href="' + item.url + '">' +
          '<span class="nz-search-result-title">' + escapeHtml(item.title) + "</span>" +
          '<span class="nz-search-result-subtitle">' + escapeHtml(item.subtitle || "") + "</span>" +
          "</a>";
      });
    });
    resultsEl.innerHTML = html;
    activeIndex = -1;
  }

  function escapeHtml(value) {
    var div = document.createElement("div");
    div.textContent = value;
    return div.innerHTML;
  }

  function onInput() {
    var query = input.value.trim();
    window.clearTimeout(debounceTimer);
    if (query.length < 2) {
      renderEmpty();
      return;
    }
    renderLoading();
    debounceTimer = window.setTimeout(function () {
      fetch("/django-admin/search/?q=" + encodeURIComponent(query), { credentials: "same-origin" })
        .then(function (response) {
          return response.json();
        })
        .then(function (data) {
          renderResults(data.groups || []);
        })
        .catch(function () {
          renderNoResults();
        });
    }, DEBOUNCE_MS);
  }

  function onKeydown(event) {
    var items = resultsEl.querySelectorAll(".nz-search-result");
    if (event.key === "ArrowDown") {
      event.preventDefault();
      activeIndex = Math.min(activeIndex + 1, items.length - 1);
      highlight(items);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      activeIndex = Math.max(activeIndex - 1, 0);
      highlight(items);
    } else if (event.key === "Enter") {
      if (activeIndex >= 0 && items[activeIndex]) {
        window.location.href = items[activeIndex].getAttribute("href");
      } else if (items.length) {
        window.location.href = items[0].getAttribute("href");
      }
    } else if (event.key === "Escape") {
      closeModal();
    }
  }

  function highlight(items) {
    items.forEach(function (item, index) {
      item.classList.toggle("nz-search-result-active", index === activeIndex);
    });
    if (items[activeIndex]) {
      items[activeIndex].scrollIntoView({ block: "nearest" });
    }
  }

  document.addEventListener("keydown", function (event) {
    var isMeta = event.metaKey || event.ctrlKey;
    if (isMeta && event.key.toLowerCase() === "k") {
      event.preventDefault();
      if (modal && modal.classList.contains("nz-search-open")) {
        closeModal();
      } else {
        openModal();
      }
    } else if (event.key === "Escape" && modal && modal.classList.contains("nz-search-open")) {
      closeModal();
    }
  });

  // Real, discoverable entry point -- previously this search could
  // only ever be opened via the Ctrl+K/Cmd+K keyboard shortcut, with
  // no visible trigger anywhere in the navbar, so most users would
  // never discover it exists.
  window.NutrizoneSearch = { open: openModal };

  function injectSearchTrigger() {
    var navbar = document.querySelector("#jazzy-navbar .navbar-nav") || document.querySelector(".navbar-nav.ms-auto");
    if (!navbar || document.querySelector(".nz-search-trigger")) {
      return;
    }
    var li = document.createElement("li");
    li.className = "nav-item nz-search-trigger-wrap";
    var button = document.createElement("button");
    button.type = "button";
    button.className = "nz-search-trigger";
    button.setAttribute("aria-label", t("placeholder", "Search products, orders, customers..."));
    var isMac = /Mac|iPhone|iPod|iPad/i.test(navigator.platform || "");
    button.innerHTML =
      '<i class="fas fa-magnifying-glass" aria-hidden="true"></i>' +
      '<span class="nz-search-trigger-text">' + t("placeholder", "Search products, orders, customers...") + "</span>" +
      '<kbd class="nz-search-trigger-kbd">' + (isMac ? "\u2318K" : "Ctrl K") + "</kbd>";
    button.addEventListener("click", openModal);
    li.appendChild(button);
    navbar.insertBefore(li, navbar.firstChild);
  }

  document.addEventListener("DOMContentLoaded", injectSearchTrigger);
})();
