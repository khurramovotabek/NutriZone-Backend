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
})();
