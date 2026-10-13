/*
 * NutriZone Dashboard → Chat markazi (templates/admin/chat_admin.html, apps/platform/infrastructure/chat_view.py).
 * Queue | thread | customer profile. The admin uses session auth (the chat socket is JWT-only), so the desk polls:
 * the queue every 6 s, the open thread every 3 s with ?after=<last message time> (cheap), paused while the tab is
 * hidden. Replies, stickers and photos go through the desk API, which pushes them to the customer in real time.
 */
(function () {
  "use strict";

  var cfg = JSON.parse(document.getElementById("nzc-config").textContent);
  var root = document.getElementById("nzc");
  var $ = function (s, r) { return (r || root).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || root).querySelectorAll(s)); };
  var S = { filter: cfg.filter, q: "", rows: cfg.rows || [], active: null, conv: null, msgs: [], lastAt: null, sending: false, waiting: null, quickId: null };
  var baseTitle = document.title;

  // ---------------------------------------------------------------- helpers
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function url(name, id, action) { return cfg.urls[name].replace("__", id || "").replace("--", action || ""); }
  function csrf() { var el = document.querySelector("[name=csrfmiddlewaretoken]"); return el ? el.value : ""; }
  function api(u, opts) {
    return fetch(u, Object.assign({ credentials: "same-origin" }, opts || {})).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok || j.success === false) throw new Error((j.error && j.error.message) || "Xatolik"); return j.data; });
    });
  }
  function post(u, body) { return api(u, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() }, body: JSON.stringify(body || {}) }); }
  function ago(iso) {
    if (!iso) return "";
    var s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 60) return "hozir";
    if (s < 3600) return Math.floor(s / 60) + " daq";
    if (s < 86400) return Math.floor(s / 3600) + " soat";
    if (s < 604800) return Math.floor(s / 86400) + " kun";
    return new Date(iso).toLocaleDateString("ru-RU");
  }
  function hm(iso) { var d = new Date(iso); return ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2); }
  function day(iso) {
    var d = new Date(iso), t = new Date(), y = new Date(Date.now() - 864e5);
    if (d.toDateString() === t.toDateString()) return "Bugun";
    if (d.toDateString() === y.toDateString()) return "Kecha";
    return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" });
  }
  function initials(n) { return (n || "#").split(/\s+/).slice(0, 2).map(function (p) { return p[0] || ""; }).join("").toUpperCase() || "#"; }
  function avatar(c, size) {
    return c && c.avatar ? '<span class="nzc-av ' + (size || "") + '"><img src="' + esc(c.avatar) + '" alt=""></span>'
      : '<span class="nzc-av ' + (size || "") + '" data-tone="' + ((c && c.name ? c.name.charCodeAt(0) : 0) % 6) + '">' + esc(initials(c && c.name)) + "</span>";
  }
  function money(n) { return Math.round(Number(n) || 0).toLocaleString("ru-RU").replace(/ /g, " "); }
  function toast(text, bad) {
    var el = document.createElement("div");
    el.className = "nzc-toast" + (bad ? " bad" : ""); el.textContent = text;
    document.body.appendChild(el); setTimeout(function () { el.remove(); }, bad ? 5000 : 2500);
  }

  // ---------------------------------------------------------------- queue
  function renderTabs(stats) {
    $$(".nzc-tabs button").forEach(function (b) { b.classList.toggle("on", b.getAttribute("data-f") === S.filter); });
    if (!stats) return;
    Object.keys(stats).forEach(function (k) {
      var c = $('[data-c="' + k + '"]'); if (c) c.textContent = stats[k];
      var kpi = $('[data-k="' + k + '"] b'); if (k === "review" && $('[data-k="review"]')) $('[data-k="review"]').classList.toggle("bad", stats[k] > 0); if (kpi) kpi.textContent = k === "first_reply" ? (stats[k] == null ? "—" : stats[k] + " daq") : k === "csat" ? (stats[k] == null ? "—" : stats[k] + " ★") : stats[k];
    });
    var hours = $("[data-hours]");
    if (hours) { hours.classList.toggle("off", !stats.open_now); hours.querySelector("b").textContent = stats.open_now ? "Ish vaqti" : "Ish vaqtidan tashqari"; hours.querySelector("small").textContent = stats.hours; }
    if (S.waiting !== null && stats.waiting > S.waiting) ping();
    S.waiting = stats.waiting;
    document.title = (stats.waiting ? "(" + stats.waiting + ") " : "") + baseTitle;
  }
  function renderList() {
    var list = $("[data-list]");
    if (!S.rows.length) {
      list.innerHTML = '<div class="nzc-empty"><i class="fas ' + (S.filter === "waiting" ? "fa-circle-check" : "fa-inbox") + '" aria-hidden="true"></i><b>' +
        (S.q ? "Hech narsa topilmadi" : S.filter === "waiting" ? "Hamma savollarga javob berilgan" : "Suhbat yo'q") + "</b></div>";
      return;
    }
    list.innerHTML = S.rows.map(function (r) {
      var badge = r.type === "customer_sales" ? '<em class="store"><i class="fas fa-store" aria-hidden="true"></i> ' + esc(r.store || "Do'kon") + "</em>" : r.assigned === "me" ? '<em class="me">mening</em>' : r.assigned === "other" ? '<em>band</em>' : '<em class="free">yangi</em>';
      return '<button type="button" class="nzc-item' + (r.id === S.active ? " on" : "") + (r.unread ? " unread" : "") + (r.review ? " is-review" : "") + '" data-id="' + r.id + '" role="listitem">' +
        avatar(r.customer) + '<span class="nzc-item-main"><span class="nzc-item-top"><b>' + esc(r.customer.name) + "</b><time>" + ago(r.last_at) + "</time></span>" +
        '<span class="nzc-item-last">' + (r.last_from_customer ? "" : '<i class="fas fa-reply" aria-hidden="true"></i> ') + esc(r.last || "Xabar yo'q") + "</span>" +
        '<span class="nzc-item-meta">' + badge + (r.waiting_since ? '<em class="wait"><i class="fas fa-hourglass-half" aria-hidden="true"></i> ' + ago(r.waiting_since) + "</em>" : "") +
        (r.review ? '<em class="review" title="Past baho — nazoratda"><i class="fas fa-eye" aria-hidden="true"></i> ' + r.review.score + "★ nazoratda</em>" : r.rating ? '<em class="rate">' + "★".repeat(r.rating) + "</em>" : "") + (r.unread ? '<span class="nzc-badge">' + r.unread + "</span>" : "") + "</span></span></button>";
    }).join("");
  }
  function loadQueue() {
    return api(cfg.urls.queue + "?f=" + S.filter + "&q=" + encodeURIComponent(S.q)).then(function (d) { S.rows = d.rows; renderList(); renderTabs(d.stats); }).catch(function () {});
  }

  // ---------------------------------------------------------------- thread
  function card(c) {
    if (!c) return '<div class="nzc-card-msg missing"><i class="fas fa-circle-exclamation" aria-hidden="true"></i> Mahsulot yoki buyurtma endi mavjud emas</div>';
    var href = (cfg.site || "") + c.url;
    if (c.kind === "order") {
      return '<a class="nzc-card-msg order" href="' + esc(href) + '" target="_blank" rel="noopener"><span class="ic"><i class="fas fa-receipt" aria-hidden="true"></i></span><span><small>Buyurtma · ' + esc(c.date) + '</small><b>' + esc(c.title) + "</b><em>" + esc(c.status_label) + " · " + c.units + " dona · " + money(c.total) + " so'm</em>" + (c.eta ? '<em class="eta"><i class="fas fa-truck" aria-hidden="true"></i> Taxminan ' + esc(c.eta) + "</em>" : "") + "</span></a>";
    }
    return '<a class="nzc-card-msg" href="' + esc(href) + '" target="_blank" rel="noopener">' + (c.image ? '<img src="' + esc(c.image) + '" alt="">' : '<span class="ic"><i class="fas fa-box" aria-hidden="true"></i></span>') +
      '<span><small>Mahsulot</small><b>' + esc(c.title) + "</b><em>" + (c.price ? money(c.price) + " so'm" : "narx yo'q") + ' · <span class="' + (c.in_stock ? "ok" : "no") + '">' + (c.in_stock ? "mavjud" : "tugagan") + "</span></em></span></a>";
  }
  function bubble(m) {
    var body;
    if (m.kind === "system" && m.type === "card") return '<div class="nzc-system has-card"><i class="fas fa-robot" aria-hidden="true" title="Bot"></i>' + card(m.card) + "<small>" + hm(m.at) + "</small></div>";
    if (m.kind === "system") return '<div class="nzc-system"><i class="fas fa-robot" aria-hidden="true"></i><p>' + esc(m.content) + '</p><small>' + hm(m.at) + "</small></div>";
    if (m.deleted) body = '<i class="nzc-deleted">Xabar o\'chirilgan</i>';
    else if (m.type === "card") body = card(m.card);
    else if (m.type === "sticker" && m.sticker) body = '<span class="nzc-sticker"><span>' + m.sticker.emoji + "</span><small>" + esc(m.sticker.label) + "</small></span>";
    else if (m.attachment) {
      var a = m.attachment;
      body = a.type === "image" ? '<a href="' + esc(a.url) + '" target="_blank" rel="noopener" class="nzc-img"><img src="' + esc(a.url) + '" alt="' + esc(a.name || "Rasm") + '"></a>'
        : a.type === "video" ? '<video src="' + esc(a.url) + '" controls preload="metadata" class="nzc-video"></video>'
        : '<a href="' + esc(a.url) + '" target="_blank" rel="noopener" class="nzc-file"><i class="fas fa-file" aria-hidden="true"></i> ' + esc(a.name || "Fayl") + "</a>";
      if (m.content) body += '<p>' + esc(m.content) + "</p>";
    } else body = "<p>" + esc(m.content) + "</p>";
    var side = m.kind === "customer" ? "in" : "out";
    var ticks = side === "out" ? (m.read_at ? '<i class="fas fa-check-double read" title="O\'qildi" aria-label="O\'qildi"></i>' : '<i class="fas fa-check" title="Yuborildi" aria-label="Yuborildi"></i>') : "";
    return '<div class="nzc-msg ' + side + " " + m.kind + (m.type === "sticker" || m.type === "card" ? " is-sticker" : "") + '" data-mid="' + m.id + '">' +
      (side === "out" ? '<small class="nzc-who">' + esc(m.who) + "</small>" : "") + '<div class="nzc-bubble">' + body +
      '<span class="nzc-time">' + (m.edited ? "tahrirlangan · " : "") + hm(m.at) + " " + ticks + "</span></div></div>";
  }
  function renderMsgs(scroll) {
    var box = $("[data-msgs]"), lastDay = "", html = "";
    S.msgs.forEach(function (m) { var d = day(m.at); if (d !== lastDay) { html += '<div class="nzc-day"><span>' + d + "</span></div>"; lastDay = d; } html += bubble(m); });
    var atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
    box.innerHTML = html || '<div class="nzc-empty"><b>Hali xabar yo\'q</b></div>';
    if (scroll || atBottom) box.scrollTop = box.scrollHeight;
  }
  function renderHead() {
    var c = S.conv, p = S.profile && S.profile.customer;
    var status = { open: ["Ochiq", "#16a34a"], closed: ["Yopilgan", "#64748b"], archived: ["Arxivda", "#94a3b8"] }[c.status] || [c.status, "#64748b"];
    var actions = [];
    if (c.can_reply && c.status === "open" && c.assigned !== "me") actions.push('<button type="button" class="nzc-act primary" data-act="take"><i class="fas fa-hand" aria-hidden="true"></i> O\'zimga olish</button>');
    if (c.status === "open") actions.push('<button type="button" class="nzc-act" data-act="close"><i class="fas fa-circle-check" aria-hidden="true"></i> Yopish</button>');
    if (c.status === "closed") actions.push('<button type="button" class="nzc-act" data-act="reopen"><i class="fas fa-rotate-left" aria-hidden="true"></i> Qayta ochish</button>', '<button type="button" class="nzc-act" data-act="archive"><i class="fas fa-box-archive" aria-hidden="true"></i> Arxivlash</button>');
    $("[data-head]").innerHTML = '<button type="button" class="nzc-back" data-back aria-label="Orqaga"><i class="fas fa-arrow-left" aria-hidden="true"></i></button>' + avatar(p || { name: "Mijoz" }, "lg") +
      '<div class="nzc-head-main"><b>' + esc(p ? p.name : "Mijoz") + "</b><small>" + esc(p ? p.phone : "") + (c.store ? " · " + esc(c.store) : "") + "</small>" +
      '<span class="nzc-chips"><span class="nzi-pill" style="--t:' + status[1] + '">' + status[0] + "</span>" + (c.type === "customer_sales" ? '<span class="nzi-chip" style="--t:#ea580c"><i class="fas fa-store" aria-hidden="true"></i> Do\'kon suhbati</span>' : '<span class="nzi-chip" style="--t:#4f46e5"><i class="fas fa-headset" aria-hidden="true"></i> Qo\'llab-quvvatlash</span>') +
      (c.assigned_name ? '<span class="nzi-chip" style="--t:#0891b2"><i class="fas fa-user-tie" aria-hidden="true"></i> ' + esc(c.assigned_name) + "</span>" : "") + "</span></div>" +
      '<div class="nzc-head-actions">' + actions.join("") + "</div>";
    renderReview();
    var banner = $("[data-banner]"), composer = $("[data-composer]");
    if (!c.can_reply) { banner.innerHTML = '<i class="fas fa-store" aria-hidden="true"></i> Bu mijoz va do\'kon o\'rtasidagi suhbat — javobni do\'kon egasi «Mening do\'konim» sahifasida beradi. Siz faqat kuzatasiz.'; banner.hidden = false; composer.hidden = true; }
    else if (c.status !== "open") { banner.innerHTML = '<i class="fas fa-lock" aria-hidden="true"></i> Suhbat yopilgan. Javob yozish uchun «Qayta ochish»ni bosing.'; banner.hidden = false; composer.hidden = true; }
    else { banner.hidden = true; composer.hidden = false; }
  }
  function stars(n) { return "★".repeat(n) + "<i>" + "★".repeat(5 - n) + "</i>"; }
  function renderReview() {
    var box = $("[data-review]"), r = S.conv && S.conv.review;
    if (!r) { box.hidden = true; box.innerHTML = ""; return; }
    box.innerHTML = '<i class="fas fa-eye" aria-hidden="true"></i><b>Nazoratda</b><span class="stars">' + stars(r.score) + "</span>" +
      "<p>" + (r.comment ? "«" + esc(r.comment) + "»" : "Mijoz izoh qoldirmagan.") + " Mijoz bilan bog'lanib, natijani yozing.</p>" +
      '<form data-resolve><input type="text" maxlength="500" placeholder="Nima qilindi? (masalan: qo\'ng\'iroq qilindi, kupon berildi)" data-note aria-label="Menejer izohi">' +
      '<button type="submit" class="nzc-act primary"><i class="fas fa-check" aria-hidden="true"></i> Hal qilindi</button></form>';
    box.hidden = false;
  }
  function renderProfile() {
    var p = S.profile, box = $("[data-profile]");
    if (!p || !p.customer) { box.innerHTML = '<div class="nzc-empty small">Mijoz topilmadi.</div>'; return; }
    var c = p.customer, l = p.loyalty;
    box.innerHTML = '<section class="nzc-card nzc-who-card">' + avatar(c, "xl") + "<b>" + esc(c.name) + '</b><small>' + esc(c.phone) + "</small>" +
      '<span class="nzc-chips center">' + (c.telegram ? '<span class="nzi-chip" style="--t:#0891b2"><i class="fab fa-telegram" aria-hidden="true"></i> ' + esc(c.telegram.indexOf("ulangan") === 0 ? c.telegram : "@" + c.telegram) + "</span>" : "") +
      (l && l.tier ? '<span class="nzi-chip" style="--t:' + esc(l.color) + '">' + esc(l.tier) + "</span>" : "") + "</span>" +
      '<a class="nzc-link" href="' + esc(c.url) + '"><i class="fas fa-user" aria-hidden="true"></i> Mijoz kartasi</a></section>' +
      '<section class="nzc-card nzc-nums"><div><b>' + p.order_count + '</b><small>buyurtma</small></div><div><b>' + money(p.spent) + '</b><small>so\'m xarid</small></div><div><b>' + money(l ? l.balance : 0) + '</b><small>coin</small></div><div><b>' + p.other_chats + '</b><small>boshqa suhbat</small></div></section>' +
      '<section class="nzc-card"><h4>So\'nggi buyurtmalar</h4>' + (p.orders.length ? '<ul class="nzc-orders">' + p.orders.map(function (o) {
        return '<li><a href="' + esc(o.url) + '"><b>' + esc(o.number) + "</b><small>" + esc(o.date) + '</small></a><span><b>' + money(o.total) + ' so\'m</b><em style="--t:' + esc(o.color) + '">' + esc(o.status) + "</em></span></li>";
      }).join("") + "</ul>" : '<p class="nzc-muted">Hali buyurtma bermagan.</p>') + "</section>" +
      '<section class="nzc-card"><h4>Suhbat</h4><p class="nzc-muted">Boshlangan: ' + esc(S.conv.created) + "<br>Xabarlar: " + S.msgs.length + "</p>" +
      (S.conv.rating ? '<div class="nzc-rating"><span>' + "★".repeat(S.conv.rating.score) + '<i>' + "★".repeat(5 - S.conv.rating.score) + "</i></span>" + (S.conv.rating.comment ? "<p>«" + esc(S.conv.rating.comment) + "»</p>" : "") + "</div>" : "") +
      (p.ratings && p.ratings.count ? '<p class="nzc-muted">Mijozning o\'rtacha bahosi: <b>' + p.ratings.avg + " ★</b> (" + p.ratings.count + ")</p>" : "") + "</section>";
  }
  function openConv(id, silent) {
    S.active = id; S.msgs = []; S.lastAt = null; S.profile = null; S.vars = {};
    root.classList.add("has-thread");
    $("[data-placeholder]").hidden = true; $("[data-head]").hidden = false; $("[data-msgs]").hidden = false;
    $("[data-msgs]").innerHTML = '<div class="nzc-empty"><i class="fas fa-circle-notch fa-spin" aria-hidden="true"></i></div>';
    renderList();
    try { history.replaceState(null, "", "?c=" + id + "&f=" + S.filter); } catch (e) { /* ignore */ }
    return api(url("conversation", id)).then(function (d) {
      if (S.active !== id) return;
      S.conv = d.conversation; S.profile = d.profile; S.msgs = d.messages; S.vars = d.vars || {};
      S.lastAt = S.msgs.length ? S.msgs[S.msgs.length - 1].at : null;
      renderHead(); renderMsgs(true); renderProfile();
      if (!silent) { var input = $("[data-input]"); if (input && !$("[data-composer]").hidden) input.focus(); }
      loadQueue();
    }).catch(function (e) { toast(e.message, true); });
  }
  function pollThread() {
    if (!S.active || document.hidden) return;
    api(url("conversation", S.active) + (S.lastAt ? "?after=" + encodeURIComponent(S.lastAt) : "")).then(function (d) {
      var known = {}; S.msgs.forEach(function (m) { known[m.id] = 1; });
      var fresh = d.messages.filter(function (m) { return !known[m.id]; });
      var statusChanged = !S.conv || d.conversation.status !== S.conv.status || d.conversation.assigned !== S.conv.assigned || !!d.conversation.review !== !!S.conv.review;
      S.conv = d.conversation;
      if (fresh.length) { S.msgs = S.msgs.concat(fresh); S.lastAt = S.msgs[S.msgs.length - 1].at; renderMsgs(false); if (fresh.some(function (m) { return m.kind === "customer"; })) ping(); }
      if (statusChanged) renderHead();
    }).catch(function () {});
  }

  // ---------------------------------------------------------------- composer
  function send(body) {
    if (S.sending || !S.active) return Promise.resolve();
    S.sending = true; $("[data-send]").disabled = true;
    return post(url("send", S.active), body).then(function (d) {
      var known = {}; S.msgs.forEach(function (m) { known[m.id] = 1; });
      d.messages.forEach(function (m) { if (!known[m.id]) S.msgs.push(m); });
      S.lastAt = S.msgs.length ? S.msgs[S.msgs.length - 1].at : S.lastAt;
      S.conv = d.conversation; renderHead(); renderMsgs(true); loadQueue();
    }).catch(function (e) { toast(e.message, true); throw e; }).finally(function () { S.sending = false; $("[data-send]").disabled = false; });
  }
  function grow(t) { t.style.height = "auto"; t.style.height = Math.min(t.scrollHeight, 160) + "px"; }
  function popup(kind) {
    var pop = $("[data-pop]");
    if (!pop.hidden && pop.getAttribute("data-kind") === kind) { pop.hidden = true; return; }
    pop.setAttribute("data-kind", kind);
    if (kind === "sticker") pop.innerHTML = '<div class="nzc-stickers">' + cfg.stickers.map(function (s) { return '<button type="button" data-sticker="' + s.code + '" title="' + esc(s.label) + '"><span>' + s.emoji + "</span><small>" + esc(s.label) + "</small></button>"; }).join("") + "</div>";
    else if (kind === "quick") pop.innerHTML = (cfg.quick.length ? '<ul class="nzc-quick">' + cfg.quick.map(function (q, i) { return '<li><button type="button" data-quick="' + i + '"><b>' + esc(q.title) + "</b><span>" + preview(q.text) + "</span></button></li>"; }).join("") + "</ul>" : '<p class="nzc-muted">Tayyor javob yo\'q.</p>') +
      '<div class="nzc-vars">O\'zgaruvchilar: ' + Object.keys(cfg.variables || {}).map(function (k) { return '<button type="button" data-var="' + k + '" title="' + esc(cfg.variables[k]) + (S.vars[k] ? " — " + esc(S.vars[k]) : " — ma\'lumot yo\'q") + '"><mark>{' + k + "}</mark></button>"; }).join(" ") + "</div>" +
      '<a class="nzc-pop-link" href="' + esc(cfg.quick_admin) + '"><i class="fas fa-pen" aria-hidden="true"></i> Tayyor javoblarni tahrirlash</a>';
    else {
      var orders = (S.profile && S.profile.orders) || [];
      pop.innerHTML = '<label class="nzc-search in-pop"><i class="fas fa-magnifying-glass" aria-hidden="true"></i><input type="search" placeholder="Mahsulot nomi yoki SKU…" data-card-q aria-label="Mahsulot qidirish"></label>' +
        '<div class="nzc-card-results" data-card-results><div class="nzc-empty small"><i class="fas fa-circle-notch fa-spin" aria-hidden="true"></i></div></div>' +
        (orders.length ? '<h5>Mijoz buyurtmalari</h5><div class="nzc-card-results">' + orders.map(function (o) { return '<button type="button" class="nzc-pick" data-card="order:' + o.id + '"><i class="fas fa-receipt" aria-hidden="true"></i><span><b>' + esc(o.number) + "</b><small>" + esc(o.status) + " · " + money(o.total) + " so'm</small></span></button>"; }).join("") + "</div>" : "");
      searchCards("");
      setTimeout(function () { var i = $("[data-card-q]"); if (i) i.focus(); }, 30);
    }
    pop.hidden = false;
  }

  var VAR_RE = /\{([a-z_]+)\}/g;
  function known(k) { return cfg.variables && Object.prototype.hasOwnProperty.call(cfg.variables, k); }
  // a quick reply as the customer will get it: filled values highlighted, the ones without data in red
  function preview(text) {
    return esc(text).replace(VAR_RE, function (all, k) {
      if (!known(k)) return all;
      return S.vars[k] ? '<mark title="{' + k + '}">' + esc(S.vars[k]) + "</mark>" : '<mark class="miss" title="Ma\'lumot yo\'q">{' + k + "}</mark>";
    });
  }
  function fill(text) {
    var missing = [];
    var out = text.replace(VAR_RE, function (all, k) { if (!known(k)) return all; if (S.vars[k]) return S.vars[k]; missing.push("{" + k + "}"); return all; });
    return { text: out, missing: missing };
  }
  function insertAtCursor(input, text) {
    var a = input.selectionStart || input.value.length, b = input.selectionEnd || a;
    input.value = input.value.slice(0, a) + text + input.value.slice(b); input.selectionStart = input.selectionEnd = a + text.length; grow(input); input.focus();
  }

  var cardTimer;
  function searchCards(q) {
    api(cfg.cards + "?q=" + encodeURIComponent(q)).then(function (rows) {
      var box = $("[data-card-results]"); if (!box) return;
      box.innerHTML = rows.length ? rows.map(function (c) {
        return '<button type="button" class="nzc-pick" data-card="product:' + c.id + '">' + (c.image ? '<img src="' + esc(c.image) + '" alt="">' : '<i class="fas fa-box" aria-hidden="true"></i>') +
          "<span><b>" + esc(c.title) + "</b><small>" + (c.price ? money(c.price) + " so'm" : "narx yo'q") + " · " + (c.in_stock ? "mavjud" : "tugagan") + "</small></span></button>";
      }).join("") : '<p class="nzc-muted">Topilmadi.</p>';
    }).catch(function () {});
  }

  // ---------------------------------------------------------------- sounds
  var audio;
  function ping() {
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      var o = audio.createOscillator(), g = audio.createGain();
      o.frequency.value = 880; g.gain.value = 0.04; o.connect(g); g.connect(audio.destination); o.start(); o.stop(audio.currentTime + 0.12);
    } catch (e) { /* no audio */ }
  }

  // ---------------------------------------------------------------- events
  root.addEventListener("click", function (e) {
    var tab = e.target.closest(".nzc-tabs button");
    if (tab) { S.filter = tab.getAttribute("data-f"); renderTabs(); $("[data-list]").innerHTML = '<div class="nzc-empty"><i class="fas fa-circle-notch fa-spin" aria-hidden="true"></i></div>'; loadQueue(); return; }
    var item = e.target.closest(".nzc-item");
    if (item) { openConv(item.getAttribute("data-id")); return; }
    if (e.target.closest("[data-back]")) { root.classList.remove("has-thread"); return; }
    var act = e.target.closest("[data-act]");
    if (act) {
      var name = act.getAttribute("data-act");
      if ((name === "close" || name === "archive") && !window.confirm(name === "close" ? "Suhbat yopilsinmi? Mijoz yangi xabar yozsa, uni qayta ochish mumkin." : "Suhbat arxivga o'tkazilsinmi?")) return;
      act.disabled = true;
      post(url("action", S.active, name)).then(function (d) { S.conv = d.conversation; renderHead(); loadQueue(); toast({ take: "Suhbat sizga biriktirildi", close: "Suhbat yopildi", reopen: "Suhbat qayta ochildi", archive: "Arxivlandi" }[name]); })
        .catch(function (err) { toast(err.message, true); act.disabled = false; });
      return;
    }
    var tool = e.target.closest("[data-tool]");
    if (tool) { popup(tool.getAttribute("data-tool")); return; }
    var st = e.target.closest("[data-sticker]");
    if (st) { $("[data-pop]").hidden = true; send({ kind: "sticker", content: st.getAttribute("data-sticker") }).catch(function () {}); return; }
    var qr = e.target.closest("[data-quick]");
    if (qr) {
      var q = cfg.quick[+qr.getAttribute("data-quick")], input = $("[data-input]"), f = fill(q.text);
      input.value = f.text; S.quickId = q.id; grow(input); input.focus(); $("[data-pop]").hidden = true;
      if (f.missing.length) { toast(f.missing.join(", ") + " uchun ma'lumot yo'q — yuborishdan oldin o'zingiz yozing", true); var at = input.value.indexOf(f.missing[0]); if (at >= 0) input.setSelectionRange(at, at + f.missing[0].length); }
      return;
    }
    var v = e.target.closest("[data-var]");
    if (v) { var k = v.getAttribute("data-var"); insertAtCursor($("[data-input]"), S.vars[k] || "{" + k + "}"); $("[data-pop]").hidden = true; return; }
    var pick = e.target.closest("[data-card]");
    if (pick) { $("[data-pop]").hidden = true; send({ kind: "card", content: pick.getAttribute("data-card") }).catch(function () {}); return; }
    if (!e.target.closest("[data-pop]")) $("[data-pop]").hidden = true;
  });
  $("[data-review]").addEventListener("submit", function (e) {
    e.preventDefault();
    var btn = e.target.querySelector("button"); btn.disabled = true;
    post(url("action", S.active, "resolve"), { note: e.target.querySelector("[data-note]").value }).then(function (d) { S.conv = d.conversation; renderHead(); loadQueue(); toast("Nazorat yopildi — rahmat!"); })
      .catch(function (err) { toast(err.message, true); btn.disabled = false; });
  });
  $("[data-composer]").addEventListener("submit", function (e) {
    e.preventDefault();
    var input = $("[data-input]"), text = input.value.trim();
    if (!text) return;
    send({ kind: "text", content: text, quick_id: S.quickId }).then(function () { input.value = ""; S.quickId = null; grow(input); }).catch(function () {});
  });
  $("[data-input]").addEventListener("keydown", function (e) { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("[data-composer]").requestSubmit(); } });
  $("[data-input]").addEventListener("input", function (e) { grow(e.target); });
  $("[data-file]").addEventListener("change", function (e) {
    var f = e.target.files[0]; e.target.value = "";
    if (!f || !S.active) return;
    var fd = new FormData(); fd.append("file", f);
    toast("Yuklanmoqda…");
    api(url("upload", S.active), { method: "POST", headers: { "X-CSRFToken": csrf() }, body: fd })
      .then(function (a) { return send({ kind: "attachment", attachment: a, content: $("[data-input]").value.trim() }); })
      .then(function () { $("[data-input]").value = ""; })
      .catch(function (err) { toast(err.message, true); });
  });
  root.addEventListener("input", function (e) { if (e.target.hasAttribute("data-card-q")) { clearTimeout(cardTimer); var v = e.target.value; cardTimer = setTimeout(function () { searchCards(v); }, 250); } });
  var qTimer;
  $("[data-q]").addEventListener("input", function (e) { clearTimeout(qTimer); qTimer = setTimeout(function () { S.q = e.target.value; loadQueue(); }, 280); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") $("[data-pop]").hidden = true; });
  document.addEventListener("visibilitychange", function () { if (!document.hidden) { loadQueue(); pollThread(); } });

  // ---------------------------------------------------------------- start
  renderTabs(); renderList();
  if (cfg.open) openConv(cfg.open, true);
  else if (window.innerWidth > 900 && S.rows.length) openConv(S.rows[0].id, true);
  setInterval(function () { if (!document.hidden) loadQueue(); }, 6000);
  setInterval(pollThread, 3000);
})();
