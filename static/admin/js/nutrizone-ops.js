/* Yetkazib berish narxlari → "Narx kalkulyatori": asks /django-admin/ordering/deliverysettings/calc/ for the price a shopper would see. */
(function () {
  "use strict";
  function money(n) { return String(Math.round(n || 0)).replace(/\B(?=(\d{3})+(?!\d))/g, " "); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function init(root) {
    var q = function (k) { return root.querySelector('[data-c="' + k + '"]'); };
    var opts = {};
    try { opts = JSON.parse(q("opts").textContent || "{}"); } catch (e) { opts = {}; }
    var region = q("region"), city = q("city"), out = q("out"), timer = null, seq = 0;
    (opts.regions || []).forEach(function (r) { var o = document.createElement("option"); o.value = r.code; o.textContent = r.name; region.appendChild(o); });
    function onlyZone(zone) {
      root.querySelectorAll("[data-only]").forEach(function (el) { el.hidden = zone && el.getAttribute("data-only") !== zone; });
    }
    function fillCities() {
      var r = (opts.regions || []).filter(function (x) { return x.code === region.value; })[0];
      city.innerHTML = '<option value="">—</option>';
      (r ? r.cities : []).forEach(function (c) { var o = document.createElement("option"); o.value = c.code; o.textContent = c.name; city.appendChild(o); });
      onlyZone(region.value ? (region.value === "TGCITYR" ? "tashkent" : "regions") : "");
    }
    function run() {
      if (!region.value) { out.innerHTML = '<span class="nzdp-muted">Hududni tanlang</span>'; return; }
      var params = new URLSearchParams({ region: region.value, city: city.value, kg: q("kg").value, km: q("km").value, total: q("total").value });
      var mine = ++seq;
      out.style.opacity = ".6";
      fetch(root.getAttribute("data-endpoint") + "?" + params.toString(), { credentials: "same-origin" })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (mine !== seq) return;
          out.style.opacity = "";
          if (!d.ok) { out.innerHTML = '<span class="nzdp-muted">' + esc(d.error || "Xatolik") + "</span>"; return; }
          var meta = [d.zone_label, d.carrier, d.eta].filter(Boolean).map(function (t) { return "<span>" + esc(t) + "</span>"; }).join("");
          var parts = (d.parts || []).map(function (t) { return "<span>" + esc(t) + "</span>"; }).join("");
          var fee = d.fee > 0 ? money(d.fee) + " so'm" : "Bepul";
          var strike = d.fee === 0 && d.base_fee > 0 ? ' <s class="nzdp-muted" style="font-size:1rem">' + money(d.base_fee) + " so'm</s>" : "";
          out.innerHTML = '<div class="fee">' + fee + strike + '</div><div class="meta">' + meta + '</div><div class="meta">' + parts + "</div>";
        })
        .catch(function () { out.style.opacity = ""; out.innerHTML = '<span class="nzdp-muted">Hisoblab bo\'lmadi</span>'; });
    }
    function later() { clearTimeout(timer); timer = setTimeout(run, 250); }
    region.addEventListener("change", function () { fillCities(); run(); });
    root.addEventListener("input", function (e) { if (e.target !== region) later(); });
    root.addEventListener("change", function (e) { if (e.target === city) run(); });
    onlyZone("");
  }
  function boot() { document.querySelectorAll(".nzdp-calc[data-endpoint]").forEach(init); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();

/* Moliya: KPI numbers count up from 0 on load ([data-nzf-count]; "1 234 567" style, sign kept). */
(function () {
  "use strict";
  if (window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  function run() {
    document.querySelectorAll("[data-nzf-count]").forEach(function (el) {
      var node = el.firstChild;
      if (!node || node.nodeType !== 3) return;
      var m = node.textContent.match(/^(\s*)([−-]?)([\d ]+)(.*)$/);
      if (!m) return;
      var target = parseInt(m[3].replace(/\s/g, ""), 10);
      if (!target || target < 10) return;
      var t0 = null, dur = 900;
      function fmt(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, " "); }
      function step(ts) {
        if (t0 === null) t0 = ts;
        var p = Math.min(1, (ts - t0) / dur), e = 1 - Math.pow(1 - p, 3);
        node.textContent = m[1] + m[2] + fmt(Math.round(target * e)) + m[4];
        if (p < 1) requestAnimationFrame(step);
      }
      requestAnimationFrame(step);
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run); else run();
})();
