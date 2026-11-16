/* Orders list: the "next step" button under each status (Tasdiqlash -> Yig'ishni boshlash -> Kuryerga berish -> Yetkazildi).
 * Posts to the Order board's move endpoint (same service path, same rules). "Kuryerga berish" uses the location where the
 * stock was reserved (or the first one holding every item); when no location has everything, the board opens instead. */
(function () {
  "use strict";
  function csrf() {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    var input = document.querySelector("input[name=csrfmiddlewaretoken]");
    return m ? decodeURIComponent(m[1]) : input ? input.value : "";
  }
  function fail(btn, text) {
    btn.disabled = false;
    btn.classList.add("is-err");
    var msg = btn.parentNode.querySelector(".nzo-next-msg") || document.createElement("span");
    msg.className = "nzo-next-msg";
    msg.textContent = text || "Xatolik";
    btn.parentNode.appendChild(msg);
  }
  function move(btn, body) {
    return fetch(btn.getAttribute("data-nzo-move"), {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf(), "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify(body),
    }).then(function (r) { return r.json().catch(function () { return { ok: false }; }); }).then(function (res) {
      if (!res.ok) return fail(btn, res.error);
      btn.classList.add("is-done");
      btn.innerHTML = '<i class="fas fa-circle-check"></i> ' + (res.message || "OK");
      setTimeout(function () { window.location.reload(); }, 700);
    }).catch(function () { fail(btn); });
  }
  document.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest("button.nzo-next");
    if (!btn || btn.disabled) return;
    e.preventDefault();
    e.stopPropagation();
    btn.disabled = true;
    btn.classList.remove("is-err");
    var old = btn.parentNode.querySelector(".nzo-next-msg");
    if (old) old.remove();
    var action = btn.getAttribute("data-action");
    if (action !== "ship") return move(btn, { action: action });
    fetch(btn.getAttribute("data-nzo-ship"), { credentials: "same-origin" }).then(function (r) { return r.json(); }).then(function (res) {
      var locs = (res && res.locations) || [];
      var pick = locs.filter(function (l) { return l.default && l.ok; })[0] || locs.filter(function (l) { return l.ok; })[0];
      if (!pick) { window.location.href = btn.getAttribute("data-nzo-move").replace(/[0-9a-f-]{36}\/move\/$/, ""); return; }
      move(btn, { action: "ship", store_id: pick.id });
    }).catch(function () { fail(btn); });
  }, true);
})();
