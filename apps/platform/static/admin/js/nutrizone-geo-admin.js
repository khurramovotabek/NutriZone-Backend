/*
 * Dashboard → Geo & Location maps (apps/geo/infrastructure/admin.py, Leaflet self-hosted in admin/vendor/leaflet).
 *
 *   [data-nzgeo-picker]   a point editor bound to two inputs (data-lat / data-lng = input ids): click or drag the pin,
 *                         search a place, paste a Yandex / Google / Apple / 2GIS link or "lat, lng", or "my location".
 *   [data-nzgeo-view]     a read-only point (data-lat, data-lng, data-label).
 *   [data-nzgeo-overview] many points (JSON in a <script type="application/json" data-points>) with popups.
 *
 * Every map has the same layer switcher: Xarita · Sputnik · Gibrid · Relyef (Esri tiles -- no key, not blocked;
 * see nutrizone-geo-maps.js for why OSM / CARTO tiles are not used).
 */
(function () {
  "use strict";
  if (!window.L) return;
  var L = window.L;
  var ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/";
  var ATTR = "Tiles &copy; Esri";
  var API = "/api/v1/geo/locations/";
  var LAYERS = {
    street: { label: "Xarita", url: ESRI + "World_Street_Map/MapServer/tile/{z}/{y}/{x}" },
    satellite: { label: "Sputnik", url: ESRI + "World_Imagery/MapServer/tile/{z}/{y}/{x}" },
    hybrid: { label: "Gibrid", url: ESRI + "World_Imagery/MapServer/tile/{z}/{y}/{x}", labels: ESRI + "Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}" },
    topo: { label: "Relyef", url: ESRI + "World_Topo_Map/MapServer/tile/{z}/{y}/{x}" },
  };
  var TASHKENT = [41.2995, 69.2401];

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function fx(n) { return Number(n).toFixed(6); }
  function pinIcon(color) {
    return L.divIcon({ className: "nzgeo-pin", iconSize: [34, 34], iconAnchor: [17, 32], popupAnchor: [0, -28],
      html: '<svg width="34" height="34" viewBox="0 0 24 24" style="color:' + (color || "#4f46e5") + '"><path fill="currentColor" d="M12 2C7.86 2 4.5 5.36 4.5 9.5c0 5.5 6.5 12 7 12.5.2.2.4.2.6 0 .5-.5 7-7 7-12.5C19.5 5.36 16.14 2 12 2Z"/><circle cx="12" cy="9.4" r="3.1" fill="#fff"/></svg>' });
  }
  // the same "open in" links the storefront and the order desk use
  function links(lat, lng, label) {
    var q = encodeURIComponent(label || "");
    return [
      ["Yandex", "https://yandex.uz/maps/?pt=" + fx(lng) + "," + fx(lat) + "&z=17&l=map", "#FC3F1D"],
      ["Yo'nalish", "https://yandex.uz/maps/?rtext=~" + fx(lat) + "," + fx(lng) + "&rtt=auto", "#FC3F1D"],
      ["Google", "https://www.google.com/maps/search/?api=1&query=" + fx(lat) + "," + fx(lng), "#1a73e8"],
      ["Apple", "https://maps.apple.com/?ll=" + fx(lat) + "," + fx(lng) + "&q=" + (q || "Manzil"), "#8b5cf6"],
      ["2GIS", "https://2gis.uz/geo/" + fx(lng) + "," + fx(lat), "#19aa1e"],
    ];
  }
  function linksHtml(lat, lng, label) {
    return '<span class="nzgeo-links">' + links(lat, lng, label).map(function (l) { return '<a href="' + esc(l[1]) + '" target="_blank" rel="noopener" style="--t:' + l[2] + '">' + l[0] + "</a>"; }).join("") + "</span>";
  }

  function baseMap(el, center, zoom) {
    var map = L.map(el, { scrollWheelZoom: false, zoomControl: true }).setView(center, zoom);
    var current = null, labels = null;
    function use(key) {
      var def = LAYERS[key] || LAYERS.street;
      if (current) map.removeLayer(current);
      if (labels) { map.removeLayer(labels); labels = null; }
      current = L.tileLayer(def.url, { maxZoom: 19, attribution: ATTR }).addTo(map);
      if (def.labels) labels = L.tileLayer(def.labels, { maxZoom: 19 }).addTo(map);
      try { localStorage.setItem("nzgeo-layer", key); } catch (e) { /* private mode */ }
      Array.prototype.forEach.call(bar.querySelectorAll("button"), function (b) { b.classList.toggle("on", b.getAttribute("data-layer") === key); });
    }
    var bar = L.DomUtil.create("div", "nzgeo-layers");
    bar.innerHTML = Object.keys(LAYERS).map(function (k) { return '<button type="button" data-layer="' + k + '">' + LAYERS[k].label + "</button>"; }).join("");
    L.DomEvent.disableClickPropagation(bar);
    bar.addEventListener("click", function (e) { var b = e.target.closest("button"); if (b) use(b.getAttribute("data-layer")); });
    var ctl = L.control({ position: "topright" });
    ctl.onAdd = function () { return bar; };
    ctl.addTo(map);
    var saved = "street";
    try { saved = localStorage.getItem("nzgeo-layer") || "street"; } catch (e) { /* ignore */ }
    use(saved);
    map.on("focus click", function () { map.scrollWheelZoom.enable(); });
    setTimeout(function () { map.invalidateSize(); }, 200);
    return map;
  }

  // admin Media scripts load in <head>: build the maps once the page is parsed
  function init() {
  // ---------------------------------------------------------------- read-only point
  Array.prototype.forEach.call(document.querySelectorAll("[data-nzgeo-view]"), function (el) {
    var lat = parseFloat(el.getAttribute("data-lat")), lng = parseFloat(el.getAttribute("data-lng"));
    if (isNaN(lat) || isNaN(lng)) return;
    var map = baseMap(el, [lat, lng], 16);
    var label = el.getAttribute("data-label") || "";
    L.marker([lat, lng], { icon: pinIcon() }).addTo(map).bindPopup("<b>" + esc(label || "Manzil") + "</b><br>" + fx(lat) + ", " + fx(lng) + "<br>" + linksHtml(lat, lng, label));
    var acc = parseFloat(el.getAttribute("data-accuracy"));
    if (!isNaN(acc) && acc > 0) L.circle([lat, lng], { radius: acc, color: "#4f46e5", weight: 1, fillOpacity: 0.12 }).addTo(map);
  });

  // ---------------------------------------------------------------- many points
  Array.prototype.forEach.call(document.querySelectorAll("[data-nzgeo-overview]"), function (el) {
    var data = [];
    try { data = JSON.parse(el.querySelector('script[type="application/json"]').textContent); } catch (e) { data = []; }
    var holder = el.querySelector("[data-map]");
    var map = baseMap(holder, TASHKENT, 11);
    var groups = {}, byId = {};
    data.forEach(function (p) {
      var m = L.marker([p.lat, p.lng], { icon: pinIcon(p.color) }).bindPopup(
        '<div class="nzgeo-pop"><small>' + esc(p.kind_label) + "</small><b>" + esc(p.title) + "</b><span>" + esc(p.subtitle || "") + "</span>" +
        (p.url ? '<a class="nzgeo-open" href="' + esc(p.url) + '">Ochish →</a>' : "") + linksHtml(p.lat, p.lng, p.title) + "</div>");
      (groups[p.kind] = groups[p.kind] || L.layerGroup().addTo(map)).addLayer(m);
      byId[p.id] = m;
    });
    var toggles = Array.prototype.slice.call(el.querySelectorAll("[data-kind-toggle]"));
    function shown() { var on = {}; toggles.forEach(function (cb) { on[cb.getAttribute("data-kind-toggle")] = cb.checked; }); return on; }
    toggles.forEach(function (cb) {
      var g = groups[cb.getAttribute("data-kind-toggle")];
      if (g && !cb.checked) map.removeLayer(g);  // e.g. city centres start hidden
      cb.addEventListener("change", function () { var grp = groups[cb.getAttribute("data-kind-toggle")]; if (!grp) return; if (cb.checked) grp.addTo(map); else map.removeLayer(grp); });
    });
    var on = shown();
    var pts = data.filter(function (p) { return on[p.kind] !== false; }).map(function (p) { return [p.lat, p.lng]; });
    var focus = byId[el.getAttribute("data-focus") || ""];
    if (focus) { map.setView(focus.getLatLng(), 17); focus.openPopup(); }
    else if (pts.length) map.fitBounds(pts, { padding: [40, 40], maxZoom: 15 });
  });

  // ---------------------------------------------------------------- point editor
  Array.prototype.forEach.call(document.querySelectorAll("[data-nzgeo-picker]"), function (el) {
    var latIn = document.getElementById(el.getAttribute("data-lat")), lngIn = document.getElementById(el.getAttribute("data-lng"));
    if (!latIn || !lngIn) return;
    var holder = el.querySelector("[data-map]"), status = el.querySelector("[data-status]"), linkBox = el.querySelector("[data-links]");
    var srcIn = document.getElementById(el.getAttribute("data-source") || ""), accIn = document.getElementById(el.getAttribute("data-accuracy") || "");
    function value() { var a = parseFloat(latIn.value), b = parseFloat(lngIn.value); return isNaN(a) || isNaN(b) ? null : [a, b]; }
    var start = value();
    var map = baseMap(holder, start || TASHKENT, start ? 15 : 11);
    var marker = null, circle = null;
    function say(text, bad) { if (status) { status.textContent = text || ""; status.classList.toggle("bad", !!bad); } }
    function place(lat, lng, opts) {
      opts = opts || {};
      latIn.value = fx(lat); lngIn.value = fx(lng);
      if (!opts.initial) latIn.dispatchEvent(new Event("change", { bubbles: true }));  // the form's "unsaved changes" only on a real edit
      if (!marker) {
        marker = L.marker([lat, lng], { icon: pinIcon(), draggable: true }).addTo(map);
        marker.on("dragend", function () { var p = marker.getLatLng(); place(p.lat, p.lng, { keepCircle: false }); });
      } else marker.setLatLng([lat, lng]);
      if (circle && !opts.keepCircle) { map.removeLayer(circle); circle = null; }
      if (opts.accuracy) circle = L.circle([lat, lng], { radius: opts.accuracy, color: "#4f46e5", weight: 1, fillOpacity: 0.12 }).addTo(map);
      if (!opts.initial && srcIn) { srcIn.value = opts.source || "map_pin"; srcIn.dispatchEvent(new Event("change", { bubbles: true })); }
      if (!opts.initial && accIn) accIn.value = opts.accuracy ? Math.round(opts.accuracy) : "";  // a hand-placed pin has no measured accuracy
      if (opts.fly) map.flyTo([lat, lng], Math.max(map.getZoom(), 16), { duration: 0.6 });
      if (linkBox) linkBox.innerHTML = linksHtml(lat, lng, "");
      say(opts.note || (fx(lat) + ", " + fx(lng)));
    }
    if (start) place(start[0], start[1], { initial: true });
    map.on("click", function (e) { place(e.latlng.lat, e.latlng.lng); });
    function fromInputs() { var v = value(); if (v) place(v[0], v[1], { fly: true, source: "manual" }); }
    latIn.addEventListener("input", fromInputs); lngIn.addEventListener("input", fromInputs);

    var tools = el.querySelector("[data-tools]");
    if (!tools) return;
    var results = el.querySelector("[data-results]"), q = el.querySelector("[data-q]");
    var timer;
    q && q.addEventListener("input", function () {
      clearTimeout(timer);
      var text = q.value.trim();
      if (text.length < 3) { results.hidden = true; return; }
      timer = setTimeout(function () {
        var c = map.getCenter();
        fetch(API + "geocode?q=" + encodeURIComponent(text) + "&lang=uz&lat=" + c.lat + "&lng=" + c.lng).then(function (r) { return r.json(); }).then(function (j) {
          var rows = (j && j.data) || [];
          results.innerHTML = rows.length ? rows.map(function (r, i) { return '<button type="button" data-i="' + i + '"><b>' + esc(r.title) + "</b><small>" + esc(r.subtitle) + "</small></button>"; }).join("") : '<p>Topilmadi — boshqacha yozib ko\'ring yoki xaritada bosing.</p>';
          results.hidden = false; results._rows = rows;
        }).catch(function () { say("Qidiruv ishlamadi — internetni tekshiring", true); });
      }, 350);
    });
    results && results.addEventListener("click", function (e) {
      var b = e.target.closest("button[data-i]"); if (!b) return;
      var r = results._rows[+b.getAttribute("data-i")];
      place(r.lat, r.lng, { fly: true, source: "search", note: r.title + " — " + fx(r.lat) + ", " + fx(r.lng) });
      results.hidden = true; q.value = r.title;
    });
    var paste = el.querySelector("[data-paste]");
    paste && paste.addEventListener("click", function () {
      var input = el.querySelector("[data-link]"), text = (input.value || "").trim();
      if (!text) { input.focus(); return; }
      paste.disabled = true;
      fetch(API + "parse-link", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: text }) })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
        .then(function (res) {
          if (!res.ok) { say("Havoladan joylashuv topilmadi. Yandex / Google / Apple / 2GIS havolasi yoki \"41.31, 69.27\" yozing.", true); return; }
          place(res.j.data.latitude, res.j.data.longitude, { fly: true, source: "link", note: "Havoladan olindi" }); input.value = "";
        }).catch(function () { say("Tarmoq xatosi", true); }).finally(function () { paste.disabled = false; });
    });
    var me = el.querySelector("[data-me]");
    me && me.addEventListener("click", function () {
      if (!navigator.geolocation) { say("Brauzer joylashuvni aniqlay olmaydi", true); return; }
      me.disabled = true; say("Aniqlanmoqda…");
      navigator.geolocation.getCurrentPosition(function (p) {
        me.disabled = false;
        place(p.coords.latitude, p.coords.longitude, { fly: true, source: "gps", accuracy: p.coords.accuracy, keepCircle: true, note: "Aniqlik ±" + Math.round(p.coords.accuracy) + " m" });
      }, function (err) {
        me.disabled = false;
        say(err.code === 1 ? "Joylashuvga ruxsat berilmagan — brauzer manzil satridagi 🔒 belgisidan ruxsat bering" : "Joylashuv aniqlanmadi, xaritada bosing", true);
      }, { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 });
    });
    var clear = el.querySelector("[data-clear]");
    clear && clear.addEventListener("click", function () {
      latIn.value = ""; lngIn.value = ""; if (marker) { map.removeLayer(marker); marker = null; } if (circle) { map.removeLayer(circle); circle = null; }
      if (linkBox) linkBox.innerHTML = ""; say("Koordinata o'chirildi");
    });
  });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
