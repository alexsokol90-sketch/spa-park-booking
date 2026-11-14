"use strict";
// Кнопки «Скопировать код» на странице /links.
document.querySelectorAll("[data-copy]").forEach(function (b) {
  b.addEventListener("click", function () {
    navigator.clipboard.writeText(document.getElementById(b.dataset.copy).textContent).then(function () { b.textContent = "Скопировано"; });
  });
});
