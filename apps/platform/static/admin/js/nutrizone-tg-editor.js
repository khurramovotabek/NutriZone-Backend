/*
 * Telegram RichText editor (apps/telegram_bot/infrastructure/rich_text_field.py).
 * Turns every <textarea data-nztg> into: toolbar + contenteditable + live Telegram bubble preview + counter.
 * The textarea stays the form field; the server sanitizes again (telegram_html.sanitize).
 */
(function () {
  "use strict";

  var EMOJI = ["💪", "🔥", "⚡", "✅", "🎁", "🎉", "🏋️", "🥤", "💊", "🍫", "🛒", "📦", "🚚", "💳", "💰", "🏷️", "⭐", "🏆", "❤️", "👉", "👇", "📍", "📞", "🕒", "🆕", "🔝", "💯", "⏳", "🎯", "🧪", "🌿", "🥇", "🤝", "📢", "❗", "ℹ️"];
  var TOOLS = [
    ["bold", "B", "Qalin (Ctrl+B)", "fa-bold"],
    ["italic", "I", "Kursiv (Ctrl+I)", "fa-italic"],
    ["underline", "U", "Tagiga chizilgan (Ctrl+U)", "fa-underline"],
    ["strikeThrough", "S", "Ustidan chizilgan", "fa-strikethrough"],
    ["spoiler", "", "Yashirin matn (spoiler)", "fa-eye-slash"],
    ["code", "", "Kod / promokod", "fa-code"],
    ["|"],
    ["link", "", "Havola qo'shish", "fa-link"],
    ["quote", "", "Iqtibos", "fa-quote-right"],
    ["insertUnorderedList", "", "Ro'yxat", "fa-list-ul"],
    ["insertOrderedList", "", "Raqamli ro'yxat", "fa-list-ol"],
    ["|"],
    ["emoji", "", "Emoji", "fa-face-smile"],
    ["removeFormat", "", "Formatni tozalash", "fa-eraser"],
  ];

  function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }

  // Telegram HTML (newlines) -> editor HTML (<br>)
  function toEditor(v) { return (v || "").replace(/\r?\n/g, "<br>"); }

  function visibleLength(html) {
    var d = document.createElement("div");
    d.innerHTML = html.replace(/<br\s*\/?>/gi, "\n").replace(/<\/(div|p|li)>/gi, "\n");
    return (d.textContent || "").replace(/\n+$/, "").length;
  }

  function wrapSelection(tag, cls) {
    var sel = window.getSelection();
    if (!sel.rangeCount || sel.isCollapsed) return false;
    var range = sel.getRangeAt(0);
    var el = document.createElement(tag);
    if (cls) el.className = cls;
    try { range.surroundContents(el); } catch (e) { el.appendChild(range.extractContents()); range.insertNode(el); }
    sel.removeAllRanges();
    var r = document.createRange(); r.selectNodeContents(el); sel.addRange(r);
    return true;
  }

  function build(textarea) {
    if (textarea._nztg) return;
    textarea._nztg = true;
    var root = textarea.closest("[data-nztg-root]") || textarea.parentNode;
    var limit = parseInt(textarea.getAttribute("data-limit") || "4096", 10);

    var bar = document.createElement("div");
    bar.className = "nztg-bar";
    TOOLS.forEach(function (t) {
      if (t[0] === "|") { var s = document.createElement("span"); s.className = "nztg-sep"; bar.appendChild(s); return; }
      var b = document.createElement("button");
      b.type = "button"; b.className = "nztg-btn"; b.title = t[2]; b.setAttribute("aria-label", t[2]); b.dataset.cmd = t[0];
      b.innerHTML = '<i class="fas ' + t[3] + '" aria-hidden="true"></i>';
      bar.appendChild(b);
    });

    var editor = document.createElement("div");
    editor.className = "nztg-editor";
    editor.contentEditable = "true";
    editor.setAttribute("role", "textbox");
    editor.setAttribute("aria-multiline", "true");
    editor.dataset.placeholder = textarea.getAttribute("placeholder") || "Xabar matnini yozing…";
    editor.innerHTML = toEditor(textarea.value);

    var foot = document.createElement("div");
    foot.className = "nztg-foot";
    foot.innerHTML = '<span class="nztg-hint"><i class="fab fa-telegram"></i> Telegram formatlash: qalin, kursiv, spoiler, havola, iqtibos</span><span class="nztg-count"></span>';
    var counter = foot.querySelector(".nztg-count");

    var emoji = document.createElement("div");
    emoji.className = "nztg-emoji"; emoji.hidden = true;
    EMOJI.forEach(function (e) { var b = document.createElement("button"); b.type = "button"; b.textContent = e; emoji.appendChild(b); });

    var linkBox = document.createElement("div");
    linkBox.className = "nztg-linkbox"; linkBox.hidden = true;
    linkBox.innerHTML = '<input type="url" placeholder="https://nutrizone.uz/…"><button type="button" class="nztg-ok">Qo\'shish</button><button type="button" class="nztg-cancel">Bekor</button>';

    var preview = null;
    if (!textarea.hasAttribute("data-no-preview")) {
      preview = document.createElement("div");
      preview.className = "nztg-preview";
      preview.innerHTML = '<div class="nztg-preview-head"><i class="fab fa-telegram"></i> Telegram\'da shunday ko\'rinadi</div><div class="nztg-chat"><div class="nztg-bubble"><div class="nztg-bubble-text"></div><span class="nztg-time">' + new Date().toTimeString().slice(0, 5) + "</span></div></div>";
    }

    var wrap = document.createElement("div");
    wrap.className = "nztg-wrap";
    var left = document.createElement("div");
    left.className = "nztg-main";
    left.appendChild(bar); left.appendChild(linkBox); left.appendChild(emoji); left.appendChild(editor); left.appendChild(foot);
    wrap.appendChild(left);
    if (preview) wrap.appendChild(preview);
    textarea.style.display = "none";
    root.appendChild(wrap);

    var savedRange = null;
    function saveRange() { var s = window.getSelection(); if (s.rangeCount && editor.contains(s.anchorNode)) savedRange = s.getRangeAt(0).cloneRange(); }
    function restoreRange() { if (!savedRange) return; var s = window.getSelection(); s.removeAllRanges(); s.addRange(savedRange); }

    function sync() {
      var html = editor.innerHTML;
      if (editor.textContent.trim() === "" && !/<img/i.test(html)) html = "";
      textarea.value = html;
      var n = visibleLength(html);
      counter.textContent = n + " / " + limit;
      counter.classList.toggle("is-over", n > limit);
      counter.classList.toggle("is-near", n > limit * 0.9 && n <= limit);
      if (preview) preview.querySelector(".nztg-bubble-text").innerHTML = html || '<span class="nztg-empty">Matn hali yozilmagan</span>';
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    }

    bar.addEventListener("mousedown", function (e) { if (e.target.closest(".nztg-btn")) e.preventDefault(); });
    bar.addEventListener("click", function (e) {
      var btn = e.target.closest(".nztg-btn"); if (!btn) return;
      var cmd = btn.dataset.cmd;
      editor.focus();
      if (cmd === "spoiler") wrapSelection("span", "tg-spoiler");
      else if (cmd === "code") wrapSelection("code");
      else if (cmd === "quote") { if (!wrapSelection("blockquote")) document.execCommand("formatBlock", false, "blockquote"); }
      else if (cmd === "link") { saveRange(); linkBox.hidden = false; emoji.hidden = true; linkBox.querySelector("input").value = ""; linkBox.querySelector("input").focus(); return; }
      else if (cmd === "emoji") { saveRange(); emoji.hidden = !emoji.hidden; linkBox.hidden = true; return; }
      else document.execCommand(cmd, false, null);
      sync();
    });
    emoji.addEventListener("click", function (e) {
      var b = e.target.closest("button"); if (!b) return;
      editor.focus(); restoreRange();
      document.execCommand("insertText", false, b.textContent);
      saveRange(); sync();
    });
    function applyLink() {
      var url = linkBox.querySelector("input").value.trim();
      linkBox.hidden = true;
      if (!/^(https?:\/\/|tg:\/\/|mailto:|tel:)/i.test(url)) return;
      editor.focus(); restoreRange();
      var sel = window.getSelection();
      if (sel.isCollapsed) document.execCommand("insertHTML", false, '<a href="' + esc(url) + '">' + esc(url) + "</a>");
      else document.execCommand("createLink", false, url);
      sync();
    }
    linkBox.querySelector(".nztg-ok").addEventListener("click", applyLink);
    linkBox.querySelector(".nztg-cancel").addEventListener("click", function () { linkBox.hidden = true; });
    linkBox.querySelector("input").addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); applyLink(); } });

    editor.addEventListener("input", sync);
    editor.addEventListener("keyup", saveRange);
    editor.addEventListener("mouseup", saveRange);
    editor.addEventListener("paste", function (e) {
      // keep pasted text clean: Word / Google Docs markup never reaches the post
      var text = (e.clipboardData || window.clipboardData).getData("text/plain");
      if (text == null) return;
      e.preventDefault();
      document.execCommand("insertText", false, text);
    });
    sync();
  }

  function init(root) { (root || document).querySelectorAll("textarea[data-nztg]").forEach(build); }
  window.NZTG = { init: init };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function () { init(); });
  else init();
})();
