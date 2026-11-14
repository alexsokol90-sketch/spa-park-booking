/* Виджет «Забронировать онлайн» для сайта СПА-парка (spapark86.ru) и любых других страниц.
   Подключение одной строкой перед </body>:
   <script src="https://spa.5-42-98-218.sslip.io/static/widget.js" async></script>
   Необязательно: data-label="Записаться", data-start="couple" (сразу «СПА для двоих»), data-position="left".
   Свои кнопки на странице: любой элемент с атрибутом data-spa-book (например, <a data-spa-book="prog_23">). */
(function () {
  "use strict";
  var script = document.currentScript;
  var base = script.src.replace(/\/static\/widget\.js.*$/, "/");
  var label = script.getAttribute("data-label") || "Забронировать онлайн";
  var defaultStart = script.getAttribute("data-start") || "book";
  var left = script.getAttribute("data-position") === "left";
  var overlay = null;

  var css = document.createElement("style");
  css.textContent =
    ".spa-book-btn{position:fixed;bottom:24px;" + (left ? "left" : "right") + ":24px;z-index:2147483000;border:0;cursor:pointer;" +
    "padding:16px 24px;background:linear-gradient(180deg,#b79a72,#836c4a);color:#fff;font:600 14px/1 Inter,Arial,sans-serif;" +
    "letter-spacing:.04em;text-transform:uppercase;box-shadow:0 12px 30px rgba(38,39,43,.35)}" +
    ".spa-book-btn:hover{filter:brightness(1.08)}" +
    ".spa-book-overlay{position:fixed;inset:0;z-index:2147483001;background:rgba(26,26,29,.45);display:flex;justify-content:flex-end;align-items:flex-end}" +
    ".spa-book-frame{width:420px;height:min(740px,calc(100vh - 32px));margin:16px;border:0;background:#f7f4ef;box-shadow:0 24px 60px rgba(0,0,0,.35)}" +
    "@media(max-width:760px){.spa-book-frame{width:100%;height:100%;margin:0}}";
  document.head.appendChild(css);

  function open(start) {
    if (overlay) return;
    overlay = document.createElement("div");
    overlay.className = "spa-book-overlay";
    var frame = document.createElement("iframe");
    frame.className = "spa-book-frame";
    frame.title = "Онлайн-запись в СПА-парк";
    frame.allow = "microphone";
    frame.src = base + "?embed=1&start=" + encodeURIComponent(start || defaultStart);
    overlay.appendChild(frame);
    overlay.addEventListener("click", function (e) { if (e.target === overlay) close(); });
    document.body.appendChild(overlay);
  }

  function close() {
    if (overlay) { overlay.remove(); overlay = null; }
  }

  window.addEventListener("message", function (e) {
    if (e.origin + "/" === base && e.data && e.data.spaPark === "close") close();
  });
  document.addEventListener("click", function (e) {
    var el = e.target.closest && e.target.closest("[data-spa-book]");
    if (el) { e.preventDefault(); open(el.getAttribute("data-spa-book")); }
  });

  var btn = document.createElement("button");
  btn.type = "button";
  btn.className = "spa-book-btn";
  btn.textContent = label;
  btn.addEventListener("click", function () { open(defaultStart); });
  document.body.appendChild(btn);
  window.SpaParkBooking = { open: open, close: close };
})();
