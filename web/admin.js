"use strict";
// Интерфейс администратора: сетка по пространствам, захваты, карточки броней, запросы, обзвон, гости, маркетинг.
(function () {
  const TZ = "Asia/Yekaterinburg";
  const OFFSET = "+05:00";
  const OPEN_MIN = 10 * 60;
  const CLOSE_MIN = 24 * 60;
  const PX = 1.3; // пикселей на минуту
  const STEP = 30;
  const state = { day: null, grid: null, programs: [], serverSkew: 0, seenFeed: 0, segment: "lapsed_90" };

  // ---------- утилиты ----------
  function h(tag, attrs, children) {
    const el = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => {
      if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (v !== undefined && v !== null && v !== false) el.setAttribute(k, v);
    });
    (children || []).forEach((c) => el.append(c instanceof Node ? c : document.createTextNode(String(c))));
    return el;
  }

  async function api(path, opts) {
    const o = Object.assign({ headers: { "Content-Type": "application/json" } }, opts || {});
    if (o.body && typeof o.body !== "string") o.body = JSON.stringify(o.body);
    const resp = await fetch(path, o);
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      const err = new Error((data.detail && (data.detail.message || data.detail)) || resp.statusText);
      err.detail = data.detail;
      throw err;
    }
    return data;
  }

  const fmtTime = (iso) => new Date(iso).toLocaleTimeString("ru-RU", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
  const fmtDate = (iso) => new Date(iso).toLocaleDateString("ru-RU", { timeZone: TZ, day: "numeric", month: "long" });
  const dayStart = (day) => new Date(day + "T00:00:00" + OFFSET);
  const minutesOf = (iso, day) => (new Date(iso) - dayStart(day)) / 60000;
  const isoAt = (day, minutes) => {
    const hh = String(Math.floor(minutes / 60)).padStart(2, "0");
    const mm = String(minutes % 60).padStart(2, "0");
    return day + "T" + hh + ":" + mm + ":00" + OFFSET;
  };
  const serverNow = () => new Date(Date.now() + state.serverSkew);
  const todayStr = () => new Date().toLocaleDateString("sv-SE", { timeZone: TZ });

  function toast(text, kind) {
    const el = h("div", { class: "toast " + (kind || ""), text: text });
    document.getElementById("toasts").append(el);
    setTimeout(() => el.remove(), 9000);
  }

  // ---------- вкладки ----------
  const loaders = {};
  document.getElementById("tabs").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-tab]");
    if (!btn) return;
    document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("active", b === btn));
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.id === "tab-" + btn.dataset.tab));
    if (loaders[btn.dataset.tab]) loaders[btn.dataset.tab]();
  });

  // ---------- сетка ----------
  async function loadGrid() {
    const data = await api("api/admin/grid?day=" + state.day);
    state.grid = data;
    state.serverSkew = new Date(data.now) - Date.now();
    renderGrid();
  }

  function renderGrid() {
    const data = state.grid;
    const grid = document.getElementById("grid");
    const height = (CLOSE_MIN - OPEN_MIN) * PX;
    grid.innerHTML = "";
    grid.style.gridTemplateColumns = "56px repeat(" + data.spaces.length + ", 1fr)";
    grid.append(h("div", { class: "ghead" }));
    data.spaces.forEach((s) => grid.append(h("div", { class: "ghead" }, [s.name, h("small", { text: s.is_relax ? "без прогрева" : "" })])));
    const times = h("div", { class: "gtime", style: "height:" + height + "px" });
    for (let m = OPEN_MIN; m <= CLOSE_MIN; m += 60) {
      times.append(h("div", { style: "top:" + (m - OPEN_MIN) * PX + "px", text: String(m / 60).padStart(2, "0") + ":00" }));
    }
    grid.append(times);
    data.spaces.forEach((s) => grid.append(column(s, height)));
    drawNow(grid);
  }

  function column(space, height) {
    const col = h("div", { class: "gcol", style: "height:" + height + "px;background-size:100% " + 60 * PX + "px" });
    col.addEventListener("click", (e) => {
      if (e.target !== col) return;
      const minute = OPEN_MIN + Math.floor(e.offsetY / PX / STEP) * STEP;
      openNewBooking(space, minute);
    });
    state.grid.bookings.filter((b) => b.space_id === space.id).forEach((b) => drawBooking(col, b));
    return col;
  }

  function drawBooking(col, b) {
    const top = Math.max(0, minutesOf(b.starts_at, state.day) - OPEN_MIN) * PX;
    const end = minutesOf(b.ends_at, state.day) - OPEN_MIN;
    const busy = minutesOf(b.busy_until, state.day) - OPEN_MIN;
    const el = h("div", { class: "bk " + b.status, style: "top:" + top + "px;height:" + Math.max(18, end * PX - top - 2) + "px" }, [
      h("b", { text: fmtTime(b.starts_at) + " " + b.program_name }),
      h("div", { class: "meta", text: (b.guest_name || b.guest_phone || "гость") + " · " + b.master_name }),
    ]);
    if (b.status === "hold") {
      const left = (new Date(b.hold_expires_at) - serverNow()) / 1000;
      if (left < 120) el.classList.add("expiring");
      const who = b.source === "bot" ? "бот" : "администратор";
      el.append(h("span", { class: "tag", text: "держит " + who + " до " + fmtTime(b.hold_expires_at) }));
    } else if (b.preorders.length) {
      el.append(h("span", { class: "tag", text: "предзаказ: " + b.preorders.length }));
    }
    if (b.visit_status === "confirmed") el.append(h("span", { class: "tag", text: "визит подтверждён" }));
    if (b.payment_status !== "unpaid") el.append(h("span", { class: "tag", text: "оплачено" }));
    el.addEventListener("click", () => openBooking(b.id));
    col.append(el);
    if (busy > end) {
      col.append(h("div", { class: "cleanup", style: "top:" + end * PX + "px;height:" + (busy - end) * PX + "px", text: "уборка" }));
    }
  }

  function drawNow(grid) {
    if (state.day !== todayStr()) return;
    const m = minutesOf(serverNow().toISOString(), state.day) - OPEN_MIN;
    if (m < 0 || m > CLOSE_MIN - OPEN_MIN) return;
    const headH = grid.querySelector(".ghead").offsetHeight;
    grid.append(h("div", { class: "nowline", style: "top:" + (headH + m * PX) + "px" }));
  }

  function setDay(day) {
    state.day = day;
    document.getElementById("day").value = day;
    loadGrid();
  }

  function shiftDay(delta) {
    const d = new Date(state.day + "T12:00:00" + OFFSET);
    d.setDate(d.getDate() + delta);
    setDay(d.toLocaleDateString("sv-SE", { timeZone: TZ }));
  }

  document.getElementById("prevDay").onclick = () => shiftDay(-1);
  document.getElementById("nextDay").onclick = () => shiftDay(1);
  document.getElementById("today").onclick = () => setDay(todayStr());
  document.getElementById("day").onchange = (e) => setDay(e.target.value);

  // ---------- модальное окно новой записи ----------
  const modal = document.getElementById("modal");
  const box = document.getElementById("modalBox");
  let countdownTimer = null;

  function closeModal() {
    modal.hidden = true;
    clearInterval(countdownTimer);
  }
  modal.addEventListener("click", (e) => { if (e.target === modal) closeModal(); });

  function openNewBooking(space, minute) {
    const progs = state.programs.filter((p) => p.space_id === space.id);
    const select = h("select", { id: "nbProg" }, progs.map((p) => h("option", { value: p.id, text: p.name + " · " + p.duration_min + " мин · " + p.price + " ₽" })));
    const time = h("input", { type: "time", id: "nbTime", value: isoAt(state.day, minute).slice(11, 16), step: 1800 });
    const phone = h("input", { id: "nbPhone", placeholder: "+7 900 000-00-01" });
    const name = h("input", { id: "nbName", placeholder: "Имя (для нового гостя)" });
    const err = h("div", { class: "error" });
    box.innerHTML = "";
    box.append(
      h("h3", { text: "Новая запись · " + space.name + " · " + fmtDate(isoAt(state.day, minute)) }),
      h("label", {}, ["Программа", select]),
      h("label", {}, ["Начало", time]),
      h("label", {}, ["Телефон гостя", phone]),
      h("label", {}, ["Имя", name]),
      err,
      h("div", { class: "row-actions" }, [
        h("button", { type: "button", class: "primary", text: "Захватить окно на 15 мин", onclick: () => submitHold(select.value, time.value, phone.value, name.value, err) }),
        h("button", { type: "button", text: "Отмена", onclick: closeModal }),
      ])
    );
    modal.hidden = false;
  }

  async function submitHold(programId, time, phone, name, err) {
    const [hh, mm] = time.split(":").map(Number);
    try {
      const hold = await api("api/admin/hold", { method: "POST", body: { program_id: Number(programId), start: isoAt(state.day, hh * 60 + mm), phone: phone, name: name || null } });
      showHold(hold);
    } catch (e) {
      err.textContent = e.message;
      showAlternatives(e.detail, phone, name, err);
    }
  }

  function showAlternatives(detail, phone, name, err) {
    if (!detail || !detail.alternatives) return;
    const list = h("div", { class: "alts" });
    if (!detail.alternatives.length) list.append(h("p", { class: "muted", text: "Похожих окон в пределах ±2 часов нет." }));
    detail.alternatives.forEach((a) => {
      const prog = state.programs.find((p) => p.id === a.program_id) || { name: "" };
      list.append(h("button", { type: "button", text: fmtTime(a.start) + " · " + prog.name + " · " + a.master_name, onclick: async () => {
        try {
          showHold(await api("api/admin/hold", { method: "POST", body: { program_id: a.program_id, start: a.start, master_id: a.master_id, phone: phone, name: name || null } }));
        } catch (e) { err.textContent = e.message; }
      } }));
    });
    err.after(list);
  }

  function showHold(hold) {
    const cd = h("div", { class: "countdown" });
    const tick = () => {
      const left = Math.max(0, Math.round((new Date(hold.hold_expires_at) - serverNow()) / 1000));
      cd.textContent = String(Math.floor(left / 60)).padStart(2, "0") + ":" + String(left % 60).padStart(2, "0");
      if (!left) { clearInterval(countdownTimer); cd.textContent = "захват истёк"; }
    };
    box.innerHTML = "";
    box.append(
      h("h3", { text: "Окно закреплено" }),
      h("p", { text: hold.program_name + " · " + hold.space_name + " · " + fmtTime(hold.starts_at) + " · мастер " + hold.master_name }),
      h("p", { class: "muted", text: "Гость: " + (hold.guest_name || "") + " " + (hold.guest_phone || "") }),
      cd,
      h("div", { class: "row-actions" }, [
        h("button", { type: "button", class: "primary", text: "Подтвердить бронь", onclick: async () => {
          try { await api("api/admin/bookings/" + hold.id + "/confirm", { method: "POST" }); closeModal(); toast("Бронь создана"); } catch (e) { toast(e.message, "escalation"); }
        } }),
        h("button", { type: "button", class: "danger", text: "Снять захват", onclick: async () => { await api("api/admin/bookings/" + hold.id + "/cancel", { method: "POST" }); closeModal(); } }),
      ])
    );
    tick();
    clearInterval(countdownTimer);
    countdownTimer = setInterval(tick, 1000);
  }

  // ---------- карточка брони ----------
  const drawer = document.getElementById("drawer");
  const STATUS = { hold: "захват", confirmed: "подтверждена", completed: "завершена", cancelled: "отменена", expired: "захват истёк" };
  const VISIT = { none: "—", asked: "запрос отправлен, ждём ответа", confirmed: "гость подтвердил", declined: "гость отказался" };
  const PAY = { unpaid: "не оплачено", prepaid: "предоплата", paid: "оплачено", certificate: "сертификат" };

  async function openBooking(id) {
    const b = await api("api/admin/bookings/" + id);
    const pre = b.preorders.length ? b.preorders.map((p) => p.name + (p.qty > 1 ? " ×" + p.qty : "")).join(", ") : "—";
    const kv = [
      ["Гость", (b.guest_name || "—") + " · " + (b.guest_phone || "")],
      ["Программа", b.program_name],
      ["Пространство", b.space_name],
      ["Время", fmtDate(b.starts_at) + ", " + fmtTime(b.starts_at) + "–" + fmtTime(b.ends_at) + " (+уборка " + b.cleanup_min + " мин)"],
      ["Мастер занят", fmtTime(b.starts_at) + "–" + fmtTime(b.master_until) + " (" + b.master_min + " мин)"],
      ["Мастер", b.master_name],
      ["Гостей / стоимость", b.guests_count + " · " + b.price + " ₽" + (b.prepay ? " (нужна предоплата)" : "")],
      ["Статус", STATUS[b.status] + (b.status === "hold" ? " до " + fmtTime(b.hold_expires_at) : "")],
      ["Источник", b.source === "bot" ? "ассистент в MAX" : "ресепшен"],
      ["Визит", VISIT[b.visit_status]],
      ["Предзаказ", pre],
      ["Оплата", PAY[b.payment_status] + (b.payment_method ? " (" + b.payment_method + ")" : "")],
    ];
    const dl = h("dl", { class: "kv" });
    kv.forEach(([k, v]) => dl.append(h("dt", { text: k }), h("dd", { text: v })));
    const act = (text, fn, cls) => h("button", { type: "button", class: cls || "", text: text, onclick: async () => { await fn(); openBooking(id); } });
    const actions = h("div", { class: "actions" });
    if (b.status === "hold") actions.append(act("Подтвердить бронь", () => api("api/admin/bookings/" + id + "/confirm", { method: "POST" }), "primary"));
    if (b.status === "confirmed" || b.status === "completed") {
      [["paid", "карта на месте"], ["paid", "наличные"], ["paid", "ресепшен отеля"], ["prepaid", "онлайн на сайте"], ["certificate", "сертификат"]].forEach(([st, m]) =>
        actions.append(act("Оплата: " + m, () => api("api/admin/bookings/" + id + "/payment", { method: "POST", body: { status: st, method: m } }))));
    }
    if (b.status === "hold" || b.status === "confirmed") actions.append(act("Отменить", () => api("api/admin/bookings/" + id + "/cancel", { method: "POST" }), "danger"));
    drawer.innerHTML = "";
    drawer.append(
      h("button", { type: "button", class: "close", text: "✕", onclick: () => { drawer.hidden = true; } }),
      h("h3", { text: "Бронь №" + b.id }),
      dl,
      h("p", { class: "muted", text: "Оплата подтверждается вручную: открытого API кассы нет." }),
      h("button", { type: "button", text: "Карточка гостя", onclick: () => openGuest(b.guest_id) }),
      actions
    );
    drawer.hidden = false;
  }

  // ---------- запросы (эскалации) ----------
  async function loadEsc() {
    const data = await api("api/admin/escalations");
    const list = document.getElementById("escList");
    const fresh = data.items.filter((e) => e.status === "new").length;
    const badge = document.getElementById("escCount");
    badge.hidden = !fresh;
    badge.textContent = fresh;
    list.innerHTML = "";
    if (!data.items.length) list.append(h("p", { class: "muted", text: "Открытых запросов нет." }));
    data.items.forEach((e) => list.append(escCard(e)));
  }

  function escCard(e) {
    const hist = h("div", { class: "history" }, e.history.map((m) => h("p", { class: m.role, text: (m.role === "guest" ? "Гость: " : m.role === "admin" ? "Админ: " : "Бот: ") + m.text })));
    const input = h("input", { placeholder: "Ответить гостю в MAX…" });
    const send = async () => {
      if (!input.value.trim()) return;
      await api("api/admin/escalations/" + e.id + "/reply", { method: "POST", body: { text: input.value.trim() } });
      input.value = "";
      loadEsc();
    };
    const card = h("div", { class: "card" + (e.priority === "high" ? " high" : "") }, [
      h("div", { class: "head" }, [
        h("div", {}, [h("div", { class: "reason", text: (e.priority === "high" ? "🔴 " : "") + e.reason_title }), h("div", { class: "muted", text: (e.guest_name || "Гость") + " · " + (e.guest_phone || "телефон не указан") + " · " + fmtTime(e.created_at) })]),
        h("span", { class: "pill " + e.status, text: e.status === "new" ? "не принят · уведомлений: " + e.notified_count : "в работе" }),
      ]),
      h("p", { text: e.details }),
      hist,
      h("div", { class: "reply" }, [input, h("button", { type: "button", class: "primary", text: "Ответить", onclick: send })]),
      h("div", { class: "row-actions" }, [
        e.status === "new" ? h("button", { type: "button", text: "Принять", onclick: async () => { await api("api/admin/escalations/" + e.id + "/accept", { method: "POST" }); loadEsc(); } }) : "",
        h("button", { type: "button", text: "Закрыть", onclick: async () => { await api("api/admin/escalations/" + e.id + "/close", { method: "POST" }); loadEsc(); } }),
      ]),
    ]);
    input.addEventListener("keydown", (ev) => { if (ev.key === "Enter") send(); });
    return card;
  }
  loaders.esc = loadEsc;

  // ---------- обзвон ----------
  async function loadCalls() {
    const data = await api("api/admin/no-answer");
    const table = document.getElementById("callsTable");
    table.innerHTML = "";
    table.append(h("tr", {}, ["Время", "Гость", "Телефон", "Программа", "Мастер"].map((t) => h("th", { text: t }))));
    if (!data.items.length) table.append(h("tr", {}, [h("td", { colspan: 5, class: "muted", text: "Неответивших нет." })]));
    data.items.forEach((b) => table.append(h("tr", {}, [fmtDate(b.starts_at) + ", " + fmtTime(b.starts_at), b.guest_name || "—", b.guest_phone || "—", b.program_name, b.master_name].map((t) => h("td", { text: t })))));
  }
  loaders.calls = loadCalls;
  document.querySelectorAll("[data-job]").forEach((btn) => btn.addEventListener("click", async () => {
    const res = await api("api/admin/jobs/" + btn.dataset.job, { method: "POST" });
    toast("Готово: " + res.result);
    loadCalls();
  }));

  // ---------- гости ----------
  async function loadGuests() {
    const q = document.getElementById("guestQ").value;
    const data = await api("api/admin/guests?q=" + encodeURIComponent(q));
    const table = document.getElementById("guestsTable");
    table.innerHTML = "";
    table.append(h("tr", {}, ["Имя", "Телефон", "Карта", "Баллы", "Д. р.", "Визитов", "Последний визит", "Рассылки"].map((t) => h("th", { text: t }))));
    data.items.forEach((g) => table.append(h("tr", { onclick: () => openGuest(g.id) }, [
      g.name || "—", g.phone, g.loyalty_card || "—", g.loyalty_points, g.birth_date ? new Date(g.birth_date).toLocaleDateString("ru-RU") : "—",
      g.visits, g.last_visit ? fmtDate(g.last_visit) : "—", g.ads_ok ? "согласие есть" : "нет согласия",
    ].map((t) => h("td", { text: t })))));
  }
  loaders.guests = async () => { await loadGuests(); loadPdLog(); };

  const ACTIONS = { list_guests: "просмотр списка", view_guest: "карточка гостя", view_booking: "карточка брони", view_dialog: "диалог эскалации", export: "выгрузка данных", erase: "удаление данных", campaign: "рассылка" };
  async function loadPdLog() {
    const data = await api("api/admin/pd-log");
    const table = document.getElementById("pdLog");
    table.innerHTML = "";
    table.append(h("tr", {}, ["Когда", "Кто", "Действие", "Гость", "Детали"].map((t) => h("th", { text: t }))));
    data.items.slice(0, 30).forEach((l) => table.append(h("tr", {}, [fmtDate(l.created_at) + " " + fmtTime(l.created_at), l.actor, ACTIONS[l.action] || l.action, l.guest_name || (l.guest_id ? "#" + l.guest_id : "—"), l.details].map((t) => h("td", { text: t })))));
  }

  const KIND = { pd: "Обработка ПДн", rules: "Правила и противопоказания", ads: "Рекламные сообщения" };
  async function openGuest(id) {
    const g = await api("api/admin/guests/" + id);
    const dl = h("dl", { class: "kv" });
    [["Имя", g.name || "—"], ["Телефон", g.phone || "—"], ["Дата рождения", g.birth_date ? new Date(g.birth_date).toLocaleDateString("ru-RU") : "—"],
      ["Карта лояльности", (g.loyalty_card || "—") + " · баллов: " + g.loyalty_points], ["Язык", g.lang === "en" ? "английский" : "русский"],
      ["Рассылки", g.unsubscribed ? "отписан" : "—"]].forEach(([k, v]) => dl.append(h("dt", { text: k }), h("dd", { text: v })));
    const consents = h("div", {}, g.consents.map((c) => h("div", { class: "consent-row" }, [
      h("span", { class: c.granted ? "ok" : "no", text: (c.granted ? "✓ " : "✕ ") + KIND[c.kind] }),
      " · " + fmtDate(c.created_at) + " " + fmtTime(c.created_at) + " · канал: " + c.channel + " · версия: " + c.text_version,
    ])));
    const visits = h("div", {}, g.bookings.slice(0, 10).map((b) => h("div", { class: "consent-row", text: fmtDate(b.starts_at) + " · " + b.program_name + " · " + b.master_name + " · " + (STATUS[b.status] || b.status) + " · " + b.price_total + " ₽" })));
    drawer.innerHTML = "";
    drawer.append(
      h("button", { type: "button", class: "close", text: "✕", onclick: () => { drawer.hidden = true; } }),
      h("h3", { text: "Гость #" + g.id }), dl,
      h("h3", { text: "Согласия" }), consents.childNodes.length ? consents : h("p", { class: "muted", text: "Нет отметок" }),
      h("h3", { text: "Визиты" }), visits,
      h("div", { class: "actions" }, [
        h("a", { class: "btnlink", href: "api/admin/guests/" + id + "/export", text: "Выгрузить данные (JSON)" }),
        h("button", { type: "button", class: "danger", text: "Удалить данные по запросу", onclick: async () => {
          if (!window.confirm("Удалить персональные данные гостя? Переписка будет удалена, профиль обезличен, будущие записи отменены.")) return;
          await api("api/admin/guests/" + id + "/erase", { method: "POST" });
          drawer.hidden = true; toast("Данные гостя удалены"); loadGuests(); loadPdLog();
        } }),
      ])
    );
    drawer.hidden = false;
  }
  document.getElementById("guestQ").addEventListener("input", () => loadGuests());

  // ---------- маркетинг ----------
  const SPACES = [["turkey", "Турция"], ["himalaya", "Гималаи"], ["india", "Индия"], ["china", "Китай"], ["japan", "Япония"], ["siberia", "Сибирь"], ["relax", "Релакс"]];
  function renderParam(seg) {
    const wrap = document.getElementById("segParam");
    wrap.innerHTML = "";
    if (!seg || !seg.param) return;
    const input = seg.param.type === "space"
      ? h("select", { id: "mkParam" }, SPACES.map(([v, t]) => h("option", { value: v, text: t, selected: v === seg.param.default })))
      : h("input", { id: "mkParam", type: "number", value: seg.param.default });
    input.addEventListener("change", () => { document.getElementById("mkSend").disabled = true; });
    wrap.append(h("label", {}, [seg.param.label, input]));
  }

  async function loadMarketing() {
    const data = await api("api/admin/marketing/segments");
    renderParam(data.segments.find((s) => s.key === state.segment));
    const wrap = document.getElementById("segments");
    wrap.innerHTML = "";
    data.segments.forEach((s) => {
      const el = h("div", { class: "seg" + (s.key === state.segment ? " active" : ""), onclick: () => {
        state.segment = s.key;
        document.getElementById("mkText").value = s.template;
        document.getElementById("mkSend").disabled = true;
        loadMarketing();
      } }, [h("span", { text: s.title }), h("b", { text: s.count })]);
      wrap.append(el);
      if (s.key === state.segment && !document.getElementById("mkText").value) document.getElementById("mkText").value = s.template;
    });
    const hist = document.getElementById("mkHistory");
    hist.innerHTML = "";
    hist.append(h("tr", {}, ["Рассылка", "Сегмент", "Отправлено", "Когда"].map((t) => h("th", { text: t }))));
    data.history.forEach((c) => hist.append(h("tr", {}, [c.name, c.segment, c.sent, c.sent_at ? fmtDate(c.sent_at) + " " + fmtTime(c.sent_at) : "—"].map((t) => h("td", { text: t })))));
  }
  loaders.marketing = loadMarketing;

  const mkBody = () => {
    const param = document.getElementById("mkParam");
    return { segment: state.segment, template: document.getElementById("mkText").value, goal: document.getElementById("mkGoal").value,
      name: "Рассылка: " + state.segment, param: param ? String(param.value) : null, use_ai: document.getElementById("mkAi").checked };
  };
  document.getElementById("mkGen").onclick = async () => {
    const res = await api("api/admin/marketing/generate", { method: "POST", body: Object.assign(mkBody(), { template: "-----" }) });
    document.getElementById("mkText").value = res.template;
    if (!res.ai) toast("Ключ ИИ не задан — подставлен базовый шаблон сегмента");
  };
  document.getElementById("mkPreview").onclick = async () => {
    const res = await api("api/admin/marketing/preview", { method: "POST", body: mkBody() });
    const list = document.getElementById("mkPreviewList");
    list.innerHTML = "";
    if (!res.items.length) list.append(h("p", { class: "muted", text: "В сегменте нет гостей с согласием на рассылку." }));
    res.items.forEach((p) => list.append(h("div", { class: "pv" }, [h("small", { text: p.name + " · " + p.phone }), p.text])));
    state.previewTexts = Object.fromEntries(res.items.map((p) => [p.guest_id, p.text]));
    if (mkBody().use_ai && !res.ai) toast("Ключ ИИ не задан — показан текст по шаблону");
    document.getElementById("mkSend").disabled = !res.items.length;
  };
  document.getElementById("mkSend").onclick = async () => {
    if (!window.confirm("Отправить рассылку гостям сегмента?")) return;
    const res = await api("api/admin/marketing/send", { method: "POST", body: Object.assign(mkBody(), { texts: state.previewTexts || null }) });
    toast("Отправлено: " + res.sent + " из " + res.total);
    document.getElementById("mkSend").disabled = true;
    loadMarketing();
  };

  // ---------- расход ----------
  async function loadStock() {
    const data = await api("api/admin/consumption?day=" + state.day);
    const table = document.getElementById("stockTable");
    table.innerHTML = "";
    table.append(h("tr", {}, ["Позиция", "Категория", "Нужно на " + fmtDate(state.day + "T12:00:00" + OFFSET), "Остаток"].map((t) => h("th", { text: t }))));
    if (!data.items.length) table.append(h("tr", {}, [h("td", { colspan: 4, class: "muted", text: "Предзаказов на этот день нет." })]));
    const CAT = { tea: "чай", bath: "в ванну", extra: "допы" };
    data.items.forEach((i) => table.append(h("tr", {}, [i.name, CAT[i.category], i.qty, i.stock].map((t) => h("td", { text: t })))));
  }
  loaders.stock = loadStock;

  // ---------- живые обновления ----------
  async function loadFeed() {
    const data = await api("api/admin/feed");
    const items = data.items.slice().reverse();
    items.slice(state.seenFeed).forEach((f) => toast(f.text, f.kind));
    state.seenFeed = items.length;
  }

  function connect() {
    const live = document.getElementById("live");
    const es = new EventSource("api/admin/stream");
    es.addEventListener("change", (e) => {
      if (e.data === "grid") loadGrid();
      if (e.data === "escalations") loadEsc();
      if (e.data === "admin_feed") loadFeed();
      if (loaders[e.data] && document.getElementById("tab-" + e.data) && document.getElementById("tab-" + e.data).classList.contains("active")) loaders[e.data]();
    });
    es.onopen = () => { live.textContent = "● онлайн"; live.classList.remove("off"); };
    es.onerror = () => { live.textContent = "● переподключение"; live.classList.add("off"); };
  }

  async function init() {
    const cat = await api("api/admin/catalog");
    state.programs = cat.programs;
    const feed = await api("api/admin/feed");
    state.seenFeed = feed.items.length;
    setDay(todayStr());
    loadEsc();
    connect();
    setInterval(loadGrid, 10000); // страховка: не реже раза в 10 секунд
    setInterval(() => { if (state.grid) renderGrid(); }, 15000); // обратный отсчёт и линия «сейчас»
  }

  window.SPA = { h: h, api: api, toast: toast, fmtDate: fmtDate, fmtTime: fmtTime, loaders: loaders, todayStr: todayStr };
  init();
})();
