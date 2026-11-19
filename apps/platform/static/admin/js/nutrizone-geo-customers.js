/* Geo → Mijozlar xaritasi: customers (clustered by screen distance), region bubbles, branches; period / metric / segment
   filters, customer search and a region ranking that flies the map. Data: templates/admin/geo_customers.html data-src. */
(function () {
  "use strict";
  function ready(fn) { if (document.readyState !== "loading") fn(); else document.addEventListener("DOMContentLoaded", fn); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function som(n) { return Math.round(n || 0).toLocaleString("ru-RU").replace(/,/g, " "); }
  function compact(n) {
    n = n || 0;
    if (n >= 1e9) return (n / 1e9).toFixed(1).replace(".0", "") + " mlrd";
    if (n >= 1e6) return (n / 1e6).toFixed(1).replace(".0", "") + " mln";
    if (n >= 1e3) return Math.round(n / 1e3) + " ming";
    return String(Math.round(n));
  }
  var ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/";
  var LAYERS = {
    street: { label: "Xarita", url: ESRI + "World_Street_Map/MapServer/tile/{z}/{y}/{x}" },
    satellite: { label: "Sputnik", url: ESRI + "World_Imagery/MapServer/tile/{z}/{y}/{x}" },
    hybrid: { label: "Gibrid", url: ESRI + "World_Imagery/MapServer/tile/{z}/{y}/{x}", labels: ESRI + "Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}" },
    topo: { label: "Relyef", url: ESRI + "World_Topo_Map/MapServer/tile/{z}/{y}/{x}" },
  };
  var UZ = [[37.1, 55.9], [45.6, 73.2]]; // Uzbekistan's bounding box

  ready(function () {
    var root = document.querySelector("[data-nzcm]");
    if (!root || !window.L) return;
    var L = window.L;
    var mapEl = root.querySelector("[data-map]");
    var map = L.map(mapEl, { zoomControl: false, scrollWheelZoom: false, minZoom: 5, maxBounds: L.latLngBounds([[33, 50], [49, 78]]) });
    map.fitBounds(UZ, { padding: [10, 10] });
    if (window.ResizeObserver) new ResizeObserver(function () { map.invalidateSize(); }).observe(mapEl);
    L.control.zoom({ position: "topright" }).addTo(map);
    map.on("focus click", function () { map.scrollWheelZoom.enable(); });

    // base layers (the same choice as every geo page, remembered)
    var tile = null, labels = null;
    var bar = L.DomUtil.create("div", "nzgeo-layers");
    bar.innerHTML = Object.keys(LAYERS).map(function (k) { return '<button type="button" data-layer="' + k + '">' + LAYERS[k].label + "</button>"; }).join("");
    L.DomEvent.disableClickPropagation(bar);
    function useLayer(key) {
      var def = LAYERS[key] || LAYERS.street;
      if (tile) map.removeLayer(tile);
      if (labels) { map.removeLayer(labels); labels = null; }
      tile = L.tileLayer(def.url, { maxZoom: 19, attribution: "Tiles &copy; Esri" }).addTo(map);
      if (def.labels) labels = L.tileLayer(def.labels, { maxZoom: 19 }).addTo(map);
      try { localStorage.setItem("nzgeo-layer", key); } catch (e) { /* private mode */ }
      Array.prototype.forEach.call(bar.querySelectorAll("button"), function (b) { b.classList.toggle("on", b.getAttribute("data-layer") === key); });
    }
    bar.addEventListener("click", function (e) { var b = e.target.closest("button"); if (b) useLayer(b.getAttribute("data-layer")); });
    var ctl = L.control({ position: "topright" }); ctl.onAdd = function () { return bar; }; ctl.addTo(map);
    var savedLayer = "street"; try { savedLayer = localStorage.getItem("nzgeo-layer") || "street"; } catch (e) { /* ignore */ }
    useLayer(savedLayer);

    var state = { data: null, metric: "revenue", hidden: {}, period: root.getAttribute("data-period") };
    var segColor = {};
    var regionLayer = L.layerGroup().addTo(map), pointLayer = L.layerGroup().addTo(map), branchLayer = L.layerGroup().addTo(map);
    var loading = root.querySelector("[data-loading]");

    function popup(c) {
      var seg = state.data.segments.filter(function (s) { return s.key === c.seg; })[0] || {};
      return '<div class="nzcm-pop"><h5>' + esc(c.name) + '</h5><span class="seg" style="--t:' + seg.color + '">' + esc(seg.label) + "</span>" +
        "<dl><dt>Telefon</dt><dd>" + (c.phone ? '<a href="tel:' + esc(c.phone) + '">' + esc(c.phone) + "</a>" : "—") + "</dd>" +
        "<dt>Buyurtmalar</dt><dd>" + c.orders + "</dd><dt>Xarid summasi</dt><dd>" + som(c.spent) + " so'm</dd>" +
        "<dt>Oxirgi buyurtma</dt><dd>" + (esc(c.last) || "—") + "</dd><dt>Joy</dt><dd>" + esc([c.city, c.region].filter(Boolean).join(", ")) + "</dd>" +
        "<dt>Nuqta</dt><dd>" + (c.src === "order" ? "oxirgi yetkazish" : "saqlangan manzil") + "</dd></dl>" +
        '<div class="acts"><a href="' + esc(c.url) + '">Mijoz kartasi</a>' + (c.orders_url ? '<a href="' + esc(c.orders_url) + '">Buyurtmalari</a>' : "") +
        '<a href="https://yandex.uz/maps/?pt=' + c.lng + "," + c.lat + '&z=17&l=map" target="_blank" rel="noopener">Yandex</a></div></div>';
    }

    // ---- customers: grid clustering in screen pixels, re-drawn on zoom / pan
    function drawPoints() {
      pointLayer.clearLayers();
      if (!state.data) return;
      var pts = state.data.customers.filter(function (c) { return !state.hidden[c.seg]; });
      var z = map.getZoom(), cell = z >= 13 ? 0 : 56, buckets = {};
      pts.forEach(function (c) {
        if (!cell) { buckets[c.id] = [c]; return; }
        var p = map.project([c.lat, c.lng], z), k = Math.floor(p.x / cell) + ":" + Math.floor(p.y / cell);
        (buckets[k] = buckets[k] || []).push(c);
      });
      Object.keys(buckets).forEach(function (k) {
        var group = buckets[k];
        if (group.length === 1) {
          var c = group[0];
          L.marker([c.lat, c.lng], { icon: L.divIcon({ className: "", iconSize: [20, 20], iconAnchor: [10, 10],
            html: '<div class="nzcm-dot ' + c.seg + '" style="--t:' + segColor[c.seg] + '"></div>' }), title: c.name, riseOnHover: true })
            .bindPopup(popup(c), { maxWidth: 300 }).addTo(pointLayer);
          return;
        }
        var lat = 0, lng = 0;
        group.forEach(function (c) { lat += c.lat; lng += c.lng; });
        var size = Math.min(58, 30 + Math.round(Math.log2(group.length) * 6));
        var spent = group.reduce(function (s, c) { return s + c.spent; }, 0);
        L.marker([lat / group.length, lng / group.length], { icon: L.divIcon({ className: "", iconSize: [size, size], iconAnchor: [size / 2, size / 2],
          html: '<div class="nzcm-cluster" style="width:' + size + "px;height:" + size + 'px">' + group.length + "</div>" }),
          title: group.length + " mijoz · " + som(spent) + " so'm" })
          .on("click", function () { map.fitBounds(L.latLngBounds(group.map(function (c) { return [c.lat, c.lng]; })).pad(0.3), { maxZoom: 15 }); })
          .addTo(pointLayer);
      });
    }

    // ---- regions: a bubble per region sized by the chosen metric, its name and value underneath
    function drawRegions() {
      regionLayer.clearLayers();
      if (!state.data) return;
      var rows = state.data.regions, max = Math.max.apply(null, rows.map(function (r) { return r[state.metric]; }).concat([1]));
      rows.forEach(function (r) {
        var v = r[state.metric];
        if (!v) return;
        var radius = 14 + Math.sqrt(v / max) * 46;
        L.circleMarker([r.lat, r.lng], { radius: radius, color: "#0d9488", weight: 2, fillColor: "#14b8a6", fillOpacity: 0.18, interactive: true })
          .bindTooltip("<b>" + esc(r.name) + "</b><br>" + r.customers + " mijoz · " + r.orders + " buyurtma<br>" + som(r.revenue) + " so'm · " + r.branches + " filial", { sticky: true })
          .on("click", function () { focusRegion(r); })
          .addTo(regionLayer);
        var label = state.metric === "revenue" ? compact(v) + " so'm" : v + (state.metric === "customers" ? " mijoz" : " buyurtma");
        L.marker([r.lat, r.lng], { interactive: false, icon: L.divIcon({ className: "", iconSize: [0, 0],
          html: '<div class="nzcm-region-label">' + esc(r.name.replace(/ viloyati| shahri/, "")) + "<small>" + label + "</small></div>" }) }).addTo(regionLayer);
      });
    }

    function drawBranches() {
      branchLayer.clearLayers();
      (state.data ? state.data.branches : []).forEach(function (b) {
        var wh = b.kind === "warehouse";
        L.marker([b.lat, b.lng], { zIndexOffset: 500, icon: L.divIcon({ className: "", iconSize: [28, 28], iconAnchor: [14, 14],
          html: '<div class="nzcm-branch' + (wh ? " wh" : "") + '"><i class="fas ' + (wh ? "fa-warehouse" : "fa-store") + '"></i></div>' }) })
          .bindTooltip(esc(b.name) + (wh ? " · sklad" : ""), { direction: "top", offset: [0, -12] }).addTo(branchLayer);
      });
    }

    function focusRegion(r) {
      var inside = state.data.customers.filter(function (c) { return c.region === r.name; });
      if (inside.length > 1) map.fitBounds(L.latLngBounds(inside.map(function (c) { return [c.lat, c.lng]; })).pad(0.25), { maxZoom: 13 });
      else map.setView([r.lat, r.lng], inside.length ? 11 : 8);
      Array.prototype.forEach.call(root.querySelectorAll("[data-regions] button"), function (b) { b.classList.toggle("on", b.getAttribute("data-id") === r.id); });
    }

    function stat(label, value, tone, icon, sub) {
      return '<div class="nzi-stat" style="--t:' + tone + '"><i class="fas ' + icon + '" aria-hidden="true"></i><div><b>' + value + "</b><span>" + label + "</span>" + (sub ? "<small>" + sub + "</small>" : "") + "</div></div>";
    }

    function drawSide() {
      var d = state.data, t = d.totals;
      root.querySelector("[data-stats]").innerHTML =
        stat("Xaritadagi mijozlar", t.on_map, "#0d9488", "fa-users", t.unplaced ? t.unplaced + " tasi nuqtasiz" : "hammasi nuqtali") +
        stat("Xaridorlar", t.buyers, "#16a34a", "fa-bag-shopping", d.period_label.toLowerCase()) +
        stat("Tushum (yetkazilgan)", compact(t.revenue) + " so'm", "#4f46e5", "fa-sack-dollar", "onlayn buyurtmalar") +
        stat("Faol hududlar", t.regions_active + " / " + d.regions.length, "#d97706", "fa-map", "mijozi bor viloyatlar") +
        stat("VIP chegarasi", compact(t.vip_cut) + " so'm", "#db2777", "fa-crown", "eng ko'p xarid qilgan 10%");
      root.querySelector("[data-period-label]").textContent = d.period_label;
      var max = Math.max.apply(null, d.regions.map(function (r) { return r.revenue; }).concat([1]));
      root.querySelector("[data-regions]").innerHTML = d.regions.map(function (r, i) {
        return '<li><button type="button" data-id="' + r.id + '" class="' + (r.customers ? "" : "is-empty") + '"><span class="n">' + (i + 1) + '</span><span class="nm">' + esc(r.name) +
          '</span><span class="v">' + compact(r.revenue) + '</span><span class="bar"><i style="width:' + Math.round(r.revenue / max * 100) + '%"></i></span><span class="sub">' +
          r.customers + " mijoz · " + r.orders + " buyurtma" + (r.avg ? " · o'rtacha " + compact(r.avg) : "") + " · " + (r.branches ? r.branches + " filial" : "filial yo'q") + "</span></button></li>";
      }).join("");
      var leads = (d.segments.filter(function (s) { return s.key === "lead"; })[0] || {}).n || 0;
      var vip = (d.segments.filter(function (s) { return s.key === "vip"; })[0] || {}).n || 0;
      var top = d.regions[0];
      var tips = [];
      if (top && top.revenue) tips.push(["#4f46e5", "fa-trophy", "<b>" + esc(top.name) + "</b> — tushumning " + top.share + "%. Yetkazish tezligi va zaxirani shu hududga moslang."]);
      if (t.no_branch.length) tips.push(["#ea580c", "fa-store", "Filialsiz, lekin mijozi bor hududlar: <b>" + t.no_branch.map(esc).join(", ") + "</b> — yangi filial yoki punkt uchun nomzod."]);
      if (leads) tips.push(["#64748b", "fa-bell", "<b>" + leads + "</b> mijoz manzil saqlagan, lekin bu davrda buyurtma bermagan — eslatma yoki kupon yuboring."]);
      if (vip) tips.push(["#d97706", "fa-crown", "<b>" + vip + "</b> VIP mijoz — shaxsiy taklif va tezkor yetkazish bilan ushlab qoling."]);
      if (t.unplaced) tips.push(["#e11d48", "fa-location-crosshairs", "<b>" + t.unplaced + "</b> mijozning nuqtasi yo'q — buyurtmada xaritada belgilash endi oson, keyingi buyurtmada qo'shiladi."]);
      root.querySelector("[data-insights]").innerHTML = '<h4><i class="fas fa-lightbulb" aria-hidden="true"></i> Tavsiyalar</h4>' +
        (tips.length ? tips.map(function (x) { return '<div class="nzcm-insight" style="--t:' + x[0] + '"><i class="fas ' + x[1] + '" aria-hidden="true"></i><span>' + x[2] + "</span></div>"; }).join("") : '<p class="nzi-muted">Bu davrda ma\'lumot yo\'q.</p>');
      root.querySelector("[data-legend]").innerHTML = d.segments.map(function (s) {
        return '<label style="--t:' + s.color + '"><input type="checkbox" data-seg="' + s.key + '"' + (state.hidden[s.key] ? "" : " checked") + "><i></i>" + esc(s.label) + " <b>" + s.n + "</b></label>";
      }).join("") + '<label style="--t:#ea580c"><input type="checkbox" data-branches checked><i></i>Filiallar</label>';
    }

    function load(period) {
      loading.hidden = false;
      fetch(root.getAttribute("data-src") + "?p=" + encodeURIComponent(period), { credentials: "same-origin" })
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(function (d) {
          state.data = d; state.period = period;
          d.segments.forEach(function (s) { segColor[s.key] = s.color; });
          drawSide(); drawRegions(); drawPoints(); drawBranches();
          try { history.replaceState(null, "", "?p=" + period); } catch (e) { /* ignore */ }
        })
        .catch(function () { root.querySelector("[data-stats]").innerHTML = '<p class="nzi-muted">Ma\'lumotni yuklab bo\'lmadi — sahifani yangilang.</p>'; })
        .finally(function () { loading.hidden = true; });
    }

    map.on("zoomend moveend", drawPoints);
    root.addEventListener("click", function (e) {
      var p = e.target.closest("[data-period]");
      if (p && p.tagName === "BUTTON") {
        Array.prototype.forEach.call(root.querySelectorAll(".nzcm-seg button"), function (b) { b.classList.toggle("on", b === p); b.setAttribute("aria-selected", b === p); });
        load(p.getAttribute("data-period")); return;
      }
      var m = e.target.closest("[data-metric]");
      if (m) {
        state.metric = m.getAttribute("data-metric");
        Array.prototype.forEach.call(root.querySelectorAll("[data-metric]"), function (b) { b.classList.toggle("on", b === m); });
        drawRegions(); return;
      }
      var rb = e.target.closest("[data-regions] button");
      if (rb) { var r = state.data.regions.filter(function (x) { return x.id === rb.getAttribute("data-id"); })[0]; if (r) focusRegion(r); }
    });
    root.addEventListener("change", function (e) {
      if (e.target.matches("[data-seg]")) { state.hidden[e.target.getAttribute("data-seg")] = !e.target.checked; drawPoints(); }
      if (e.target.matches("[data-branches]")) { if (e.target.checked) branchLayer.addTo(map); else map.removeLayer(branchLayer); }
    });

    // customer search: name or phone digits, among the customers on the map
    var search = root.querySelector("[data-search]"), results = root.querySelector("[data-results]");
    search.addEventListener("input", function () {
      var q = search.value.trim().toLowerCase(), digits = q.replace(/\D/g, "");
      if (!state.data || q.length < 2) { results.hidden = true; return; }
      var hits = state.data.customers.filter(function (c) {
        return c.name.toLowerCase().indexOf(q) !== -1 || (digits.length >= 3 && c.phone.replace(/\D/g, "").indexOf(digits) !== -1);
      }).slice(0, 8);
      results.innerHTML = hits.length ? hits.map(function (c) {
        return '<button type="button" data-cid="' + c.id + '"><span class="nzcm-dot" style="--t:' + segColor[c.seg] + ';width:12px;height:12px"></span><span><b>' + esc(c.name) + "</b><small>" +
          esc(c.phone) + " · " + c.orders + " buyurtma · " + esc(c.city) + "</small></span></button>";
      }).join("") : '<p class="nzi-muted" style="padding:8px;margin:0">Topilmadi</p>';
      results.hidden = false;
    });
    search.addEventListener("keydown", function (e) { if (e.key === "Enter") e.preventDefault(); if (e.key === "Escape") results.hidden = true; });
    results.addEventListener("click", function (e) {
      var b = e.target.closest("[data-cid]");
      if (!b) return;
      var c = state.data.customers.filter(function (x) { return x.id === b.getAttribute("data-cid"); })[0];
      results.hidden = true;
      if (!c) return;
      state.hidden[c.seg] = false;
      map.setView([c.lat, c.lng], 16);
      setTimeout(function () { L.popup({ maxWidth: 300 }).setLatLng([c.lat, c.lng]).setContent(popup(c)).openOn(map); }, 350);
    });
    L.DomEvent.disableClickPropagation(root.querySelector(".nzcm-top"));
    L.DomEvent.disableScrollPropagation(root.querySelector(".nzcm-top"));
    ["legend", "metric"].forEach(function (k) { var el = root.querySelector(".nzcm-" + k); L.DomEvent.disableClickPropagation(el); });

    load(state.period);
    setTimeout(function () { map.invalidateSize(); }, 250);
  });
})();
