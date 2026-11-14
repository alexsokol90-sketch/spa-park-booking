"use strict";
// Страница гостя: каталог пространств, баннер cookie, согласия перед чатом, чат-ассистент (тот же движок, что в мессенджерах).
(function () {
  const UID_KEY = "spa_uid";
  const CONSENT_KEY = "spa_consent_v1";
  const COOKIE_KEY = "spa_cookie_ok";
  const chat = document.getElementById("chat");
  const log = document.getElementById("log");
  const form = document.getElementById("form");
  const input = document.getElementById("input");
  const gate = document.getElementById("consentGate");
  let pendingPayload = null;
  let started = false;

  function uid() {
    let id = Number(localStorage.getItem(UID_KEY));
    if (!id) {
      id = -Math.floor(1e6 + Math.random() * 9e9);
      localStorage.setItem(UID_KEY, String(id));
    }
    return id;
  }

  async function post(path, body) {
    const resp = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    return resp.json();
  }

  // ---------- cookie ----------
  const cookie = document.getElementById("cookie");
  if (!localStorage.getItem(COOKIE_KEY)) cookie.hidden = false;
  document.getElementById("cookieOk").onclick = () => { localStorage.setItem(COOKIE_KEY, new Date().toISOString()); cookie.hidden = true; };

  // ---------- каталог пространств ----------
  function rub(n) { return n.toLocaleString("ru-RU") + " ₽"; }

  async function loadSpaces() {
    const resp = await fetch("api/public/spaces");
    const data = await resp.json();
    const grid = document.getElementById("spaceGrid");
    data.spaces.forEach((s) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "space";
      card.style.backgroundImage = "url('static/img/" + s.code + ".jpg')";
      const body = document.createElement("div");
      body.className = "space-body";
      const name = document.createElement("div");
      name.className = "space-name";
      name.textContent = s.name;
      const desc = document.createElement("div");
      desc.className = "space-desc";
      desc.textContent = s.description;
      const meta = document.createElement("div");
      meta.className = "space-meta";
      meta.textContent = s.programs + " программ · от " + rub(s.min_price) + " →";
      body.append(name, desc, meta);
      card.append(body);
      card.onclick = () => openChat("space:" + s.id);
      grid.append(card);
    });
  }

  // ---------- чат ----------
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
    log.append(el);
    scroll();
  }

  function makeButton(b) {
    if (b.link) {
      const a = document.createElement("a");
      a.href = b.link.url; a.target = "_blank"; a.rel = "noopener"; a.textContent = b.link.text + " ↗";
      return a;
    }
    const btn = document.createElement("button");
    btn.type = "button";
    if (b.contact) {
      btn.className = "primary";
      btn.textContent = "Указать телефон";
      btn.onclick = () => {
        const phone = window.prompt("Ваш номер телефона", "+7 ");
        if (phone && phone.replace(/\D/g, "").length >= 10) { addMine(phone); send({ phone: phone }); }
      };
      return btn;
    }
    btn.textContent = b.text;
    if (/^(confirm|cbok|hold):/.test(b.payload) || b.payload === "cbok") btn.className = "primary";
    btn.onclick = () => { addMine(b.text); send({ payload: b.payload }); };
    return btn;
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
      row.forEach((b) => r.append(makeButton(b)));
      kb.append(r);
    });
    return kb;
  }

  function addBot(m) {
    const el = document.createElement("div");
    el.className = "msg " + (m.text.startsWith("Администратор:") ? "admin" : "bot");
    el.append(bold(m.text));
    if (m.buttons.length || m.link || m.request_contact) el.append(keyboard(m));
    log.append(el);
    scroll();
  }

  async function send(body) {
    const typing = document.createElement("div");
    typing.className = "typing";
    typing.textContent = "ассистент печатает…";
    log.append(typing);
    scroll();
    try {
      const data = await post("api/chat", Object.assign({ uid: uid() }, body));
      typing.remove();
      (data.messages || []).forEach(addBot);
    } catch (e) {
      typing.textContent = "Нет связи. Попробуйте ещё раз или позвоните: +7 (3466) 49-11-47";
    }
  }

  function showChat() {
    gate.hidden = true;
    log.hidden = false;
    form.hidden = false;
    if (!started) {
      started = true;
      send(pendingPayload ? { payload: pendingPayload } : {});
    } else if (pendingPayload) {
      send({ payload: pendingPayload });
    }
    pendingPayload = null;
    input.focus();
  }

  function openChat(payload) {
    pendingPayload = payload || null;
    chat.hidden = false;
    document.querySelector(".chat-fab").hidden = true;
    if (localStorage.getItem(CONSENT_KEY)) showChat();
  }

  document.querySelectorAll("[data-open-chat]").forEach((el) => el.addEventListener("click", () => openChat(el.dataset.payload)));
  document.getElementById("chatClose").onclick = () => { chat.hidden = true; document.querySelector(".chat-fab").hidden = false; };
  document.getElementById("chatReset").onclick = () => {
    localStorage.removeItem(UID_KEY);
    localStorage.removeItem(CONSENT_KEY);
    log.innerHTML = "";
    started = false;
    gate.hidden = false; log.hidden = true; form.hidden = true;
    document.getElementById("cPd").checked = false;
    document.getElementById("cAds").checked = false;
    document.getElementById("consentOk").disabled = true;
  };

  const cPd = document.getElementById("cPd");
  const cAds = document.getElementById("cAds");
  const okBtn = document.getElementById("consentOk");
  cPd.addEventListener("change", () => { okBtn.disabled = !cPd.checked; });
  okBtn.onclick = async () => {
    okBtn.disabled = true;
    await post("api/chat/consent", { uid: uid(), pd: true, ads: cAds.checked });
    localStorage.setItem(CONSENT_KEY, new Date().toISOString());
    showChat();
  };

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    addMine(text);
    send({ text: text });
  });

  // ---------- голосовые ----------
  const mic = document.getElementById("mic");
  let recorder = null;
  let chunks = [];

  async function sendVoice(blob) {
    const typing = document.createElement("div");
    typing.className = "typing";
    typing.textContent = "распознаю голосовое…";
    log.append(typing);
    scroll();
    try {
      const resp = await fetch("api/chat/voice?uid=" + uid(), { method: "POST", headers: { "Content-Type": blob.type || "audio/webm" }, body: blob });
      const data = await resp.json();
      typing.remove();
      (data.messages || []).forEach(addBot);
    } catch (e) {
      typing.textContent = "Не удалось отправить голосовое. Напишите, пожалуйста, текстом.";
    }
  }

  mic.addEventListener("click", async () => {
    if (recorder && recorder.state === "recording") {
      recorder.stop();
      return;
    }
    if (!navigator.mediaDevices || !window.MediaRecorder) {
      window.alert("Браузер не поддерживает запись голоса. Напишите, пожалуйста, текстом.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      recorder = new MediaRecorder(stream);
      chunks = [];
      recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        mic.classList.remove("rec");
        addMine("🎙 голосовое сообщение");
        sendVoice(new Blob(chunks, { type: recorder.mimeType || "audio/webm" }));
      };
      recorder.start();
      mic.classList.add("rec");
    } catch (e) {
      window.alert("Нет доступа к микрофону. Разрешите его в настройках браузера или напишите текстом.");
    }
  });

  async function poll() {
    if (!started) return;
    try {
      const resp = await fetch("api/chat/inbox?uid=" + uid());
      const data = await resp.json();
      (data.messages || []).forEach(addBot);
    } catch (e) { /* сеть недоступна — повторим позже */ }
  }

  // ---------- ссылки «Забронировать онлайн» и встраивание на другие сайты ----------
  const params = new URLSearchParams(location.search);
  const START = /^(book|couple|staff|prices|(prog|space)_\d{1,4})$/;
  const start = (params.get("start") || (params.has("book") ? "book" : "")).toLowerCase();
  const startPayload = START.test(start) ? start.replace("_", ":") : null;
  if (params.has("embed")) {
    document.body.classList.add("embed");
    document.getElementById("chatClose").onclick = () => window.parent.postMessage({ spaPark: "close" }, "*");
    if (localStorage.getItem(COOKIE_KEY) === null) localStorage.setItem(COOKIE_KEY, "embed");
    cookie.hidden = true;
  } else {
    loadSpaces();
  }
  if (params.has("embed") || startPayload) openChat(startPayload || "book");
  setInterval(poll, 3000);
})();
