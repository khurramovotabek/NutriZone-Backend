/* Do'kon formasi: xarita (koordinata tanlash), shahar → xarita, haftalik ish vaqti (presetlar, nusxalash, bugungi kun). */
(function () {
  "use strict";
  function ready(fn) { if (document.readyState !== "loading") fn(); else document.addEventListener("DOMContentLoaded", fn); }

  ready(function () {
    // ---------- weekly hours
    var rows = Array.prototype.slice.call(document.querySelectorAll(".nzf-hour-row"));
    function parts(row) {
      return { closed: row.querySelector('[data-part="closed"]'), open: row.querySelector('[data-part="open"]'), close: row.querySelector('[data-part="close"]') };
    }
    function paint(row) {
      var p = parts(row);
      row.classList.toggle("is-off", p.closed.checked);
      var dur = row.querySelector(".nzf-dur");
      if (p.closed.checked || !p.open.value || !p.close.value) { dur.textContent = p.closed.checked ? "dam olish kuni" : ""; return; }
      var a = p.open.value.split(":"), b = p.close.value.split(":");
      var m = (+b[0] * 60 + +b[1]) - (+a[0] * 60 + +a[1]);
      dur.textContent = m > 0 ? Math.floor(m / 60) + " soat" + (m % 60 ? " " + (m % 60) + " daq" : "") : "⚠ vaqt noto'g'ri";
      dur.style.color = m > 0 ? "" : "#e11d48";
    }
    if (rows.length) {
      var today = (new Date().getDay() + 6) % 7; // Mon = 0
      if (rows[today]) rows[today].classList.add("is-today");
      rows.forEach(function (row) {
        paint(row);
        row.addEventListener("input", function () { paint(row); });
        row.addEventListener("change", function () { paint(row); });
      });
      document.addEventListener("click", function (e) {
        var preset = e.target.closest("[data-hours-preset]"), copy = e.target.closest("[data-hours-copy]");
        if (!preset && !copy) return;
        var src = parts(rows[0]);
        rows.forEach(function (row, i) {
          var p = parts(row);
          if (copy) { p.closed.checked = src.closed.checked; p.open.value = src.open.value; p.close.value = src.close.value; }
          else {
            var v = preset.getAttribute("data-hours-preset").split("-");
            p.closed.checked = v[2] === "sun" && i === 6;
            p.open.value = p.closed.checked ? "" : v[0]; p.close.value = p.closed.checked ? "" : v[1];
          }
          paint(row);
        });
      });
    }

    // ---------- map picker
    var el = document.getElementById("nzf-map");
    var lat = document.getElementById("id_latitude"), lng = document.getElementById("id_longitude");
    if (!el || !window.L || !lat || !lng) return;
    var has = lat.value && lng.value;
    var center = has ? [+lat.value, +lng.value] : [41.2995, 69.2401]; // Toshkent
    var map = L.map(el, { scrollWheelZoom: false }).setView(center, has ? 16 : 11);
    L.tileLayer((window.NZ_MAP_TILE_URL || "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}"), { maxZoom: 19, attribution: "© Esri" }).addTo(map);
    var marker = L.marker(center, { draggable: true, opacity: has ? 1 : 0.55 }).addTo(map);
    function put(ll, zoom) {
      marker.setLatLng(ll).setOpacity(1);
      lat.value = ll.lat.toFixed(6); lng.value = ll.lng.toFixed(6);
      if (zoom) map.setView(ll, zoom);
    }
    map.on("click", function (e) { put(e.latlng); });
    marker.on("dragend", function () { put(marker.getLatLng()); });
    [lat, lng].forEach(function (inp) { inp.addEventListener("change", function () { if (lat.value && lng.value) put(L.latLng(+lat.value, +lng.value), 16); }); });
    document.addEventListener("nz:city", function (e) {
      var o = e.detail;
      if (o && o.dataset && o.dataset.lat && !(lat.value && lng.value)) map.setView([+o.dataset.lat, +o.dataset.lng], 13);
      else if (o && o.dataset && o.dataset.lat) map.flyTo([+o.dataset.lat, +o.dataset.lng], 13);
    });
    var locate = document.getElementById("nzf-locate");
    if (locate && navigator.geolocation) locate.onclick = function () {
      navigator.geolocation.getCurrentPosition(function (p) { put(L.latLng(p.coords.latitude, p.coords.longitude), 17); });
    };
    // the map may be inside a hidden tab / collapsed card: fix its size once visible
    setTimeout(function () { map.invalidateSize(); }, 300);
    document.addEventListener("click", function () { setTimeout(function () { map.invalidateSize(); }, 200); });
  });
})();
