/*
 * Dashboard phrases rendered by scripts (charts, WMS desk, chat desk...) in the staff language.
 * The server already translated the page HTML (apps/platform/infrastructure/admin_i18n.py); this does the same
 * for text added later, with the same catalog (window.NZ_PHRASES from /django-admin/i18n/phrases.<lang>.js)
 * and the same rules: whole phrase, then numbers as {0}, {1}..., then decoration / separators.
 */
(function () {
  "use strict";
  var data = window.NZ_PHRASES;
  if (!data || !data.t) return;
  var table = data.t;
  var SKIP = { SCRIPT: 1, STYLE: 1, TEXTAREA: 1, PRE: 1, CODE: 1, NOSCRIPT: 1 };
  var ATTRS = ["placeholder", "title", "aria-label", "alt", "data-label", "data-title", "data-confirm", "data-nzi-confirm"];
  var SEPARATORS = [" | ", " · ", " • ", " — ", " – ", " - ", " → ", " ← ", ": ", " / "];
  var PREFIXES = ["Change ", "Add ", "View ", "Delete ", "Select ", "Edit ", "Изменить ", "Добавить ", "Просмотреть ", "Удалить ", "Выбрать ", "Выберите "];
  var NUM = /\d+(?:[  .,:]\d+)*/g;
  var LETTER = /[A-Za-zÀ-ɏЀ-ӿ]/;
  var EDGE = /^([^A-Za-z0-9\u00c0-\u024f\u0400-\u04ff]*)([\s\S]*?)([^A-Za-z0-9\u00c0-\u024f\u0400-\u04ff)\]»”"']*)$/;

  function norm(s) { return s.replace(/[‘’ʻʼ`´]/g, "'").replace(/\s+/g, " ").trim(); }

  function lookup(s) {
    var n = norm(s);
    if (Object.prototype.hasOwnProperty.call(table, n)) return table[n];
    var nums = [];
    var templ = n.replace(NUM, function (m) { nums.push(m); return "{" + (nums.length - 1) + "}"; });
    if (nums.length && Object.prototype.hasOwnProperty.call(table, templ)) {
      var out = table[templ];
      for (var i = 0; i < nums.length; i++) out = out.split("{" + i + "}").join(nums[i]);
      return out;
    }
    return null;
  }

  function translate(text, depth) {
    depth = depth || 0;
    var core = text.trim();
    if (!core || core.length > 600 || !LETTER.test(core)) return null;
    var hit = lookup(core);
    var m = EDGE.exec(core);
    var decorated = !!(m && (m[1] || m[3]) && m[2] && LETTER.test(m[2]));
    if (hit === null && decorated) {
      var bare = lookup(m[2]);
      if (bare !== null) hit = m[1] + bare + m[3];
    }
    if (hit === null) {
      for (var p = 0; p < PREFIXES.length; p++) {
        if (core.indexOf(PREFIXES[p]) === 0 && core.length > PREFIXES[p].length) {
          var rest = lookup(core.slice(PREFIXES[p].length));
          if (rest !== null) hit = (lookup(PREFIXES[p].trim()) || PREFIXES[p].trim()) + " " + rest;
          break;
        }
      }
    }
    if (hit === null && depth < 3) {
      for (var i = 0; i < SEPARATORS.length; i++) {
        var sep = SEPARATORS[i];
        if (core.indexOf(sep) < 0) continue;
        var parts = core.split(sep), changed = false;
        var done = parts.map(function (x) { var t = translate(x, depth + 1); if (t !== null) changed = true; return t === null ? x : t; });
        if (changed) { hit = done.join(sep); break; }
      }
    }
    if (hit === null && decorated && depth < 3) {
      var inner = translate(m[2], depth + 1);
      if (inner !== null) hit = m[1] + inner + m[3];
    }
    if (hit === null) return null;
    var lead = text.match(/^\s*/)[0], trail = text.match(/\s*$/)[0];
    return lead + hit + trail;
  }

  function skipped(el) {
    for (var e = el; e && e.nodeType === 1; e = e.parentNode) {
      if (SKIP[e.tagName] || e.isContentEditable || e.getAttribute("translate") === "no" || (e.classList && e.classList.contains("notranslate"))) return true;
    }
    return false;
  }

  function doText(node) {
    if (!node.parentNode || skipped(node.parentNode)) return;
    var t = translate(node.nodeValue);
    if (t !== null && t !== node.nodeValue) node.nodeValue = t;
  }

  function doElement(el) {
    if (skipped(el)) return;
    for (var i = 0; i < ATTRS.length; i++) {
      var v = el.getAttribute(ATTRS[i]);
      if (v) { var t = translate(v); if (t !== null && t !== v) el.setAttribute(ATTRS[i], t); }
    }
    if (el.tagName === "INPUT" && /^(submit|button|reset)$/i.test(el.type) && el.value) {
      var tv = translate(el.value); if (tv !== null) el.value = tv;
    }
    var walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    var n;
    while ((n = walker.nextNode())) {
      if (n.nodeType === 3) doText(n);
      else if (SKIP[n.tagName]) continue;
      else for (var j = 0; j < ATTRS.length; j++) {
        var a = n.getAttribute(ATTRS[j]);
        if (a) { var ta = translate(a); if (ta !== null && ta !== a) n.setAttribute(ATTRS[j], ta); }
      }
    }
  }

  var busy = false;
  var observer = new MutationObserver(function (records) {
    if (busy) return;
    busy = true;
    try {
      records.forEach(function (r) {
        if (r.type === "characterData") doText(r.target);
        else if (r.type === "attributes") { if (r.target.nodeType === 1) doElement(r.target); }
        else r.addedNodes.forEach(function (n) { if (n.nodeType === 3) doText(n); else if (n.nodeType === 1) doElement(n); });
      });
    } finally {
      observer.takeRecords();
      busy = false;
    }
  });

  window.nzTranslate = function (text) { var t = translate(String(text)); return t === null ? String(text) : t; };

  function start() {
    doElement(document.body);
    observer.observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRS });
  }
  if (document.body) start(); else document.addEventListener("DOMContentLoaded", start);
})();
