/*
 * NutriZone Admin -- theme + language switcher UI (Phase 08.1)
 * Injects two dropdowns into Jazzmin's existing right-side navbar
 * container (".navbar-nav.ms-auto") rather than overriding Jazzmin's
 * own navbar template -- stays robust to internal Jazzmin markup
 * changes on upgrade.
 */
(function () {
  "use strict";

  function injectThemeSwitcher(container) {
    var li = document.createElement("li");
    li.className = "nav-item dropdown nz-theme-switcher";
    li.innerHTML =
      '<a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown" ' +
      'aria-haspopup="true" aria-expanded="false" aria-label="' + ((window.NZ_I18N && window.NZ_I18N.theme) || "Theme") + '">' +
      '<i class="fas fa-circle-half-stroke"></i></a>' +
      '<div class="dropdown-menu dropdown-menu-end" role="menu">' +
      '<a class="dropdown-item nz-theme-option" data-theme-mode="light" href="#">' + ((window.NZ_I18N && window.NZ_I18N.light) || "Light") + '</a>' +
      '<a class="dropdown-item nz-theme-option" data-theme-mode="dark" href="#">' + ((window.NZ_I18N && window.NZ_I18N.dark) || "Dark") + '</a>' +
      '<a class="dropdown-item nz-theme-option" data-theme-mode="system" href="#">' + ((window.NZ_I18N && window.NZ_I18N.system) || "System") + '</a>' +
      "</div>";
    container.insertBefore(li, container.firstChild);

    li.querySelectorAll(".nz-theme-option").forEach(function (option) {
      option.addEventListener("click", function (event) {
        event.preventDefault();
        var mode = option.getAttribute("data-theme-mode");
        if (window.NutrizoneTheme) {
          window.NutrizoneTheme.set(mode);
        }
      });
    });
  }

  function injectLanguageSwitcher(container) {
    var languages = (window.NZ_I18N && window.NZ_I18N.languages) || [];
    if (!languages.length) {
      return;
    }
    var current = (window.NZ_I18N && window.NZ_I18N.currentLanguage) || "en";

    var li = document.createElement("li");
    li.className = "nav-item dropdown nz-language-switcher";
    var optionsHtml = languages
      .map(function (lang) {
        return (
          '<button type="submit" name="language" value="' + lang.code + '" class="dropdown-item nz-language-option' +
          (lang.code === current ? " active" : "") + '">' + lang.name + "</button>"
        );
      })
      .join("");

    li.innerHTML =
      '<a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown" ' +
      'aria-haspopup="true" aria-expanded="false" aria-label="' + ((window.NZ_I18N && window.NZ_I18N.language) || "Language") + '">' +
      current.toUpperCase() + "</a>" +
      '<div class="dropdown-menu dropdown-menu-end" role="menu">' +
      '<form method="post" action="' + ((window.NZ_I18N && window.NZ_I18N.setLanguageUrl) || "/i18n/setlang/") + '" class="nz-language-form">' +
      '<input type="hidden" name="csrfmiddlewaretoken" value="' + (window.NZ_CSRF_TOKEN || "") + '">' +
      '<input type="hidden" name="next" value="' + window.location.pathname + '">' +
      optionsHtml +
      "</form></div>";
    container.insertBefore(li, container.firstChild);

    li.querySelectorAll(".nz-language-option").forEach(function (btn) {
      btn.addEventListener("click", function (event) {
        var form = btn.closest("form");
        var hiddenLang = document.createElement("input");
        hiddenLang.type = "hidden";
        hiddenLang.name = "language";
        hiddenLang.value = btn.value;
        form.appendChild(hiddenLang);
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var navContainer = document.querySelector(".navbar-nav.ms-auto") || document.querySelector("#jazzy-navbar .navbar-nav:last-of-type");
    if (!navContainer) {
      return;
    }
    injectLanguageSwitcher(navContainer);
    injectThemeSwitcher(navContainer);
  });
})();
