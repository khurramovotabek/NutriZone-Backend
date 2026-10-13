/*
 * NutriZone Admin -- sidebar enhancements (see nutrizone-sidebar.css).
 *   1. User card: initials avatar + role line (data from window.NZ_USER, set in base_site.html).
 *   2. Menu filter: type to narrow the long app/model menu; matching groups open automatically.
 * Vanilla JS, no dependencies; does nothing if Jazzmin's markup isn't there.
 */
(function () {
  "use strict";

  function initials(name) {
    var words = (name || "").trim().split(/\s+/).filter(Boolean);
    if (!words.length) return "?";
    return (words.length > 1 ? words[0][0] + words[1][0] : words[0].slice(0, 2)).toUpperCase();
  }

  function enhanceUserPanel(sidebar, user, i18n) {
    var panel = sidebar.querySelector(".user-panel");
    if (!panel || !user) return;
    var image = panel.querySelector(".image");
    if (image && !image.querySelector("img")) {
      image.innerHTML = "";
      var avatar = document.createElement("span");
      avatar.className = "nz-sb-avatar";
      avatar.setAttribute("aria-hidden", "true");
      avatar.textContent = initials(user.name);
      image.appendChild(avatar);
    }
    var info = panel.querySelector(".info");
    if (info && !info.querySelector(".nz-sb-role")) {
      var role = document.createElement("span");
      role.className = "nz-sb-role";
      role.textContent = user.isSuperuser ? i18n.superadmin : i18n.staff;
      info.appendChild(role);
    }
  }

  function addMenuFilter(sidebar, i18n) {
    var menu = sidebar.querySelector(".sidebar-menu");
    if (!menu || sidebar.querySelector(".nz-sb-filter")) return;

    var wrap = document.createElement("div");
    wrap.className = "nz-sb-filter";
    wrap.innerHTML = '<i class="fas fa-magnifying-glass" aria-hidden="true"></i>';
    var input = document.createElement("input");
    input.type = "search";
    input.placeholder = i18n.placeholder;
    input.setAttribute("aria-label", i18n.placeholder);
    wrap.appendChild(input);
    var empty = document.createElement("p");
    empty.className = "nz-sb-empty";
    empty.textContent = i18n.empty;
    empty.hidden = true;
    menu.parentNode.insertBefore(wrap, menu);
    menu.parentNode.insertBefore(empty, menu);

    var groups = Array.prototype.slice.call(menu.children);
    // Remember which groups were open before filtering, to restore them when the filter is cleared.
    var wasOpen = groups.map(function (li) { return li.classList.contains("menu-open"); });

    function text(el) { return (el.textContent || "").toLowerCase(); }

    function apply() {
      var q = input.value.trim().toLowerCase();
      var shown = 0;
      groups.forEach(function (li, idx) {
        var link = li.querySelector(":scope > .nav-link");
        var tree = li.querySelector(":scope > .nav-treeview");
        if (!q) {
          li.classList.remove("nz-sb-hidden");
          li.classList.toggle("menu-open", wasOpen[idx]);
          if (tree) {
            tree.style.display = wasOpen[idx] ? "" : "none";
            Array.prototype.forEach.call(tree.children, function (c) { c.classList.remove("nz-sb-hidden"); });
          }
          shown++;
          return;
        }
        var groupMatch = link && text(link).indexOf(q) !== -1;
        var childHits = 0;
        if (tree) {
          Array.prototype.forEach.call(tree.children, function (c) {
            var hit = groupMatch || text(c).indexOf(q) !== -1;
            c.classList.toggle("nz-sb-hidden", !hit);
            if (hit) childHits++;
          });
        }
        var visible = groupMatch || childHits > 0;
        li.classList.toggle("nz-sb-hidden", !visible);
        if (tree) {
          li.classList.toggle("menu-open", visible);
          tree.style.display = visible ? "block" : "none";
        }
        if (visible) shown++;
      });
      empty.hidden = shown > 0;
    }

    input.addEventListener("input", apply);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { input.value = ""; apply(); input.blur(); }
      if (e.key === "Enter") {
        // Jump to the first visible destination.
        var first = menu.querySelector(".nav-treeview > .nav-item:not(.nz-sb-hidden) > .nav-link[href]:not([href^='javascript']), :scope > .nav-item:not(.nz-sb-hidden):not(.has-treeview) > .nav-link[href]");
        if (first) window.location.href = first.getAttribute("href");
      }
    });
  }

  // Pages whose URL isn't under their model's admin path still belong to that sidebar entry.
  var PATH_ALIASES = [["/settings-overview/", "/platform/sitesettings/"]];

  /* Jazzmin only highlights exact model URLs; fall back to the longest menu link that prefixes the current path
     (custom pages, change forms reached after a save, etc.) and open its group. */
  function markActive(sidebar) {
    var menu = sidebar.querySelector(".sidebar-menu");
    if (!menu || menu.querySelector(".nav-treeview .nav-link.active")) return;
    var path = window.location.pathname;
    PATH_ALIASES.forEach(function (a) { if (path.indexOf(a[0]) !== -1) path = path.replace(a[0], a[1]); });
    var best = null, bestLen = 0;
    Array.prototype.forEach.call(menu.querySelectorAll(".nav-treeview .nav-link[href]"), function (link) {
      var linkPath;
      try { linkPath = new URL(link.getAttribute("href"), window.location.href).pathname; } catch (e) { return; }
      if (linkPath.length > 1 && path.indexOf(linkPath) === 0 && linkPath.length > bestLen) { best = link; bestLen = linkPath.length; }
    });
    if (!best) return;
    best.classList.add("active");
    var group = best.closest(".sidebar-menu > .nav-item");
    if (group) {
      group.classList.add("menu-open");
      var tree = group.querySelector(":scope > .nav-treeview");
      if (tree) tree.style.display = "block";
    }
  }

  function init() {
    var sidebar = document.getElementById("jazzy-sidebar");
    if (!sidebar) return;
    var i18n = (window.NZ_I18N && window.NZ_I18N.sidebar) || { placeholder: "Filter menu…", empty: "Nothing found", superadmin: "Superadmin", staff: "Staff" };
    enhanceUserPanel(sidebar, window.NZ_USER, i18n);
    markActive(sidebar);
    addMenuFilter(sidebar, i18n);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
