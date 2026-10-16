/* Support paneli (templates/admin/support/board.html): Kanban of support cases, drag & drop between statuses,
   quick "log a call" form, search / topic filter, auto-refresh every 30 s. */
(function () {
  "use strict";
  var root = document.querySelector(".sup");
  if (!root) return;
  var board = root.querySelector("[data-board]"), form = root.querySelector("[data-new]");
  var csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || (document.querySelector("[name=csrfmiddlewaretoken]") || {}).value || "";
  var dragging = null, timer = null;

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function when(iso) {
    if (!iso) return "";
    var d = new Date(iso), now = new Date(), min = Math.round((d - now) / 60000);
    var hhmm = d.toLocaleTimeString("uz-UZ", { hour: "2-digit", minute: "2-digit" });
    if (d.toDateString() === now.toDateString()) return "bugun " + hhmm;
    var t = new Date(now); t.setDate(now.getDate() + 1);
    if (d.toDateString() === t.toDateString()) return "ertaga " + hhmm;
    return d.toLocaleDateString("uz-UZ", { day: "2-digit", month: "2-digit" }) + " " + hhmm + (min < 0 ? "" : "");
  }
  function post(url, data) {
    return fetch(url, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf }, credentials: "same-origin", body: JSON.stringify(data) })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok && b.ok, body: b }; }); });
  }
  function card(c) {
    return '<article class="sup-card' + (c.late ? " is-late" : "") + (c.priority === "high" ? " is-high" : "") + '" draggable="true" data-id="' + c.id + '">' +
      '<div class="sup-card-top"><b>' + esc(c.name) + '</b><span>' + esc(c.number) + "</span></div>" +
      '<a class="sup-phone" href="tel:' + esc(c.phone) + '"><i class="fas fa-phone"></i> ' + esc(c.phone) + "</a>" +
      '<p>' + esc(c.summary) + "</p>" +
      '<div class="sup-card-foot"><span class="sup-tag">' + esc(c.topic) + "</span>" +
      (c.next ? '<span class="sup-next"><i class="fas fa-clock"></i> ' + when(c.next) + "</span>" : "") +
      '<a href="' + c.url + '" class="sup-open" title="Ochish"><i class="fas fa-arrow-up-right-from-square"></i></a></div></article>';
  }
  function render(data) {
    board.innerHTML = data.columns.map(function (col) {
      return '<section class="sup-col' + (col.open ? "" : " is-closed") + '" data-status="' + col.key + '" style="--c:' + col.color + '">' +
        '<header><i class="fas ' + col.icon + '"></i> ' + esc(col.label) + ' <span class="sup-count">' + col.cards.length + "</span></header>" +
        '<div class="sup-list">' + (col.cards.map(card).join("") || '<p class="sup-empty">Bo\'sh</p>') + "</div></section>";
    }).join("");
  }
  function load() {
    var q = root.querySelector("[data-q]").value, topic = root.querySelector("[data-topic]").value;
    var url = root.dataset.data + "?q=" + encodeURIComponent(q) + "&topic=" + encodeURIComponent(topic);
    return fetch(url, { credentials: "same-origin" }).then(function (r) { return r.json(); }).then(render).catch(function () {});
  }

  board.addEventListener("dragstart", function (e) {
    var el = e.target.closest(".sup-card"); if (!el) return;
    dragging = el; el.classList.add("is-drag"); e.dataTransfer.effectAllowed = "move";
  });
  board.addEventListener("dragend", function () { if (dragging) dragging.classList.remove("is-drag"); dragging = null; board.querySelectorAll(".is-over").forEach(function (c) { c.classList.remove("is-over"); }); });
  board.addEventListener("dragover", function (e) { var col = e.target.closest(".sup-col"); if (!col || !dragging) return; e.preventDefault(); board.querySelectorAll(".is-over").forEach(function (c) { if (c !== col) c.classList.remove("is-over"); }); col.classList.add("is-over"); });
  board.addEventListener("drop", function (e) {
    var col = e.target.closest(".sup-col"); if (!col || !dragging) return;
    e.preventDefault();
    var id = dragging.dataset.id, status = col.dataset.status;
    if (dragging.closest(".sup-col") === col) return;
    var note = (status === "lost" || status === "callback") ? (window.prompt(status === "lost" ? "Rad etish sababi (ixtiyoriy):" : "Qachon va nima uchun qayta qo'ng'iroq (ixtiyoriy):") || "") : "";
    col.querySelector(".sup-list").prepend(dragging);
    post(root.dataset.move, { id: id, status: status, note: note }).then(function (r) { if (!r.ok) alert(r.body.error || "Xato"); load(); });
  });

  root.querySelector("[data-open-new]").addEventListener("click", function () { form.hidden = !form.hidden; if (!form.hidden) form.phone.focus(); });
  root.querySelector("[data-close-new]").addEventListener("click", function () { form.hidden = true; });
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var data = {}; new FormData(form).forEach(function (v, k) { data[k] = v; });
    var err = form.querySelector("[data-err]"); err.textContent = "";
    post(root.dataset.create, data).then(function (r) {
      if (!r.ok) { err.textContent = r.body.error || "Saqlanmadi"; return; }
      form.reset(); form.hidden = true; load();
    });
  });
  var debounce;
  root.querySelector("[data-q]").addEventListener("input", function () { clearTimeout(debounce); debounce = setTimeout(load, 300); });
  root.querySelector("[data-topic]").addEventListener("change", load);
  load(); timer = setInterval(function () { if (!document.hidden && !dragging) load(); }, 30000);
})();
