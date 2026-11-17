/* Dashboard → To'lovlar: copy callback URLs, reveal typed secrets, connection self-test. */
(function () {
  "use strict";

  document.addEventListener("click", function (e) {
    var copy = e.target.closest("[data-pay-copy]");
    if (copy) {
      var value = copy.getAttribute("data-pay-copy");
      var done = function () {
        var label = copy.textContent;
        copy.classList.add("ok");
        copy.textContent = copy.getAttribute("data-done") || "✓";
        setTimeout(function () { copy.classList.remove("ok"); copy.textContent = label; }, 1500);
      };
      if (navigator.clipboard) navigator.clipboard.writeText(value).then(done, function () {});
      return;
    }
    var eye = e.target.closest("[data-pay-eye]");
    if (eye) {
      var input = eye.parentElement.querySelector("input");
      input.type = input.type === "password" ? "text" : "password";
      eye.querySelector("i").className = input.type === "password" ? "fas fa-eye" : "fas fa-eye-slash";
    }
  });

  var test = document.querySelector("[data-pay-selftest]");
  if (test) {
    test.addEventListener("click", function () {
      var box = document.querySelector("[data-pay-result]");
      var csrf = document.querySelector("input[name=csrfmiddlewaretoken]").value;
      test.disabled = true;
      box.className = "pay-test-result show";
      box.textContent = test.getAttribute("data-wait");
      fetch(test.getAttribute("data-pay-selftest"), { method: "POST", headers: { "X-CSRFToken": csrf }, credentials: "same-origin" })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          box.className = "pay-test-result show " + (d.ok ? "ok" : "bad");
          box.textContent = d.message;
          if (d.explain) {
            var ex = document.createElement("small");
            ex.textContent = (d.code !== undefined && d.code !== null ? d.code + " · " : "") + d.explain;
            box.appendChild(ex);
          }
          var li = document.querySelector('[data-ready-key="selftest"]');
          if (li && d.ok) {
            li.classList.add("ok");
            li.querySelector("i").className = "fas fa-circle-check";
            var hint = li.querySelector("small");
            if (hint) hint.remove();
          }
          if (d.answer) {
            var pre = document.createElement("pre");
            pre.textContent = d.answer;
            box.appendChild(pre);
          }
        })
        .catch(function () { box.className = "pay-test-result show bad"; box.textContent = "Network error"; })
        .finally(function () { test.disabled = false; });
    });
  }

  var chartData = document.getElementById("pay-chart-data");
  var canvas = document.getElementById("pay-daily");
  if (chartData && canvas && window.Chart) {
    var d = JSON.parse(chartData.textContent);
    var dark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches && document.documentElement.getAttribute("data-theme") !== "light";
    if (document.documentElement.getAttribute("data-theme") === "dark") dark = true;
    var grid = dark ? "rgba(255,255,255,.08)" : "rgba(15,23,42,.06)";
    var tick = dark ? "#94a3b8" : "#64748b";
    new window.Chart(canvas, {
      type: "bar",
      data: { labels: d.labels, datasets: d.series.map(function (s) { return { label: s.name, data: s.data, backgroundColor: s.color, borderRadius: 4, stack: "v", maxBarThickness: 22 }; }) },
      options: {
        responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
        plugins: { legend: { position: "bottom", labels: { color: tick, boxWidth: 10, usePointStyle: true } },
                   tooltip: { callbacks: { label: function (c) { return c.dataset.label + ": " + Math.round(c.parsed.y).toLocaleString("ru-RU") + " so'm"; } } } },
        scales: { x: { stacked: true, grid: { display: false }, ticks: { color: tick, maxRotation: 0, autoSkip: true, maxTicksLimit: 10 } },
                  y: { stacked: true, grid: { color: grid }, ticks: { color: tick, callback: function (v) { return v >= 1e6 ? (v / 1e6) + "M" : v >= 1e3 ? (v / 1e3) + "k" : v; } } } }
      }
    });
  }
})();
