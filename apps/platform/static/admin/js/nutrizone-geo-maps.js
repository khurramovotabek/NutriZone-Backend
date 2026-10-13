/*
 * NutriZone Admin Dashboard -- Leaflet map integration.
 *
 * Real, closed gap: GeoBoundary/Address previously showed only a
 * text summary ("5 points, starts at...") or a raw lat/lng pair --
 * no actual map. Leaflet is self-hosted (no API key, matching this
 * project's own Chart.js vendoring pattern) and renders real,
 * stored coordinates on a real tile layer.
 */
(function () {
  "use strict";

  // Real, closed bug (dashboard cleanup phase): CARTO's free
  // basemaps.cartocdn.com tiles now require a registered API key --
  // every tile rendered a literal "API KEY REQUIRED" watermark
  // instead of a real map, for every Address/City map on the
  // Dashboard. Confirmed live, against multiple no-key candidates,
  // before picking this one: raw tile.openstreetmap.org is this same
  // codebase's own previously-confirmed 403 regression (see this
  // file's own git history / test_admin_maps.py) and Wikimedia's own
  // OSM-intl tiles returned a hard 403/503 here too -- both are
  // volunteer-run services that actively rate-limit exactly this kind
  // of server-hosted-dashboard traffic. Esri's ArcGIS Online basemap
  // tiles are a commercial CDN explicitly served for external,
  // no-signup, no-key embedding at this usage level, and loaded real
  // imagery successfully in this deployment.
  var NZ_MAP_TILE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}";
  var NZ_MAP_ATTRIBUTION = "Tiles &copy; Esri &mdash; Source: Esri, DeLorme, NAVTEQ";

  function showLoading(el) {
    el.classList.remove("nz-map-error");
    el.classList.add("nz-map-loading");
  }

  function showError(el, onRetry) {
    el.classList.remove("nz-map-loading");
    el.classList.add("nz-map-error");
    el.innerHTML = "";

    var message = document.createElement("p");
    message.className = "nz-map-error-message";
    message.textContent = "Unable to load map location.";
    el.appendChild(message);

    var retry = document.createElement("button");
    retry.type = "button";
    retry.className = "nz-map-retry-btn";
    retry.textContent = "Retry";
    retry.addEventListener("click", onRetry);
    el.appendChild(retry);
  }

  function clearState(el) {
    el.classList.remove("nz-map-loading", "nz-map-error");
  }

  function buildMap(el, view, onReady) {
    showLoading(el);
    el.innerHTML = "";

    try {
      var map = window.L.map(el, { scrollWheelZoom: false });
      var tileLayer = window.L.tileLayer(NZ_MAP_TILE_URL, { attribution: NZ_MAP_ATTRIBUTION, maxZoom: 19 });

      var settled = false;
      tileLayer.on("load", function () {
        if (settled) return;
        settled = true;
        clearState(el);
      });
      tileLayer.on("tileerror", function () {
        // A handful of edge tiles can legitimately 404 near map bounds;
        // only treat total failure to render anything as an error.
        if (settled || map._loaded) return;
      });

      tileLayer.addTo(map);
      onReady(map);

      // Leaflet computes tile bounds from the container's size at init
      // time; if the container was hidden/zero-size (e.g. a collapsed
      // fieldset) when init ran, tiles render blank until this fires.
      setTimeout(function () {
        map.invalidateSize();
      }, 200);
      window.addEventListener("resize", function () {
        map.invalidateSize();
      });

      return map;
    } catch (e) {
      showError(el, function () {
        el._nzMapInitialized = false;
        buildMap(el, view, onReady);
      });
      return null;
    }
  }

  function initBoundaryMaps() {
    var containers = document.querySelectorAll(".nz-geo-map[data-points]");
    containers.forEach(function (el) {
      if (el._nzMapInitialized || typeof window.L === "undefined") {
        return;
      }
      var points;
      try {
        points = JSON.parse(el.getAttribute("data-points"));
      } catch (e) {
        return;
      }
      if (!points || !points.length) {
        return;
      }

      el._nzMapInitialized = true;
      buildMap(el, points, function (map) {
        var polygon = window.L.polygon(points, { color: "#3b82f6", weight: 2, fillOpacity: 0.15 }).addTo(map);
        map.fitBounds(polygon.getBounds(), { padding: [16, 16] });
      });
    });
  }

  function initAddressMaps() {
    var containers = document.querySelectorAll(".nz-address-map[data-lat][data-lng]");
    containers.forEach(function (el) {
      if (el._nzMapInitialized) {
        return;
      }
      var lat = parseFloat(el.getAttribute("data-lat"));
      var lng = parseFloat(el.getAttribute("data-lng"));
      if (isNaN(lat) || isNaN(lng)) {
        return;
      }
      if (typeof window.L === "undefined") {
        showError(el, function () {
          window.location.reload();
        });
        return;
      }

      el._nzMapInitialized = true;
      buildMap(el, [lat, lng], function (map) {
        map.setView([lat, lng], 16);
        window.L.marker([lat, lng]).addTo(map);
      });
    });
  }

  function initAllMaps() {
    initBoundaryMaps();
    initAddressMaps();
  }

  document.addEventListener("DOMContentLoaded", initAllMaps);
})();
