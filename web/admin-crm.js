"use strict";
// CRM: аналитика клиентов, список с фильтрами, конструктор рассылок, автоматизации, сертификаты, сотрудники.
(function () {
  const { h, api, toast, fmtDate, fmtTime, loaders } = window.SPA;
  const SVG = "http://www.w3.org/2000/svg";
  const COLORS = { f: "#c8475d", m: "#3f6fb5" };       // проверено валидатором палитры (CVD ΔE 13.8)
  const BAR = "#836c4a";                               // одна серия — одна фирменная краска
  const GENDER = { f: "Женщины", m: "Мужчины" };
  const CHANNEL = { max: "MAX", tg: "Telegram", vk: "ВКонтакте", web: "Сайт", reception: "Ресепшен" };
  const SOURCE = { reception: "Ресепшен", site: "Сайт", social: "Соцсети", qr: "QR-код", ads: "Реклама", referral: "Рекомендации", messenger: "Мессенджер" };
  const rub = (n) => Math.round(n).toLocaleString("ru-RU") + " ₽";
  const pct = (x) => (x * 100).toFixed(1).replace(".0", "") + "%";

  function svg(tag, attrs, children) {
    const el = document.createElementNS(SVG, tag);
    Object.entries(attrs || {}).forEach(([k, v]) => el.setAttribute(k, v));
    (children || []).forEach((c) => el.append(c));
    return el;
  }
  function tip(el, text) { el.append(svg("title", {}, [document.createTextNode(text)])); return el; }

  // Сгруппированные столбцы (женщины/мужчины по возрастным группам), одна ось, скруглённые верхушки, зазор 2px.
  function groupedBars(target, rows, fmt) {
    const W = 640, H = 240, L = 54, B = 26, T = 10;
    const max = Math.max(1, ...rows.flatMap((r) => [r.f, r.m]));
    const chart = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img" });
    for (let i = 0; i <= 4; i++) {
      const y = T + (H - T - B) * (1 - i / 4);
      chart.append(svg("line", { x1: L, x2: W, y1: y, y2: y, stroke: "#eee6da" }));
      chart.append(svg("text", { x: L - 6, y: y + 4, "text-anchor": "end" }, [document.createTextNode(fmt((max * i) / 4))]));
    }
    const gw = (W - L) / rows.length;
    const bw = Math.min(26, gw / 3);
    rows.forEach((r, i) => {
      ["f", "m"].forEach((g, j) => {
        const v = r[g];
        const bh = ((H - T - B) * v) / max;
        const x = L + i * gw + gw / 2 - bw - 1 + j * (bw + 2);
        const y = H - B - bh;
        chart.append(tip(svg("rect", { class: "bar", x, y, width: bw, height: Math.max(bh, 0.5), rx: 4, fill: COLORS[g] }), `${GENDER[g]}, ${r.group}: ${fmt(v)}`));
      });
      chart.append(svg("text", { x: L + i * gw + gw / 2, y: H - 8, "text-anchor": "middle" }, [document.createTextNode(r.group)]));
    });
    target.innerHTML = "";
    target.append(chart, legend());
  }

  function legend() {
    return h("div", { class: "legend-row" }, ["f", "m"].map((g) => h("span", {}, [h("i", { style: "background:" + COLORS[g] }), GENDER[g]])));
  }

  function donut(target, parts) {
    const total = parts.reduce((s, p) => s + p.value, 0) || 1;
    const chart = svg("svg", { viewBox: "0 0 200 200", role: "img", class: "donut" });
    let angle = -Math.PI / 2;
    parts.forEach((p) => {
      const a = (p.value / total) * Math.PI * 2;
      const large = a > Math.PI ? 1 : 0;
      const x1 = 100 + 80 * Math.cos(angle), y1 = 100 + 80 * Math.sin(angle);
      const x2 = 100 + 80 * Math.cos(angle + a), y2 = 100 + 80 * Math.sin(angle + a);
      chart.append(tip(svg("path", { d: `M${x1} ${y1} A80 80 0 ${large} 1 ${x2} ${y2}`, fill: "none", stroke: p.color, "stroke-width": 34 }), `${p.label}: ${p.value} (${pct(p.value / total)})`));
      chart.append(svg("path", { d: `M${x1} ${y1} A80 80 0 0 1 ${x1 + 0.01} ${y1}`, stroke: "#fff", "stroke-width": 36 }));
      angle += a;
    });
    chart.append(svg("text", { x: 100, y: 106, "text-anchor": "middle", style: "font-size:22px;fill:#26272b;font-weight:600" }, [document.createTextNode(String(total))]));
    target.innerHTML = "";
    target.append(chart, h("div", { class: "legend-row" }, parts.map((p) => h("span", {}, [h("i", { style: "background:" + p.color }), p.label + " — " + pct(p.value / total)]))));
  }

  // Горизонтальные полосы одной краской — для категорий (мессенджеры, источники, возраст).
  function hbars(target, items, fmt) {
    const W = 360, rowH = 26, L = 110;
    const max = Math.max(1, ...items.map((i) => i.value));
    const total = items.reduce((s, i) => s + i.value, 0) || 1;
    const chart = svg("svg", { viewBox: `0 0 ${W} ${items.length * rowH + 4}`, role: "img", class: "hbars" });
    items.forEach((it, i) => {
      const y = i * rowH + 4;
      const w = ((W - L - 70) * it.value) / max;
      chart.append(svg("text", { x: L - 8, y: y + 14, "text-anchor": "end" }, [document.createTextNode(it.label)]));
      chart.append(tip(svg("rect", { class: "bar", x: L, y, width: Math.max(w, 1), height: 18, rx: 4, fill: BAR }), `${it.label}: ${it.value}`));
      chart.append(svg("text", { x: L + w + 6, y: y + 14 }, [document.createTextNode(fmt ? fmt(it.value) : `${it.value} · ${pct(it.value / total)}`)]));
    });
    target.innerHTML = "";
    target.append(chart);
  }

  const kpi = (value, label) => h("div", { class: "kpi" }, [h("b", { text: value }), h("span", { text: label })]);

  // ---------- клиенты: период и аналитика ----------
  const cli = { from: "", to: "" };
  const MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"];
  (function periodChips() {
    const wrap = document.getElementById("cliPeriod");
    const now = new Date();
    for (let i = 0; i < 3; i++) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
      const end = new Date(d.getFullYear(), d.getMonth() + 1, 0);
      const iso = (x) => x.toLocaleDateString("sv-SE");
      wrap.append(h("button", { type: "button", class: "chip", "data-from": iso(d), "data-to": iso(end), text: MONTHS[d.getMonth()] }));
    }
    wrap.addEventListener("click", (e) => {
      const chip = e.target.closest(".chip");
      if (!chip) return;
      wrap.querySelectorAll(".chip").forEach((c) => c.classList.toggle("active", c === chip));
      cli.from = chip.dataset.from || "";
      cli.to = chip.dataset.to || "";
      document.getElementById("cliFrom").value = cli.from;
      document.getElementById("cliTo").value = cli.to;
      loadClients();
    });
    document.getElementById("cliApply").onclick = () => {
      cli.from = document.getElementById("cliFrom").value;
      cli.to = document.getElementById("cliTo").value;
      wrap.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
      loadClients();
    };
  })();

  async function loadClients() {
    const q = new URLSearchParams();
    if (cli.from) q.set("date_from", cli.from);
    if (cli.to) q.set("date_to", cli.to);
    const a = await api("api/admin/clients/analytics?" + q.toString());
    document.getElementById("cliKpis").replaceChildren(
      kpi(a.total, "клиентов в программе"), kpi(a.new, "новых за период"),
      kpi(rub(a.effectiveness.revenue_total), "выручка за период"), kpi(a.effectiveness.active, "активных (≥1 визит за период)")
    );
    groupedBars(document.getElementById("chAgeGender"), a.age_gender, (v) => v.toFixed(0) + "%");
    groupedBars(document.getElementById("chRevenue"), a.revenue_age_gender, (v) => (v >= 1000 ? Math.round(v / 1000) + " тыс." : Math.round(v)));
    donut(document.getElementById("chGender"), ["f", "m"].map((g) => ({ label: GENDER[g], value: a.gender[g] || 0, color: COLORS[g] })));
    hbars(document.getElementById("chAge"), a.age_counts.map((r) => ({ label: r.group, value: r.n })));
    hbars(document.getElementById("chChannels"), Object.entries(a.channels).sort((x, y) => y[1] - x[1]).map(([k, v]) => ({ label: CHANNEL[k] || k, value: v })));
    hbars(document.getElementById("chSources"), Object.entries(a.sources).sort((x, y) => y[1] - x[1]).map(([k, v]) => ({ label: SOURCE[k] || k, value: v })));
    const b = a.bonus;
    document.getElementById("cliBonus").replaceChildren(
      kpi(b.accrued.toLocaleString("ru-RU"), "начислено бонусов"), kpi(b.redeemed.toLocaleString("ru-RU"), "списано бонусов"),
      kpi(b.expired.toLocaleString("ru-RU"), "сгорело бонусов"), kpi(pct(b.redeem_rate), "коэффициент погашения"),
      kpi(pct(b.burn_rate), "коэффициент сгорания"), kpi(b.avg_discount_pct.toFixed(1) + "%", "средний процент скидки бонусами")
    );
    document.getElementById("cliRef").replaceChildren(kpi(a.referral.invited, "привлечено новых клиентов"), kpi(rub(a.referral.revenue), "выручка от приглашённых"));
    const e = a.effectiveness;
    document.getElementById("cliEff").replaceChildren(
      kpi(e.participants, "участников"), kpi(e.active, "активных участников"), kpi(e.no_purchases, "клиентов без покупок"),
      kpi(e.regularity.toFixed(1), "регулярность: визитов на активного"), kpi(rub(e.revenue_per_participant), "выручка на участника"),
      kpi(rub(e.revenue_per_active), "выручка на активного (≥1 покупка)")
    );
    if (!document.querySelector("#cliTable tr")) searchClients();
  }

  // ---------- фильтры (общие для клиентов, рассылок и автоматизаций) ----------
  let META = null;
  async function meta() {
    if (!META) META = await api("api/admin/filter-fields");
    return META;
  }

  function filterRow(wrap, value) {
    const f = value || { field: "purchases", op: "gt", value: "" };
    const field = h("select", {}, META.fields.map((x) => h("option", { value: x.key, text: x.label, selected: x.key === f.field })));
    const op = h("select", {}, Object.entries(META.operators).map(([k, t]) => h("option", { value: k, text: t, selected: k === f.op })));
    const val = h("input", { value: f.value || "", placeholder: "значение" });
    const sync = () => { val.hidden = op.value === "filled" || op.value === "empty"; };
    op.addEventListener("change", sync);
    sync();
    const row = h("div", { class: "frow" }, [field, op, val, h("button", { type: "button", text: "✕", onclick: () => row.remove() })]);
    row.getValue = () => ({ field: field.value, op: op.value, value: val.value });
    wrap.append(row);
  }
  const filtersOf = (wrap) => [...wrap.querySelectorAll(".frow")].map((r) => r.getValue());

  async function searchClients() {
    await meta();
    const body = { filters: filtersOf(document.getElementById("cliFilters")), date_from: cli.from || null, date_to: cli.to || null };
    const data = await api("api/admin/clients/search", { method: "POST", body });
    const table = document.getElementById("cliTable");
    table.innerHTML = "";
    document.getElementById("cliCount").textContent = "Найдено: " + data.items.length;
    table.append(h("tr", {}, ["Клиент", "Телефон", "Пол", "Возраст", "Бонусы", "Списано", "Покупок", "Средний чек", "Выручка за период", "Первая", "Последняя", "Источник"].map((t) => h("th", { text: t }))));
    data.items.forEach((c) => table.append(h("tr", { onclick: () => openClient(c.id) }, [
      (c.name || "—") + (c.surname ? " " + c.surname : ""), c.phone, GENDER[c.gender] || "—", c.age ?? "—", c.bonus_balance, c.bonus_spent,
      c.purchases, rub(c.avg_check), rub(c.revenue), c.first_purchase ? fmtDate(c.first_purchase) : "—",
      c.last_purchase ? fmtDate(c.last_purchase) : "—", SOURCE[c.reg_source] || c.reg_source,
    ].map((t) => h("td", { text: t })))));
  }
  // ---------- карточка клиента ----------
  const VST = { confirmed: "запись", completed: "пришёл", no_show: "не пришёл", cancelled: "отменена" };
  const BTX = { accrual: "кешбэк за визит", redeem: "списание", expire: "сгорание", gift: "подарок / начисление", referral: "за друга", adjust: "корректировка" };
  const CKIND = { pd: "Обработка ПДн", rules: "Правила", ads: "Реклама" };

  async function openClient(id) {
    const c = await api("api/admin/clients/" + id);
    const drawer = document.getElementById("drawer");
    drawer.classList.add("wide-drawer");
    const f = {
      name: h("input", { value: c.name || "" }), surname: h("input", { value: c.surname || "" }), phone: h("input", { value: c.phone || "" }),
      gender: h("select", {}, [["", "—"], ["f", "Женщина"], ["m", "Мужчина"]].map(([v, t]) => h("option", { value: v, text: t, selected: (c.gender || "") === v }))),
      birth_date: h("input", { type: "date", value: c.birth_date || "" }),
      card_level: h("select", {}, [["gold", "Золотая (5%)"], ["platinum", "Платиновая (10%)"]].map(([v, t]) => h("option", { value: v, text: t, selected: c.card_level === v }))),
      segments: h("input", { value: c.segments || "", placeholder: "через запятую" }),
      unsubscribed: h("input", { type: "checkbox" }),
    };
    f.unsubscribed.checked = !!c.unsubscribed;
    const save = async () => {
      try {
        await api("api/admin/clients/" + id, { method: "PUT", body: { name: f.name.value, surname: f.surname.value, phone: f.phone.value,
          gender: f.gender.value || null, birth_date: f.birth_date.value || null, card_level: f.card_level.value, segments: f.segments.value, unsubscribed: f.unsubscribed.checked } });
        toast("Карточка сохранена"); openClient(id);
      } catch (err) { toast(err.message, "escalation"); }
    };
    const amount = h("input", { type: "number", min: 1, value: 500, style: "width:110px" });
    const note = h("input", { placeholder: "причина (необязательно)", style: "flex:1" });
    const bonus = async (sign) => {
      try {
        const r = await api("api/admin/guests/" + id + "/bonus", { method: "POST", body: { delta: sign * Math.abs(Number(amount.value)), note: note.value || (sign > 0 ? "начисление администратором" : "списание администратором") } });
        toast((sign > 0 ? "Начислено" : "Списано") + ". Баланс: " + r.balance); openClient(id);
      } catch (err) { toast(err.message, "escalation"); }
    };
    const row = (label, el) => h("label", { class: "crow" }, [h("span", { text: label }), el]);
    const table = (head, rows) => h("table", { class: "table small" }, [h("tr", {}, head.map((x) => h("th", { text: x }))), ...rows.map((r) => h("tr", {}, r.map((x) => h("td", { text: x }))))]);
    drawer.innerHTML = "";
    drawer.append(
      h("button", { type: "button", class: "close", text: "✕", onclick: () => { drawer.hidden = true; drawer.classList.remove("wide-drawer"); } }),
      h("h3", { text: ((c.name || "Гость") + " " + (c.surname || "")).trim() }),
      h("div", { class: "kpis" }, [
        h("div", { class: "kpi" }, [h("b", { text: c.bonus_balance }), h("span", { text: "бонусов" })]),
        h("div", { class: "kpi" }, [h("b", { text: c.purchases }), h("span", { text: "визитов" })]),
        h("div", { class: "kpi" }, [h("b", { text: rub(c.avg_check) }), h("span", { text: "средний чек" })]),
        h("div", { class: "kpi" }, [h("b", { text: c.last_purchase ? fmtDate(c.last_purchase) : "—" }), h("span", { text: "последний визит" })]),
      ]),
      h("h4", { text: "Данные клиента" }),
      h("div", { class: "cgrid" }, [row("Имя", f.name), row("Фамилия", f.surname), row("Телефон", f.phone), row("Пол", f.gender),
        row("Дата рождения", f.birth_date), row("Карта", f.card_level), row("Сегменты", f.segments),
        h("label", { class: "check" }, [f.unsubscribed, "отписан от рассылок"])]),
      h("p", { class: "muted", text: "Источник: " + (SOURCE[c.reg_source] || c.reg_source) + " · мессенджер: " + (CHANNEL[c.reg_channel] || c.reg_channel) + " · промокод: " + (c.referral_code || "—") + " · согласие на рекламу: " + (c.ads_ok ? "есть" : "нет") }),
      h("div", { class: "row-actions" }, [h("button", { type: "button", class: "primary", text: "Сохранить", onclick: save })]),
      h("h4", { text: "Бонусы" }),
      h("div", { class: "row-actions" }, [amount, note, h("button", { type: "button", class: "primary", text: "+ Начислить", onclick: () => bonus(1) }), h("button", { type: "button", class: "danger", text: "− Списать", onclick: () => bonus(-1) })]),
      table(["Когда", "Операция", "Бонусы", "Комментарий"], c.bonus_history.map((b) => [fmtDate(b.created_at), BTX[b.kind] || b.kind, (b.delta > 0 ? "+" : "") + b.delta, b.note + (b.expires_at ? " · до " + fmtDate(b.expires_at) : "")])),
      h("h4", { text: "История визитов" }),
      table(["Дата", "Программа", "Мастер", "Статус", "Оплачено", "Бонусами"], c.visits.map((v) => [fmtDate(v.starts_at) + " " + fmtTime(v.starts_at), v.program_name + (v.preorders ? " · " + v.preorders : ""), v.master_name, VST[v.status] || v.status, rub(v.paid), v.bonus_spent || 0])),
      h("h4", { text: "Согласия" }),
      table(["Когда", "Согласие", "Статус", "Канал"], c.consents.map((x) => [fmtDate(x.created_at), CKIND[x.kind], x.granted ? "дано" : "отозвано", CHANNEL[x.channel] || x.channel])),
      h("h4", { text: "Переписка с ассистентом" }),
      h("div", { class: "history" }, c.messages.slice().reverse().map((m) => h("p", { class: m.role, text: (m.role === "guest" ? "Гость: " : m.role === "admin" ? "Админ: " : "Бот: ") + m.text }))),
      h("div", { class: "actions" }, [h("a", { class: "btnlink", href: "api/admin/guests/" + id + "/export", text: "Выгрузить данные (JSON)" })])
    );
    drawer.hidden = false;
  }

  document.getElementById("cliAddFilter").onclick = async () => { await meta(); filterRow(document.getElementById("cliFilters")); };
  document.getElementById("cliSearch").onclick = searchClients;
  loaders.clients = loadClients;

  // ---------- конструктор рассылок ----------
  const cmpText = document.getElementById("cmpText");
  async function initCampaigns() {
    await meta();
    const vars = document.getElementById("cmpVars");
    if (!vars.childNodes.length) {
      Object.entries(META.variables).forEach(([k, t]) => vars.append(h("button", { type: "button", text: "+ " + t, onclick: () => insertVar(k) })));
    }
    loadCampaignHistory();
  }
  function insertVar(v) {
    const at = cmpText.selectionStart || cmpText.value.length;
    cmpText.value = cmpText.value.slice(0, at) + v + cmpText.value.slice(at);
    cmpText.focus();
  }
  function buttonRow() {
    const type = h("select", {}, [h("option", { value: "reply", text: "Текстовый ответ" }), h("option", { value: "link", text: "Внешняя ссылка" })]);
    const title = h("input", { placeholder: "Название кнопки" });
    const payload = h("select", {}, Object.entries(META.reply_buttons).map(([k, t]) => h("option", { value: k, text: t })));
    const url = h("input", { placeholder: "https://… или tel:+7…", hidden: true });
    type.addEventListener("change", () => { payload.hidden = type.value !== "reply"; url.hidden = type.value !== "link"; });
    const row = h("div", { class: "btnrow" }, [type, title, payload, url, h("button", { type: "button", text: "✕", onclick: () => row.remove() })]);
    row.getValue = () => ({ type: type.value, text: title.value, payload: payload.value, url: url.value });
    document.getElementById("cmpButtons").append(row);
  }
  const cmpBody = () => {
    const when = document.getElementById("cmpWhen").value;
    return {
      name: document.getElementById("cmpName").value || "Рассылка",
      filters: filtersOf(document.getElementById("cmpFilters")),
      template: cmpText.value,
      buttons: [...document.querySelectorAll("#cmpButtons .btnrow")].map((r) => r.getValue()),
      scheduled_at: when ? when + ":00+05:00" : null,
    };
  };
  document.getElementById("cmpAddFilter").onclick = async () => { await meta(); filterRow(document.getElementById("cmpFilters")); };
  document.getElementById("cmpAddBtn").onclick = async () => { await meta(); buttonRow(); };
  document.getElementById("cmpPreview").onclick = async () => {
    const res = await api("api/admin/campaigns/preview", { method: "POST", body: cmpBody() });
    document.getElementById("cmpCount").textContent = "Будет отправлено сообщений: " + res.total;
    const list = document.getElementById("cmpPreviewList");
    list.innerHTML = "";
    res.items.forEach((p) => list.append(h("div", { class: "pv" }, [h("small", { text: p.name + " · " + p.phone }), p.text])));
    document.getElementById("cmpSend").disabled = !res.total;
    document.getElementById("cmpSend").textContent = document.getElementById("cmpWhen").value ? "Запланировать" : "Отправить";
  };
  document.getElementById("cmpSend").onclick = async () => {
    if (!window.confirm("Отправить рассылку выбранным клиентам?")) return;
    await api("api/admin/campaigns", { method: "POST", body: cmpBody() });
    toast(document.getElementById("cmpWhen").value ? "Рассылка запланирована" : "Рассылка отправлена");
    document.getElementById("cmpSend").disabled = true;
    loadCampaignHistory();
  };
  async function loadCampaignHistory() {
    const data = await api("api/admin/campaigns");
    const t = document.getElementById("cmpHistory");
    t.innerHTML = "";
    const ST = { sent: "отправлена", scheduled: "запланирована", draft: "черновик" };
    t.append(h("tr", {}, ["Рассылка", "Статус", "Сообщений", "Когда"].map((x) => h("th", { text: x }))));
    data.items.forEach((c) => t.append(h("tr", {}, [c.name, ST[c.status], c.sent, c.sent_at ? fmtDate(c.sent_at) + " " + fmtTime(c.sent_at) : c.scheduled_at ? "на " + fmtDate(c.scheduled_at) + " " + fmtTime(c.scheduled_at) : "—"].map((x) => h("td", { text: x })))));
  }
  loaders.campaigns = initCampaigns;

  // ---------- автоматизации (окно как в SAMOSALE: Когда · Если · Что сделать) ----------
  const EVENTS = {
    birthday_before: { pre: "За", post: "До", label: "Дня рождения клиента" },
    after_visit: { pre: "Через", post: "После", label: "Последнего визита" },
    inactive: { pre: "Через", post: "После", label: "Последнего визита, если гость не вернулся" },
    registration: { pre: "Через", post: "После", label: "Регистрации" },
  };
  const DO = [["bonus", "Начислить бонусы"], ["segment_add", "Добавить в сегмент"], ["segment_remove", "Удалить из сегмента"],
    ["message", "Отправить сообщение"], ["chain", "Запустить цепочку сообщений"], ["staff_message", "Отправить сообщение сотруднику"]];

  function whenText(a) {
    const ev = EVENTS[a.trigger];
    return ev.pre + " " + a.days + " дн. " + ev.post.toLowerCase() + " " + ev.label.toLowerCase();
  }

  async function loadAutos() {
    await meta();
    const data = await api("api/admin/automations");
    const list = document.getElementById("autoList");
    list.innerHTML = "";
    data.items.forEach((a) => {
      const acts = (a.actions && a.actions.length ? a.actions : [a.action]).map((k) => (DO.find((d) => d[0] === k) || [k, k])[1]);
      list.append(h("div", { class: "card" + (a.active ? "" : " inactive") }, [
        h("div", { class: "head" }, [h("div", { class: "reason", text: a.name }), h("span", { class: "pill " + (a.active ? "accepted" : ""), text: a.active ? "включена" : "выключена" })]),
        h("p", { class: "muted", text: whenText(a) }),
        h("p", { text: "Что сделать: " + acts.join(", ") + (a.bonus_amount && acts.includes("Начислить бонусы") ? " · " + a.bonus_amount + " бонусов на " + a.bonus_days + " дн." : "") }),
        h("div", { class: "row-actions" }, [h("button", { type: "button", text: "Изменить", onclick: () => editAuto(a) }), h("span", { class: "muted", text: "срабатываний: " + a.runs })]),
      ]));
    });
  }

  function toggle(label, on, extra) {
    const input = h("input", { type: "checkbox" });
    input.checked = on;
    const extraBox = h("div", { class: "do-extra" }, extra || []);
    const sync = () => { extraBox.hidden = !input.checked; };
    input.addEventListener("change", sync);
    sync();
    return { input, row: h("div", { class: "do-row" }, [h("label", { class: "switch" }, [input, h("span", { class: "slider" })]), h("span", { text: label }), extraBox]) };
  }

  function editAuto(a) {
    const modal = document.getElementById("modal");
    const box = document.getElementById("modalBox");
    box.classList.add("wide-modal");
    const name = h("input", { value: a.name || "", class: "full" });
    const pre = h("span", { class: "fixed" });
    const post = h("span", { class: "fixed" });
    const days = h("input", { type: "number", value: a.days ?? 7, min: 0, max: 365, style: "width:90px" });
    const event = h("select", {}, Object.entries(EVENTS).map(([k, e]) => h("option", { value: k, text: e.label, selected: k === a.trigger })));
    const syncWhen = () => { pre.textContent = EVENTS[event.value].pre; post.textContent = EVENTS[event.value].post; };
    event.addEventListener("change", syncWhen);
    syncWhen();
    const match = h("select", {}, [h("option", { value: "all", text: "все условия", selected: a.match !== "any" }), h("option", { value: "any", text: "любое условие", selected: a.match === "any" })]);
    const filters = h("div", { class: "filters" });
    (a.filters || []).forEach((f) => filterRow(filters, f));
    const matched = h("span", { class: "muted" });
    const apply = async () => {
      const res = await api("api/admin/clients/search", { method: "POST", body: { filters: filtersOf(filters), match: match.value } });
      matched.textContent = "Подходит клиентов: " + res.items.length + (res.items.length === 300 ? "+" : "");
    };
    const acts = new Set(a.actions && a.actions.length ? a.actions : [a.action].filter(Boolean));
    const amount = h("input", { type: "number", value: a.bonus_amount || 500, style: "width:100px" });
    const bdays = h("input", { type: "number", value: a.bonus_days || 14, style: "width:80px" });
    const segment = h("input", { value: a.segment || "", placeholder: "название сегмента" });
    const segment2 = h("input", { value: a.segment || "", placeholder: "название сегмента" });
    const message = h("textarea", { rows: 3 });
    message.value = a.message || "";
    const staffMsg = h("textarea", { rows: 2, placeholder: "Например: позвонить гостю {name}, предложить программу" });
    staffMsg.value = a.staff_message || "";
    const t = {
      bonus: toggle("Начислить бонусы", acts.has("bonus"), [amount, " бонусов на ", bdays, " дней"]),
      segment_add: toggle("Добавить в сегмент", acts.has("segment_add"), [segment]),
      segment_remove: toggle("Удалить из сегмента", acts.has("segment_remove"), [segment2]),
      message: toggle("Отправить сообщение", acts.has("message"), [message, h("div", { class: "muted", text: "Переменные: {name}, {bonuses}, {referral_link}. Только гостям с согласием на рекламу." })]),
      chain: toggle("Запустить цепочку сообщений (скоро)", false, []),
      staff_message: toggle("Отправить сообщение сотруднику", acts.has("staff_message"), [staffMsg]),
    };
    t.chain.input.disabled = true;
    const active = h("input", { type: "checkbox" });
    active.checked = a.active !== false;
    const save = async () => {
      const body = {
        name: name.value, trigger: event.value, days: Number(days.value), match: match.value, filters: filtersOf(filters),
        actions: Object.entries(t).filter(([k, v]) => k !== "chain" && v.input.checked).map(([k]) => k),
        bonus_amount: Number(amount.value), bonus_days: Number(bdays.value), segment: (t.segment_remove.input.checked && !t.segment_add.input.checked ? segment2 : segment).value,
        message: message.value, staff_message: staffMsg.value, active: active.checked,
      };
      try {
        if (a.id) await api("api/admin/automations/" + a.id, { method: "PUT", body });
        else await api("api/admin/automations", { method: "POST", body });
        modal.hidden = true; box.classList.remove("wide-modal"); toast("Автоматизация сохранена"); loadAutos();
      } catch (err) { toast("Не сохранено: " + err.message, "escalation"); }
    };
    box.innerHTML = "";
    box.append(
      h("div", { class: "modal-head" }, [h("h3", { text: a.name || "Новая автоматизация" }), h("button", { type: "button", class: "close", text: "✕", onclick: () => { modal.hidden = true; box.classList.remove("wide-modal"); } })]),
      h("div", { class: "form-grid" }, [
        h("b", { text: "Название:" }), name,
        h("b", { text: "Когда:" }), h("div", { class: "inline" }, [pre, days, h("span", { class: "fixed", text: "дней" }), post, event]),
        h("b", { text: "Если:" }), h("div", { class: "if-box" }, [
          h("div", { class: "inline" }, [match, h("button", { type: "button", text: "Применить", onclick: apply }), h("button", { type: "button", text: "Сбросить", onclick: () => { filters.innerHTML = ""; matched.textContent = ""; } }), matched]),
          filters, h("button", { type: "button", text: "добавить условие", onclick: () => filterRow(filters) }),
        ]),
        h("b", { text: "Что сделать:" }), h("div", {}, Object.values(t).map((x) => x.row)),
        h("b", { text: "" }), h("label", { class: "check" }, [active, "автоматизация включена"]),
      ]),
      h("div", { class: "row-actions" }, [h("button", { type: "button", class: "primary", text: "Сохранить", onclick: save })])
    );
    modal.hidden = false;
  }
  document.getElementById("autoNew").onclick = async () => {
    await meta();
    editAuto({ id: null, name: "500 бонусов на день рождения на 14 дней", trigger: "birthday_before", days: 7, actions: ["bonus", "message"], bonus_amount: 500, bonus_days: 14, segment: "", message: "{name}, скоро ваш день рождения! Дарим 500 бонусов на 14 дней.", filters: [], match: "all", active: true });
  };
  document.getElementById("autoRun").onclick = async () => {
    const r = await api("api/admin/automations/run", { method: "POST" });
    toast("Выполнено действий: " + r.done);
    loadAutos();
  };
  loaders.autos = loadAutos;

  // ---------- сертификаты ----------
  const CST = { active: "действует", used: "использован", expired: "истёк", cancelled: "аннулирован" };
  const OPS = { sale: "продажа", redeem: "погашение", refund: "возврат", cancel: "аннулирование" };
  async function loadCerts() {
    const data = await api("api/admin/certificates");
    const t = data.totals;
    document.getElementById("certKpis").replaceChildren(kpi(rub(t.sold), "продано (приход)"), kpi(rub(t.redeemed), "погашено (расход)"), kpi(rub(t.outstanding), "остаток на действующих"), kpi(t.active, "действующих сертификатов"));
    const table = document.getElementById("certTable");
    table.innerHTML = "";
    table.append(h("tr", {}, ["Номер", "Номинал", "Остаток", "Статус", "До"].map((x) => h("th", { text: x }))));
    data.items.forEach((c) => table.append(h("tr", { onclick: () => showCert(c.number) }, [c.number + (c.program_name ? " · " + c.program_name : ""), rub(c.amount), rub(c.balance), CST[c.status], fmtDate(c.expires_at + "T12:00:00+05:00")].map((x) => h("td", { text: x })))));
  }
  async function showCert(number) {
    document.getElementById("certNumber").value = number;
    const box = document.getElementById("certCard");
    try {
      const c = await api("api/admin/certificates/" + encodeURIComponent(number));
      const amount = h("input", { type: "number", value: c.balance, min: 1, max: c.balance, style: "width:120px" });
      const bookingId = h("input", { type: "number", placeholder: "№ брони (необяз.)", style: "width:150px" });
      box.replaceChildren(h("div", { class: "cert-card" }, [
        h("div", { class: "muted", text: c.number + " · " + (c.program_name || "номинальный") + " · " + CST[c.status] }),
        h("div", { class: "big", text: rub(c.balance) + " из " + rub(c.amount) }),
        h("div", { class: "muted", text: "Действует до " + fmtDate(c.expires_at + "T12:00:00+05:00") + (c.owner_name ? " · кому: " + c.owner_name : "") + (c.buyer_name ? " · купил: " + c.buyer_name : "") }),
        c.status === "active" ? h("div", { class: "row-actions" }, ["Погасить:", amount, "₽", bookingId, h("button", { type: "button", class: "primary", text: "Списать", onclick: async () => {
          try {
            await api("api/admin/certificates/" + encodeURIComponent(c.number) + "/redeem", { method: "POST", body: { amount: Number(amount.value), booking_id: bookingId.value ? Number(bookingId.value) : null } });
            toast("Списано " + rub(Number(amount.value)));
            showCert(c.number); loadCerts();
          } catch (err) { toast(err.message, "escalation"); }
        } })]) : "",
        h("h3", { text: "Движения" }),
        ...c.ops.map((o) => h("div", { class: "consent-row", text: fmtDate(o.created_at) + " · " + OPS[o.kind] + " · " + rub(Math.abs(o.amount)) + (o.booking_id ? " · бронь №" + o.booking_id : "") + (o.actor ? " · " + o.actor : "") })),
      ]));
    } catch (err) { box.replaceChildren(h("div", { class: "cert-card error", text: err.message })); }
  }
  document.getElementById("certCheck").onclick = () => showCert(document.getElementById("certNumber").value);
  document.getElementById("cnIssue").onclick = async () => {
    const v = (id) => document.getElementById(id).value;
    try {
      await api("api/admin/certificates", { method: "POST", body: { number: v("cnNumber"), amount: Number(v("cnAmount")), kind: v("cnProgram") ? "program" : "nominal", program_name: v("cnProgram") || null, buyer_name: v("cnBuyer"), buyer_phone: v("cnPhone"), owner_name: v("cnOwner"), valid_days: Number(v("cnDays")) } });
      toast("Сертификат оформлен");
      loadCerts(); showCert(v("cnNumber"));
    } catch (err) { toast(err.message, "escalation"); }
  };
  loaders.certs = loadCerts;

  // ---------- сотрудники ----------
  async function loadEmployees() {
    const data = await api("api/admin/employees");
    const t = document.getElementById("empTable");
    t.innerHTML = "";
    t.append(h("tr", {}, ["Сотрудник", "Должность", "Телефон", "Логин", "Статус", ""].map((x) => h("th", { text: x }))));
    data.items.forEach((e) => t.append(h("tr", {}, [
      h("td", { text: e.name + (e.skills ? " · " + e.skills : "") }), h("td", { text: data.positions[e.position] }), h("td", { text: e.phone || "—" }),
      h("td", { text: e.login || "—" }), h("td", { text: e.active ? "работает" : "отключён" }),
      h("td", {}, [h("button", { type: "button", text: "Изменить", onclick: () => editEmployee(e, data.positions) })]),
    ])));
  }
  function editEmployee(e, positions) {
    const modal = document.getElementById("modal");
    const box = document.getElementById("modalBox");
    const name = h("input", { value: e.name || "" });
    const position = h("select", {}, Object.entries(positions).map(([k, t]) => h("option", { value: k, text: t, selected: k === e.position })));
    const skills = h("input", { value: e.skills || "", placeholder: "для мастера: массаж, хаммам…" });
    const phone = h("input", { value: e.phone || "" });
    const login = h("input", { value: e.login || "", placeholder: "латиницей" });
    const pin = h("input", { placeholder: e.id ? "оставьте пустым, чтобы не менять" : "4–6 цифр", inputmode: "numeric" });
    const active = h("input", { type: "checkbox" });
    active.checked = e.active !== false;
    box.innerHTML = "";
    box.append(h("h3", { text: e.id ? "Сотрудник" : "Новый сотрудник" }),
      h("label", {}, ["Имя", name]), h("label", {}, ["Должность", position]), h("label", {}, ["Навыки (для мастера)", skills]),
      h("label", {}, ["Телефон", phone]), h("label", {}, ["Логин для входа", login]), h("label", {}, ["PIN-код", pin]),
      h("label", { class: "check" }, [active, "работает"]),
      h("div", { class: "row-actions" }, [
        h("button", { type: "button", class: "primary", text: "Сохранить", onclick: async () => {
          const body = { name: name.value, position: position.value, skills: skills.value, phone: phone.value || null, login: login.value || null, pin: pin.value || null, active: active.checked };
          try {
            if (e.id) await api("api/admin/employees/" + e.id, { method: "PUT", body });
            else await api("api/admin/employees", { method: "POST", body });
            modal.hidden = true; toast("Сохранено"); loadEmployees();
          } catch (err) { toast(err.message, "escalation"); }
        } }),
        h("button", { type: "button", text: "Отмена", onclick: () => { modal.hidden = true; } }),
      ]));
    modal.hidden = false;
  }
  document.getElementById("empNew").onclick = async () => { const d = await api("api/admin/employees"); editEmployee({ position: "master", active: true }, d.positions); };
  loaders.employees = loadEmployees;

  // ---------- права: скрыть недоступные разделы ----------
  api("api/admin/me").then((me) => {
    if (!me.tabs) return;
    document.querySelectorAll(".tabs button[data-tab]").forEach((b) => { b.hidden = !me.tabs.includes(b.dataset.tab); });
    document.querySelectorAll(".tab-group").forEach((g) => { g.hidden = true; });
    const first = document.querySelector(".tabs button[data-tab]:not([hidden])");
    if (first) first.click();
  });
})();
