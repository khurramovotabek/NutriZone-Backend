/* Catalog add/change pages (templates/admin/products/premium_change_form.html): translation tabs, section bar,
   image drop zone, switches, slug autofill, colour picker, live hero title, unsaved-changes badge, Ctrl+S. */
(function () {
  "use strict";
  var LANGS = { uz: { flag: "🇺🇿", name: "O'zbekcha" }, ru: { flag: "🇷🇺", name: "Русский" }, en: { flag: "🇬🇧", name: "English" } };
  var ORDER = ["uz", "ru", "en"];
  var form = document.querySelector("#content-main form");
  if (!form || !document.body.classList.contains("nzp-page")) return;

  function el(tag, cls, html) { var e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }
  function q(sel, root) { return (root || document).querySelector(sel); }
  function qa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  /* ---------- slugify (Latin + Cyrillic transliteration) ---------- */
  var CYR = { а:"a",б:"b",в:"v",г:"g",д:"d",е:"e",ё:"yo",ж:"zh",з:"z",и:"i",й:"y",к:"k",л:"l",м:"m",н:"n",о:"o",п:"p",р:"r",с:"s",т:"t",у:"u",ф:"f",х:"h",ц:"ts",ч:"ch",ш:"sh",щ:"sch",ъ:"",ы:"y",ь:"",э:"e",ю:"yu",я:"ya",ў:"o",қ:"q",ғ:"g",ҳ:"h" };
  function slugify(s) {
    return (s || "").toLowerCase().replace(/[ʻʼ'`‘’]/g, "").split("").map(function (c) { return CYR[c] != null ? CYR[c] : c; }).join("")
      .normalize("NFKD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 200);
  }

  /* ---------- translation tabs ---------- */
  function itemsOf(group) { return qa(".inline-related", group).filter(function (it) { return !it.classList.contains("empty-form") && !/-empty$/.test(it.id); }); }
  function localeOf(item) { var s = q('select[name$="-locale_code"]', item); return s ? s.value : ""; }
  function fieldVal(item, suffix) { var f = q('[name$="-' + suffix + '"]', item); return f ? (f.value || "").trim() : ""; }
  function stateOf(item) {
    if (q('input[name$="-DELETE"]:checked', item)) return "del";
    var name = fieldVal(item, "name");
    if (!name) return "empty";
    var desc = q('[name$="-description"]', item);
    return desc && !desc.value.trim() ? "part" : "full";
  }

  function buildTabs(card) {
    var group = q(".inline-group", card) || card;
    var items = itemsOf(group);
    if (!items.length) return;
    card.classList.add("nzp-tr-ready");
    var bar = q(".nzp-tabs", card);
    if (!bar) { bar = el("div", "nzp-tabs"); bar.setAttribute("role", "tablist"); group.parentNode.insertBefore(bar, group); }
    bar.innerHTML = "";
    items.sort(function (a, b) { return ORDER.indexOf(localeOf(a)) - ORDER.indexOf(localeOf(b)); });
    var active = card._nzpActive && items.indexOf(card._nzpActive) >= 0 ? card._nzpActive : null;
    if (!active) active = items.find(function (it) { return q(".errors, .errorlist", it); }) || items[0];
    items.forEach(function (item) {
      var code = localeOf(item), meta = LANGS[code] || { flag: "🌐", name: code || "Til" };
      var st = stateOf(item);
      var b = el("button", "nzp-tab is-" + st + (item === active ? " is-active" : "") + (q(".errors, .errorlist", item) ? " has-error" : ""),
        '<span class="nzp-flag">' + meta.flag + "</span><span>" + meta.name + '</span><i title="' +
        ({ full: "To'liq", part: "Tavsif yo'q", empty: "To'ldirilmagan", del: "O'chiriladi" })[st] + '"></i>');
      b.type = "button"; b.setAttribute("role", "tab");
      b.addEventListener("click", function () { card._nzpActive = item; show(); });
      bar.appendChild(b);
      item.classList.add("nzp-tr-item");
      item.dataset.lang = code;
      // the locale select stays the source of truth, but needs no attention once the tab names it
      var sel = q('select[name$="-locale_code"]', item);
      if (sel) { var row = sel.closest(".form-group"); if (row) row.classList.add("nzp-locale-row"); }
    });
    var hint = el("span", "nzp-tabs-hint", "<i class=\"fas fa-circle-info\"></i> Bo'sh qoldirilgan til saqlanmaydi");
    bar.appendChild(hint);
    function show() {
      var cur = card._nzpActive || active;
      items.forEach(function (it, i) { var on = it === cur; it.hidden = !on; bar.children[i].classList.toggle("is-active", on); bar.children[i].setAttribute("aria-selected", on); });
    }
    card._nzpActive = active; show();
  }

  function wireTranslation(card) {
    buildTabs(card);
    card.addEventListener("input", function (e) {
      var t = e.target, item = t.closest(".inline-related");
      if (!item) return;
      if (/-name$/.test(t.name)) {
        var slug = q('input[name$="-slug"]', item);
        if (slug && (!slug.value || slug.dataset.auto === slug.value)) { slug.value = slugify(t.value); slug.dataset.auto = slug.value; }
        heroTitle();
      }
      clearTimeout(card._nzpT); card._nzpT = setTimeout(function () { refreshTabStates(card); }, 150);
    });
    card.addEventListener("change", function (e) { if (/-(DELETE|locale_code)$/.test(e.target.name)) buildTabs(card); });
  }
  function refreshTabStates(card) {
    var bar = q(".nzp-tabs", card); if (!bar) return;
    itemsOf(q(".inline-group", card) || card).sort(function (a, b) { return ORDER.indexOf(localeOf(a)) - ORDER.indexOf(localeOf(b)); })
      .forEach(function (it, i) { var b = bar.children[i]; if (b) b.className = b.className.replace(/is-(full|part|empty|del)/, "is-" + stateOf(it)); });
  }

  /* live hero title: the uz (else first filled) translation name */
  var heroH = q("[data-nzp-title]");
  function heroTitle() {
    if (!heroH || !q("[data-nzp-add]")) return;
    var names = {};
    qa('.nzp-translations input[name$="-name"]').forEach(function (i) { var it = i.closest(".inline-related"); if (it && i.value.trim()) names[localeOf(it)] = i.value.trim(); });
    var name = names.uz || names.ru || names.en || "";
    if (!name) { var main = q('#id_sku, #id_code, #id_slug, #id_full_name, #id_name'); name = main && main.value.trim(); }
    heroH.textContent = name || heroH.dataset.placeholder;
    heroH.classList.toggle("is-placeholder", !name);
  }

  /* ---------- section bar ---------- */
  function buildSections() {
    var nav = q("[data-nzp-sections]"); if (!nav) return;
    var cards = qa("#content-main form .col-lg-9 > .card > .card-body > .card, #content-main form .col-lg-9 > .card > .card-body > fieldset.nz-fieldset");
    var items = cards.map(function (c, i) {
      var h = q(":scope > .card-header", c) || q(":scope > legend", c);
      var label = h ? h.textContent.replace(/\s+/g, " ").trim() : "";
      if (!label) return null;
      if (!c.id) c.id = "nzp-sec-" + i;
      c.classList.add("nzp-section");
      return { id: c.id, label: label, el: c };
    }).filter(Boolean);
    if (items.length < 3) return;
    items.forEach(function (s) {
      var a = el("a", "nzp-sec", s.label); a.href = "#" + s.id;
      a.addEventListener("click", function (e) { e.preventDefault(); s.el.classList.remove("is-folded"); s.el.scrollIntoView({ behavior: "smooth", block: "start" }); });
      if (q(".errors, .errorlist", s.el)) a.classList.add("has-error");
      nav.appendChild(a);
    });
    nav.hidden = false;
    if ("IntersectionObserver" in window) {
      var links = qa(".nzp-sec", nav);
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          if (!en.isIntersecting) return;
          links.forEach(function (l) { l.classList.toggle("is-active", l.getAttribute("href") === "#" + en.target.id); });
        });
      }, { rootMargin: "-140px 0px -60% 0px" });
      items.forEach(function (s) { io.observe(s.el); });
    }
  }

  /* ---------- switches for the main form's booleans ---------- */
  function switches() {
    qa('.col-lg-9 .card:not(.nzp-translations) .form-group input[type=checkbox]').forEach(function (cb) {
      if (cb.closest(".inline-group") || cb.closest(".nzp-switch") || /-DELETE$/.test(cb.name) || cb.closest("ul, .nz-goal-choices") || cb.hasAttribute("data-nzi-perm") || cb.hasAttribute("data-no-switch")) return;
      var wrap = el("label", "nzp-switch"); cb.parentNode.insertBefore(wrap, cb); wrap.appendChild(cb);
      wrap.appendChild(el("span", "nzp-switch-ui")); var txt = el("span", "nzp-switch-text"); wrap.appendChild(txt);
      var sync = function () { txt.textContent = cb.checked ? "Ha" : "Yo'q"; wrap.classList.toggle("is-on", cb.checked); };
      cb.addEventListener("change", sync); sync();
    });
  }

  /* ---------- drag & drop image picker ---------- */
  function dropzones() {
    qa('input[type=file][name$="_upload"]').forEach(function (inp) {
      if (inp.closest(".inline-group")) return;
      var heroImg = q("[data-nzp-hero-img]");
      var current = heroImg ? heroImg.getAttribute("src") : "";
      var dz = el("div", "nzp-drop" + (current ? " has-image" : ""));
      dz.innerHTML = '<div class="nzp-drop-preview">' + (current ? '<img src="' + current + '" alt="">' : '<i class="fas fa-image"></i>') + "</div>" +
        '<div class="nzp-drop-text"><b>' + (current ? "Rasmni almashtirish" : "Rasm yuklash") + "</b><span>Faylni shu yerga tashlang yoki <u>tanlang</u></span>" +
        '<small>JPEG · PNG · WebP · 10 MB gacha</small><em class="nzp-drop-file" hidden></em></div>';
      inp.parentNode.insertBefore(dz, inp); dz.appendChild(inp);
      inp.classList.add("nzp-drop-input");
      function preview(file) {
        var name = q(".nzp-drop-file", dz);
        if (!file) { name.hidden = true; return; }
        if (!/^image\/(jpeg|png|webp)$/.test(file.type)) { name.hidden = false; name.className = "nzp-drop-file is-bad"; name.textContent = "Faqat JPEG, PNG yoki WebP"; return; }
        name.hidden = false; name.className = "nzp-drop-file"; name.textContent = file.name + " · " + Math.max(1, Math.round(file.size / 1024)) + " KB — saqlanganda yuklanadi";
        var r = new FileReader();
        r.onload = function () {
          q(".nzp-drop-preview", dz).innerHTML = '<img src="' + r.result + '" alt="">'; dz.classList.add("has-image");
          var media = q(".nzp-hero-media");
          if (media) media.innerHTML = '<img src="' + r.result + '" alt="" data-nzp-hero-img>';
        };
        r.readAsDataURL(file);
      }
      inp.addEventListener("change", function () { preview(inp.files[0]); });
      ["dragenter", "dragover"].forEach(function (t) { dz.addEventListener(t, function (e) { e.preventDefault(); dz.classList.add("is-over"); }); });
      ["dragleave", "drop"].forEach(function (t) { dz.addEventListener(t, function () { dz.classList.remove("is-over"); }); });
      dz.addEventListener("drop", function (e) {
        e.preventDefault();
        if (e.dataTransfer.files.length) { inp.files = e.dataTransfer.files; preview(inp.files[0]); markDirty(); }
      });
    });
  }

  /* ---------- flavour colour: swatch + hex + presets ---------- */
  function colourPicker() {
    var inp = q("#id_color_hex"); if (!inp) return;
    var PRESETS = ["#7b3f00", "#f5deb3", "#ff4f79", "#ffd23f", "#6a0dad", "#2ecc71", "#ff8c00", "#e8e8e8", "#3b82f6", "#111827"];
    var box = el("div", "nzp-colour");
    inp.parentNode.insertBefore(box, inp); box.appendChild(inp);
    var hex = el("input", "nzp-hex"); hex.type = "text"; hex.maxLength = 7; hex.value = inp.value; hex.setAttribute("aria-label", "HEX");
    box.appendChild(hex);
    var pre = el("div", "nzp-presets"); box.appendChild(pre);
    PRESETS.forEach(function (c) { var b = el("button", "nzp-preset"); b.type = "button"; b.style.background = c; b.title = c; b.addEventListener("click", function () { set(c); markDirty(); }); pre.appendChild(b); });
    function set(c) {
      inp.value = c; hex.value = c;
      var sw = q("[data-nzp-hero-swatch]"); if (sw) sw.style.background = c;
      var hero = q("[data-nzp-hero]"); if (hero) hero.style.setProperty("--t", c);
      qa(".nzp-preset", pre).forEach(function (b) { b.classList.toggle("is-on", b.title.toLowerCase() === c.toLowerCase()); });
    }
    inp.addEventListener("input", function () { set(inp.value); });
    hex.addEventListener("input", function () { var v = hex.value.trim(); if (/^#?[0-9a-f]{6}$/i.test(v)) set(v[0] === "#" ? v : "#" + v); });
    set(inp.value || "#10b981");
  }

  /* ---------- package picker: <select class="nzpk-select"> -> icon grid with search + a suggestion from the unit ---------- */
  var pkPop = null, pkOwner = null;
  function closePicker() { if (pkPop) { pkPop.remove(); pkPop = null; } if (pkOwner) { pkOwner.trigger.setAttribute("aria-expanded", "false"); pkOwner = null; } }
  function suggestSlug(row) {
    var unit = q('select[name$="-weight_unit"], #id_weight_unit', row), val = q('input[name$="-weight_value"], #id_weight_value', row);
    if (!unit || !unit.value) return "";
    var u = unit.value, n = parseFloat(val && val.value) || 0;
    if (u === "capsule" || u === "tablet") return "capsule-bottle";
    if (u === "chewable") return "blister";
    if (u === "gummy") return "jar";
    if (u === "ml") return n && n <= 100 ? "shot" : "bottle";
    if (u === "l") return "bottle";
    if (u === "kg") return n >= 1.5 ? "tub" : "jar";
    if (u === "g") return n && n <= 60 ? "sachet" : n >= 1500 ? "tub" : "jar";
    return "";
  }
  function pickerOptions(sel) {
    return Array.prototype.map.call(sel.options, function (o) { return { value: o.value, label: o.textContent.trim(), icon: o.dataset.icon || (o.value ? "fa-box" : "fa-ban"), sub: o.dataset.sub || "", slug: o.dataset.slug || "" }; });
  }
  function enhancePicker(sel) {
    if (sel.dataset.nzpk || sel.closest(".empty-form") || /__prefix__/.test(sel.name)) return;
    sel.dataset.nzpk = "1";
    var wrap = el("div", "nzpk"), trigger = el("button", "nzpk-trigger"), hint = el("button", "nzpk-hint");
    trigger.type = "button"; trigger.setAttribute("aria-haspopup", "listbox"); trigger.setAttribute("aria-expanded", "false");
    hint.type = "button"; hint.hidden = true;
    sel.parentNode.insertBefore(wrap, sel); wrap.appendChild(sel); wrap.appendChild(trigger); wrap.appendChild(hint);
    sel.classList.add("nzpk-native");
    var row = sel.closest("tr, .card-body, fieldset") || form;
    function paint() {
      var o = sel.options[sel.selectedIndex], has = o && o.value;
      trigger.innerHTML = '<span class="nzpk-ico"><i class="fas ' + (has ? (o.dataset.icon || "fa-box") : "fa-box-open") + '"></i></span><span class="nzpk-label">' +
        (has ? o.textContent.trim() : "Qadoq tanlang") + '</span><i class="fas fa-chevron-down nzpk-caret"></i>';
      trigger.classList.toggle("is-empty", !has);
      var slug = has ? "" : suggestSlug(row), opt = slug && pickerOptions(sel).find(function (x) { return x.slug === slug; });
      hint.hidden = !opt;
      if (opt) { hint.innerHTML = '<i class="fas fa-wand-magic-sparkles"></i> Tavsiya: <b><i class="fas ' + opt.icon + '"></i> ' + opt.label + "</b>"; hint.dataset.value = opt.value; }
    }
    hint.addEventListener("click", function () { sel.value = hint.dataset.value; sel.dispatchEvent(new Event("change", { bubbles: true })); });
    sel.addEventListener("change", paint);
    row.addEventListener("change", function (e) { if (/weight_(unit|value)$/.test(e.target.name || "")) paint(); });
    row.addEventListener("input", function (e) { if (/weight_value$/.test(e.target.name || "")) paint(); });
    trigger.addEventListener("click", function () { if (pkOwner && pkOwner.sel === sel) closePicker(); else openPicker(sel, trigger); });
    trigger.addEventListener("keydown", function (e) { if (e.key === "ArrowDown") { e.preventDefault(); openPicker(sel, trigger); } });
    paint();
  }
  function openPicker(sel, trigger) {
    closePicker();
    var opts = pickerOptions(sel), suggested = suggestSlug(sel.closest("tr, .card-body, fieldset") || form);
    pkPop = el("div", "nzpk-pop"); pkPop.setAttribute("role", "listbox");
    pkPop.innerHTML = '<label class="nzpk-search"><i class="fas fa-magnifying-glass"></i><input type="search" placeholder="Qidirish: banka, бутылка, pouch…" aria-label="Qadoq qidirish"></label><div class="nzpk-grid"></div>' +
      '<div class="nzpk-foot"><span>' + (opts.length - 1) + " ta qadoq turi</span>" + (window.NZPK_MANAGE ? '<a href="' + window.NZPK_MANAGE + '" target="_blank" rel="noopener"><i class="fas fa-gear"></i> Qadoqlarni boshqarish</a>' : "") + "</div>";
    document.body.appendChild(pkPop);
    pkOwner = { sel: sel, trigger: trigger }; trigger.setAttribute("aria-expanded", "true");
    var grid = q(".nzpk-grid", pkPop), input = q("input", pkPop), focusIdx = 0, shown = [];
    function render(term) {
      term = (term || "").toLowerCase().trim();
      shown = opts.filter(function (o) { return !term || (o.label + " " + o.sub + " " + o.slug).toLowerCase().indexOf(term) >= 0; });
      grid.innerHTML = "";
      shown.forEach(function (o, i) {
        var b = el("button", "nzpk-opt" + (o.value === sel.value ? " is-on" : "") + (!o.value ? " is-none" : "") + (o.slug && o.slug === suggested ? " is-suggested" : ""));
        b.type = "button"; b.setAttribute("role", "option"); b.setAttribute("aria-selected", o.value === sel.value);
        b.innerHTML = '<span class="nzpk-ico"><i class="fas ' + o.icon + '"></i></span><span class="nzpk-txt"><b>' + o.label + "</b><small>" + (o.value ? (o.sub || o.slug) : "qadoq ko'rsatilmaydi") + "</small></span>" +
          (o.slug && o.slug === suggested ? '<em title="O\'lchov birligiga mos">Tavsiya</em>' : "");
        b.addEventListener("click", function () { sel.value = o.value; sel.dispatchEvent(new Event("change", { bubbles: true })); closePicker(); trigger.focus(); });
        b.addEventListener("mouseenter", function () { focusIdx = i; mark(); });
        grid.appendChild(b);
      });
      if (!shown.length) grid.innerHTML = '<p class="nzpk-empty">Hech narsa topilmadi</p>';
      focusIdx = Math.max(0, shown.findIndex(function (o) { return o.value === sel.value; })); mark();
    }
    function mark() { qa(".nzpk-opt", grid).forEach(function (b, i) { b.classList.toggle("is-focus", i === focusIdx); if (i === focusIdx) b.scrollIntoView({ block: "nearest" }); }); }
    input.addEventListener("input", function () { render(input.value); });
    input.addEventListener("keydown", function (e) {
      var cols = Math.max(1, Math.round(grid.clientWidth / 190));
      if (e.key === "Escape") { closePicker(); trigger.focus(); }
      else if (e.key === "ArrowDown") { e.preventDefault(); focusIdx = Math.min(shown.length - 1, focusIdx + cols); mark(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); focusIdx = Math.max(0, focusIdx - cols); mark(); }
      else if (e.key === "ArrowRight") { focusIdx = Math.min(shown.length - 1, focusIdx + 1); mark(); }
      else if (e.key === "ArrowLeft") { focusIdx = Math.max(0, focusIdx - 1); mark(); }
      else if (e.key === "Enter") { e.preventDefault(); var b = qa(".nzpk-opt", grid)[focusIdx]; if (b) b.click(); }
    });
    render("");
    placePicker();
    setTimeout(function () { input.focus({ preventScroll: true }); }, 0);
  }
  function placePicker() {
    if (!pkPop || !pkOwner) return;
    var r = pkOwner.trigger.getBoundingClientRect(), w = Math.min(420, window.innerWidth - 24);
    if (r.bottom < 0 || r.top > window.innerHeight) { closePicker(); return; }
    pkPop.style.width = w + "px";
    pkPop.style.left = Math.max(12, Math.min(r.left, window.innerWidth - w - 12)) + "px";
    var below = window.innerHeight - r.bottom;
    if (below < 360 && r.top > below) { pkPop.style.top = "auto"; pkPop.style.bottom = (window.innerHeight - r.top + 6) + "px"; }
    else { pkPop.style.bottom = "auto"; pkPop.style.top = (r.bottom + 6) + "px"; }
  }
  document.addEventListener("mousedown", function (e) { if (pkPop && !pkPop.contains(e.target) && !(pkOwner && pkOwner.trigger.contains(e.target))) closePicker(); });
  window.addEventListener("resize", placePicker);
  document.addEventListener("scroll", function (e) { if (pkPop && !pkPop.contains(e.target)) placePicker(); }, true);

  /* ---------- unsaved-changes badge + Ctrl/Cmd+S ---------- */
  var dirty = q("[data-nzp-dirty]");
  // unnamed inputs (map search, link box, ...) are never submitted -- typing in them is not an unsaved change
  function markDirty(e) { if (e && e.target && e.target.tagName && !e.target.name) return; if (dirty) dirty.hidden = false; }
  form.addEventListener("input", markDirty);
  form.addEventListener("change", markDirty);
  document.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
      var btn = q('#content-main [name="_continue"]') || q('#content-main [name="_save"]');
      if (btn) { e.preventDefault(); btn.click(); }
    }
  });
  var actions = q("#jazzy-actions");
  if (actions && !q(".nzp-kbd", actions)) actions.appendChild(el("div", "nzp-kbd", "<kbd>Ctrl</kbd> + <kbd>S</kbd> — saqlab, tahrirda qolish"));

  /* names come first: lift the translations card above the other sections; "nzp-fold" sections fold */
  function arrange() {
    var tr = q("div.card.nzp-translations"), host = tr && tr.parentNode;
    if (tr && host && host.firstElementChild !== tr) host.insertBefore(tr, host.firstElementChild);
    qa("#content-main .card.nzp-fold").forEach(function (c) {
      var h = q(":scope > .card-header", c); if (!h) return;
      var open = !!q(".errors, .errorlist", c);
      c.classList.toggle("is-folded", !open);
      h.setAttribute("role", "button"); h.tabIndex = 0;
      h.appendChild(el("i", "fas fa-chevron-down nzp-fold-ico"));
      var t = function () { c.classList.toggle("is-folded"); };
      h.addEventListener("click", t);
      h.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); t(); } });
    });
  }

  function init() {
    arrange();
    qa("div.card.nzp-translations").forEach(wireTranslation);
    document.addEventListener("formset:added", function (e) {
      var card = e.target && e.target.closest && e.target.closest("div.card.nzp-translations");
      if (card) { card._nzpActive = e.target; buildTabs(card); }
      qa("select.nzpk-select", e.target).forEach(enhancePicker);
    });
    qa("select.nzpk-select").forEach(enhancePicker);
    switches(); dropzones(); colourPicker(); buildSections(); heroTitle();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
