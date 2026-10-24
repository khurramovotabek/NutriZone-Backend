/* Delivery desk (Yetkazib berish markazi): courier saves, one-step status moves and the map. */
(function () {
  "use strict";

  var root = document.querySelector("[data-nzdl]");
  if (!root) return;
  var csrf = (root.querySelector("input[name=csrfmiddlewaretoken]") || {}).value || "";
  var ZERO = "00000000-0000-0000-0000-000000000000";
  var toastBox = root.querySelector("[data-nzdl-toast]");
  var toastTimer = null;

  function toast(text, isErr) {
    toastBox.textContent = text;
    toastBox.classList.toggle("is-err", !!isErr);
    toastBox.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastBox.hidden = true; }, 3500);
  }

  function post(url, body) {
    return fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify(body),
    }).then(function (r) {
      return r.json().catch(function () { return { ok: false, error: r.status + "" }; });
    });
  }

  // Courier picker: "+ New courier…" reveals name/phone inputs.
  root.querySelectorAll("[data-assign]").forEach(function (form) {
    var select = form.querySelector("select[name=courier_id]");
    var extra = form.querySelector(".nzdl-new");
    select.addEventListener("change", function () {
      extra.hidden = select.value !== "__new";
      if (!extra.hidden) extra.querySelector("input").focus();
    });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var card = form.closest("[data-order]");
      var data = {};
      new FormData(form).forEach(function (v, k) { data[k] = v; });
      if (data.courier_id === "__new") {
        data.courier_id = "";
        if (!String(data.new_courier || "").trim()) { toast(form.dataset.needName || "Kuryer ismini kiriting", true); return; }
      } else {
        data.new_courier = ""; data.new_phone = "";
      }
      var btn = form.querySelector("button");
      if (btn) btn.disabled = true;
      post(root.dataset.urlAssign.replace(ZERO, card.dataset.order), data).then(function (res) {
        if (btn) btn.disabled = false;
        if (!res.ok) { toast(res.error || "Error", true); return; }
        toast(res.message);
        form.classList.add("is-saved");
        if (data.new_courier) location.reload();
      }).catch(function () { if (btn) btn.disabled = false; toast("Network error", true); });
    });
  });

  // One step forward (same rules as the order board).
  root.querySelectorAll("[data-move]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var card = btn.closest("[data-order]");
      btn.disabled = true;
      post(root.dataset.urlMove.replace(ZERO, card.dataset.order), { action: btn.dataset.move }).then(function (res) {
        if (!res.ok) { btn.disabled = false; toast(res.error || "Error", true); return; }
        toast(res.message);
        card.style.transition = "opacity .3s";
        card.style.opacity = ".35";
        setTimeout(function () { location.reload(); }, 700);
      }).catch(function () { btn.disabled = false; toast("Network error", true); });
    });
  });

  // Map of this tab's orders.
  var mapBox = root.querySelector("[data-nzdl-map]");
  var pinsEl = document.getElementById("nzdl-pins");
  var pins = pinsEl ? JSON.parse(pinsEl.textContent) : [];
  if (mapBox && window.L) {
    var L = window.L;
    var map = L.map(mapBox, { scrollWheelZoom: false, attributionControl: true }).setView([41.3111, 69.2797], 11);
    L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}", { maxZoom: 19, attribution: "Tiles &copy; Esri" }).addTo(map);
    var bounds = [];
    pins.forEach(function (p) {
      var color = p.late ? "#dc2626" : "#0ea5e9";
      var m = L.circleMarker([p.lat, p.lng], { radius: 9, color: "#fff", weight: 2, fillColor: color, fillOpacity: 1 }).addTo(map);
      var esc = function (s) { var d = document.createElement("div"); d.textContent = s || ""; return d.innerHTML; };
      m.bindPopup("<b>" + esc(p.n) + "</b><br>" + esc(p.who) + "<br><small>" + esc(p.addr) + "</small>");
      bounds.push([p.lat, p.lng]);
    });
    if (bounds.length > 1) map.fitBounds(bounds, { padding: [24, 24], maxZoom: 15 });
    else if (bounds.length === 1) map.setView(bounds[0], 15);
    map.on("click", function () { map.scrollWheelZoom.enable(); });
    setTimeout(function () { map.invalidateSize(); }, 200);
  }
})();
