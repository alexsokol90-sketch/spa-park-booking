"use strict";
// Эмулятор чата MAX: тот же движок диалога, что и в боте. Гость определяется отрицательным uid.
(function () {
  const log = document.getElementById("log");
  const input = document.getElementById("input");
  const KEY = "spa_uid";

  function uid() {
    let id = Number(localStorage.getItem(KEY));
    if (!id) {
      id = -Math.floor(1e6 + Math.random() * 9e9);
      localStorage.setItem(KEY, String(id));
    }
    return id;
  }

  function bold(text) {
    const div = document.createElement("div");
    div.textContent = text;
    div.innerHTML = div.innerHTML.replace(/\*([^*\n]+)\*/g, "<b>$1</b>");
    return div;
  }

  function scroll() { log.scrollTop = log.scrollHeight; }

  function addMine(text) {
    const el = document.createElement("div");
    el.className = "msg me";
    el.textContent = text;
    log.appendChild(el);
    scroll();
  }

  function keyboard(m) {
    const kb = document.createElement("div");
    kb.className = "kb";
    const rows = [];
    if (m.link) rows.push([{ link: m.link }]);
    if (m.request_contact) rows.push([{ contact: true }]);
    m.buttons.forEach((row) => rows.push(row));
    rows.forEach((row) => {
      const r = document.createElement("div");
      r.className = "kb-row";
      row.forEach((b) => r.appendChild(button(b)));
      kb.appendChild(r);
    });
    return kb;
  }

  function button(b) {
    if (b.link) {
      const a = document.createElement("a");
      a.href = b.link.url; a.target = "_blank"; a.rel = "noopener"; a.textContent = b.link.text + " ↗";
      return a;
    }
    const btn = document.createElement("button");
    btn.type = "button";
    if (b.contact) {
      btn.className = "contact";
      btn.textContent = "📱 Поделиться номером";
      btn.onclick = () => {
        const phone = window.prompt("Номер телефона (демо: +7 900 000-00-01 — гость из базы)", "+7 900 000-00-01");
        if (phone) { addMine("📱 " + phone); send({ phone: phone }); }
      };
      return btn;
    }
    btn.textContent = b.text;
    btn.onclick = () => { addMine(b.text); send({ payload: b.payload }); };
    return btn;
  }

  function addBot(m, cls) {
    const el = document.createElement("div");
    el.className = "msg " + (cls || (m.text.startsWith("Администратор:") ? "admin" : "bot"));
    el.appendChild(bold(m.text));
    if (m.buttons.length || m.link || m.request_contact) el.appendChild(keyboard(m));
    log.appendChild(el);
    scroll();
  }

  async function send(body) {
    const typing = document.createElement("div");
    typing.className = "typing";
    typing.textContent = "ассистент печатает…";
    log.appendChild(typing);
    scroll();
    try {
      const resp = await fetch("api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.assign({ uid: uid() }, body)),
      });
      const data = await resp.json();
      typing.remove();
      (data.messages || []).forEach((m) => addBot(m));
    } catch (e) {
      typing.textContent = "Нет связи с сервером";
    }
  }

  async function poll() {
    try {
      const resp = await fetch("api/chat/inbox?uid=" + uid());
      const data = await resp.json();
      (data.messages || []).forEach((m) => addBot(m));
    } catch (e) { /* сеть недоступна — повторим позже */ }
  }

  document.getElementById("form").addEventListener("submit", (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    addMine(text);
    send({ text: text });
  });

  document.getElementById("reset").addEventListener("click", () => {
    localStorage.removeItem(KEY);
    log.innerHTML = "";
    send({});
  });

  send({});
  setInterval(poll, 3000);
})();
