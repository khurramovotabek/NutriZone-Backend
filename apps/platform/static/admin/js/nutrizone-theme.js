/*
 * NutriZone Admin -- theme switcher (Phase 08.1)
 * Vanilla JS. Two entry points:
 *   1. applyStoredTheme() -- called synchronously, inline, in <head>,
 *      before the stylesheet/body paints, to avoid a flash of the
 *      wrong theme.
 *   2. NutrizoneTheme.set(mode) -- called by the theme-switcher UI.
 */
(function () {
  "use strict";

  var STORAGE_KEY = "nutrizone.admin.theme";
  var MODES = ["light", "dark", "system"];

  function resolveSystemPreference() {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function effectiveTheme(mode) {
    return mode === "system" ? resolveSystemPreference() : mode;
  }

  var JAZZMIN_STORAGE_KEY = "jazzmin-theme-mode";

  function applyStoredTheme() {
    var mode = "system";
    try {
      var stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored && MODES.indexOf(stored) !== -1) {
        mode = stored;
      }
    } catch (e) {
      // localStorage unavailable (private browsing, disabled storage) -- fall back to system, never throw.
    }
    var effective = effectiveTheme(mode);
    document.documentElement.setAttribute("data-nz-theme", effective);
    document.documentElement.setAttribute("data-nz-theme-mode", mode);
    // Jazzmin's own, independent dark-mode system (data-bs-theme,
    // driven by its own 'jazzmin-theme-mode' localStorage key) is
    // kept in sync here -- otherwise Bootstrap/AdminLTE's own
    // ready-made dark-mode CSS (forms, inputs, selects, cards) never
    // activates, since it only ever reacts to data-bs-theme, not
    // data-nz-theme.
    document.documentElement.setAttribute("data-bs-theme", effective);
  }

  function setTheme(mode) {
    if (MODES.indexOf(mode) === -1) {
      return;
    }
    try {
      window.localStorage.setItem(STORAGE_KEY, mode);
      window.localStorage.setItem(JAZZMIN_STORAGE_KEY, effectiveTheme(mode));
    } catch (e) {
      // Best-effort persistence only -- theme still applies for this page view even if storage fails.
    }
    var effective = effectiveTheme(mode);
    document.documentElement.setAttribute("data-nz-theme", effective);
    document.documentElement.setAttribute("data-nz-theme-mode", mode);
    document.documentElement.setAttribute("data-bs-theme", effective);
    document.dispatchEvent(new CustomEvent("nutrizone:theme-changed", { detail: { mode: mode } }));
  }

  function currentMode() {
    return document.documentElement.getAttribute("data-nz-theme-mode") || "system";
  }

  // Re-apply when the OS preference changes while "system" is active.
  if (window.matchMedia) {
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function () {
      if (currentMode() === "system") {
        document.documentElement.setAttribute("data-nz-theme", resolveSystemPreference());
      }
    });
  }

  window.NutrizoneTheme = {
    set: setTheme,
    current: currentMode,
    applyStoredTheme: applyStoredTheme,
  };

  // Applied immediately on script execution too, in case this file
  // is loaded deferred rather than inlined synchronously in <head>.
  applyStoredTheme();
})();
