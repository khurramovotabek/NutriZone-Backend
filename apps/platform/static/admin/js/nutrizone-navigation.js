/*
 * NutriZone Admin -- navigation/drawer behavior (Phase 08.1)
 * Adds an overlay + Escape-key close for the mobile off-canvas
 * sidebar. Reuses AdminLTE/Jazzmin's own existing
 * "sidebar-collapse" body class as the single source of truth for
 * open/closed state -- this file only adds the overlay and a
 * couple of accessibility affordances on top of it.
 */
(function () {
  "use strict";

  function isMobileDrawerOpen() {
    return window.innerWidth < 768 && !document.body.classList.contains("sidebar-collapse");
  }

  function ensureOverlay() {
    var overlay = document.querySelector(".nz-sidebar-overlay");
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.className = "nz-sidebar-overlay";
      overlay.setAttribute("aria-hidden", "true");
      overlay.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,.35);z-index:1030;display:none;";
      document.body.appendChild(overlay);
      overlay.addEventListener("click", function () {
        document.body.classList.add("sidebar-collapse");
      });
    }
    return overlay;
  }

  function syncOverlay() {
    var overlay = ensureOverlay();
    overlay.style.display = isMobileDrawerOpen() ? "block" : "none";
  }

  document.addEventListener("DOMContentLoaded", function () {
    syncOverlay();

    var observer = new MutationObserver(syncOverlay);
    observer.observe(document.body, { attributes: true, attributeFilter: ["class"] });

    window.addEventListener("resize", syncOverlay);

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && isMobileDrawerOpen()) {
        document.body.classList.add("sidebar-collapse");
      }
    });
  });
})();
