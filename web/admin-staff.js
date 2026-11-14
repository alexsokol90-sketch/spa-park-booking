"use strict";
// Вкладки «График мастеров» и «Чек-листы». Общие помощники — из admin.js (window.SPA).
(function () {
  const { h, api, toast, fmtDate, fmtTime, loaders, todayStr } = window.SPA;
  const OFFSET = "+05:00";
  const WD = ["вс", "пн", "вт", "ср", "чт", "пт", "сб"];
  const sch = { start: todayStr(), data: null };

  function addDays(iso, n) {
    const d = new Date(iso + "T12:00:00" + OFFSET);
    d.setDate(d.getDate() + n);
    return d.toLocaleDateString("sv-SE", { timeZone: "Asia/Yekaterinburg" });
  }

  function dayLabel(iso) {
    const d = new Date(iso + "T12:00:00" + OFFSET);
    return { wd: WD[d.getDay()], dm: d.getDate() + "." + String(d.getMonth() + 1).padStart(2, "0"), weekend: d.getDay() === 0 || d.getDay() === 6 };
  }

  // ---------- график ----------
  async function loadSchedule() {
    sch.data = await api("api/admin/schedule?start=" + sch.start + "&days=14");
    renderSchedule();
    fillPatternMasters();
  }

  function renderSchedule() {
    const { days, masters, shifts, load } = sch.data;
    const byKey = Object.fromEntries(shifts.map((s) => [s.master_id + "|" + s.day, s]));
    const loadKey = Object.fromEntries(load.map((l) => [l.master_id + "|" + l.day, l.n]));
    const today = todayStr();
    const table = document.getElementById("schTable");
    table.innerHTML = "";
    const head = h("tr", {}, [h("th", { text: "Мастер" })]);
    days.forEach((d) => {
      const l = dayLabel(d);
      head.append(h("th", { class: (l.weekend ? "weekend " : "") + (d === today ? "today" : "") }, [l.wd, h("br"), l.dm]));
    });
    table.append(head);
    masters.forEach((m) => {
      const row = h("tr", {}, [h("td", {}, [h("b", { text: m.name }), h("br"), h("small", { class: "muted", text: m.skills })])]);
      days.forEach((d) => {
        const s = byKey[m.id + "|" + d];
        const n = loadKey[m.id + "|" + d];
        const cell = s
          ? h("div", { class: "shift on" }, [s.start + "–" + s.end, h("small", { text: n ? n + " зап." : "свободен" })])
          : h("div", { class: "shift off" }, ["выходной", n ? h("small", { text: "⚠ " + n + " зап." }) : ""]);
        cell.addEventListener("click", () => editShift(m, d, s));
        row.append(h("td", { class: d === today ? "today" : "" }, [cell]));
      });
      table.append(row);
    });
  }

  function editShift(master, day, shift) {
    const modal = document.getElementById("modal");
    const box = document.getElementById("modalBox");
    const start = h("input", { type: "time", value: shift ? shift.start : "10:00" });
    const end = h("input", { type: "time", value: shift ? (shift.end === "24:00" ? "23:59" : shift.end) : "22:00" });
    const note = h("p", { class: "muted", text: "Конец 23:59 — смена до закрытия (24:00)." });
    const save = async (off) => {
      const endVal = end.value === "23:59" ? "24:00" : end.value;
      const res = await api("api/admin/schedule", { method: "PUT", body: { master_id: master.id, day: day, start: off ? null : start.value, end: off ? null : endVal } });
      modal.hidden = true;
      if (res.conflicts.length) {
        toast("Внимание: " + res.conflicts.length + " запис. мастера вне смены — перенесите их:\n" + res.conflicts.map((c) => fmtTime(c.starts_at) + " " + c.program_name + " (" + (c.guest_name || "гость") + ")").join("\n"), "escalation");
      } else {
        toast("График обновлён — ассистент уже видит изменения");
      }
      loadSchedule();
    };
    box.innerHTML = "";
    box.append(
      h("h3", { text: master.name + " · " + fmtDate(day + "T12:00:00" + OFFSET) }),
      h("label", {}, ["Начало смены", start]),
      h("label", {}, ["Конец смены", end]),
      note,
      h("div", { class: "row-actions" }, [
        h("button", { type: "button", class: "primary", text: "Сохранить смену", onclick: () => save(false) }),
        h("button", { type: "button", class: "danger", text: "Выходной", onclick: () => save(true) }),
        h("button", { type: "button", text: "Отмена", onclick: () => { modal.hidden = true; } }),
      ])
    );
    modal.hidden = false;
  }

  function fillPatternMasters() {
    const sel = document.getElementById("patMaster");
    if (sel.options.length) return;
    sch.data.masters.forEach((m) => sel.append(h("option", { value: m.id, text: m.name })));
    document.getElementById("patFrom").value = todayStr();
  }

  document.getElementById("patApply").addEventListener("click", async () => {
    const endVal = document.getElementById("patEnd").value;
    const body = {
      master_id: Number(document.getElementById("patMaster").value),
      first_day: document.getElementById("patFrom").value,
      days: Number(document.getElementById("patDays").value),
      pattern: document.getElementById("patType").value,
      start: document.getElementById("patStart").value,
      end: endVal === "23:59" || endVal === "00:00" ? "24:00" : endVal,
    };
    const res = await api("api/admin/schedule/pattern", { method: "POST", body: body });
    toast("Заполнено дней: " + res.changed);
    loadSchedule();
  });
  document.getElementById("schPrev").onclick = () => { sch.start = addDays(sch.start, -7); loadSchedule(); };
  document.getElementById("schNext").onclick = () => { sch.start = addDays(sch.start, 7); loadSchedule(); };
  document.getElementById("schToday").onclick = () => { sch.start = todayStr(); loadSchedule(); };
  loaders.schedule = loadSchedule;

  // ---------- чек-листы ----------
  const ROLE = { admin: "администратор", master: "мастер", cleaning: "клининг" };
  const KIND = { opening: "Каждый день — открытие", daily: "Каждый день", space: "Перед каждой бронью", cleanup: "После каждой брони (уборка)", closing: "Каждый день — закрытие" };
  const cl = { role: "" };
  const clDay = document.getElementById("clDay");
  const clWho = document.getElementById("clWho");
  clDay.value = todayStr();
  clWho.value = localStorage.getItem("spa_who") || "";
  clWho.addEventListener("change", () => localStorage.setItem("spa_who", clWho.value));
  clDay.addEventListener("change", () => loadChecklists());
  document.getElementById("clRoles").addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (!chip) return;
    cl.role = chip.dataset.role;
    document.querySelectorAll("#clRoles .chip").forEach((c) => c.classList.toggle("active", c === chip));
    loadChecklists();
  });

  async function loadChecklists() {
    const data = await api("api/admin/checklists?day=" + clDay.value + (cl.role ? "&role=" + cl.role : ""));
    const list = document.getElementById("clList");
    list.innerHTML = "";
    const complete = data.items.filter((r) => r.completed_at).length;
    document.getElementById("clSummary").textContent = "Выполнено: " + complete + " из " + data.items.length;
    if (!data.items.length) list.append(h("p", { class: "muted", text: "На этот день чек-листов нет." }));
    data.items.forEach((run) => list.append(checklistCard(run)));
  }

  function runTime(run) {
    if (run.kind === "cleanup" && run.ends_at) return "уборка " + fmtTime(run.ends_at) + "–" + fmtTime(run.busy_until);
    if (run.kind === "space" && run.starts_at) return "до " + fmtTime(run.starts_at);
    return KIND[run.kind] || "";
  }

  function checklistCard(run) {
    const doneCount = Object.keys(run.done).length;
    const pct = Math.round((doneCount / run.items.length) * 100);
    const items = run.items.map((text, i) => {
      const mark = run.done[String(i)];
      const box = h("input", { type: "checkbox" });
      box.checked = Boolean(mark);
      const label = h("div", { class: "cl-item" + (mark ? " done" : "") }, [
        box,
        h("span", {}, [text, mark ? h("small", { text: mark.by + " · " + fmtTime(mark.at) }) : ""]),
      ]);
      label.addEventListener("click", async (e) => {
        e.preventDefault();
        await api("api/admin/checklists/" + run.id + "/toggle", { method: "POST", body: { index: i, who: clWho.value || ROLE[run.role] } });
        loadChecklists();
      });
      return label;
    });
    return h("div", { class: "card" + (run.completed_at ? " complete" : "") }, [
      h("div", { class: "head" }, [
        h("div", {}, [h("div", { class: "reason" }, [run.title, h("span", { class: "role-tag " + run.role, text: ROLE[run.role] })]), h("div", { class: "cl-time", text: runTime(run) })]),
        h("span", { class: "pill " + (run.completed_at ? "accepted" : "new"), text: run.completed_at ? "готово" : doneCount + "/" + run.items.length }),
      ]),
      h("div", { class: "progress" }, [h("div", { style: "width:" + pct + "%" })]),
      ...items,
    ]);
  }
  loaders.checklists = () => (document.getElementById("clEditor").hidden ? loadChecklists() : loadTemplates());

  // ---------- редактор шаблонов ----------
  document.getElementById("clEditToggle").addEventListener("click", (e) => {
    const editor = document.getElementById("clEditor");
    editor.hidden = !editor.hidden;
    document.getElementById("clList").hidden = !editor.hidden;
    e.target.textContent = editor.hidden ? "Редактировать шаблоны" : "← К чек-листам дня";
    if (editor.hidden) loadChecklists(); else loadTemplates();
  });
  document.getElementById("tplNew").addEventListener("click", () => {
    document.getElementById("tplList").prepend(templateCard({ id: null, title: "", role: cl.role || "admin", kind: "daily", items: [""], active: true }));
  });

  async function loadTemplates() {
    const data = await api("api/admin/checklist-templates");
    const list = document.getElementById("tplList");
    list.innerHTML = "";
    data.items.filter((t) => !cl.role || t.role === cl.role).forEach((t) => list.append(templateCard(t)));
  }

  function select(options, value) {
    return h("select", {}, Object.entries(options).map(([v, t]) => h("option", { value: v, text: t, selected: v === value })));
  }

  function itemRow(text, wrap) {
    const input = h("input", { value: text, placeholder: "Пункт чек-листа" });
    const row = h("div", { class: "tpl-item" }, [input]);
    const move = (dir) => {
      const sib = dir < 0 ? row.previousElementSibling : row.nextElementSibling;
      if (!sib) return;
      if (dir < 0) wrap.insertBefore(row, sib);
      else wrap.insertBefore(sib, row);
    };
    row.append(
      h("button", { type: "button", title: "Выше", text: "↑", onclick: () => move(-1) }),
      h("button", { type: "button", title: "Ниже", text: "↓", onclick: () => move(1) }),
      h("button", { type: "button", title: "Удалить пункт", text: "✕", onclick: () => row.remove() })
    );
    return row;
  }

  function templateCard(tpl) {
    const title = h("input", { class: "title", value: tpl.title, placeholder: "Название чек-листа" });
    const role = select(ROLE, tpl.role);
    const kind = select(KIND, tpl.kind === "custom" ? "daily" : tpl.kind);
    const wrap = h("div", {});
    tpl.items.forEach((t) => wrap.append(itemRow(t, wrap)));
    const save = async (active) => {
      const body = { title: title.value, role: role.value, kind: kind.value, active: active, items: [...wrap.querySelectorAll("input")].map((i) => i.value).filter((v) => v.trim()) };
      try {
        if (tpl.id) await api("api/admin/checklist-templates/" + tpl.id, { method: "PUT", body: body });
        else await api("api/admin/checklist-templates", { method: "POST", body: body });
        toast(active ? "Чек-лист сохранён" : "Чек-лист отключён");
        loadTemplates();
      } catch (err) { toast("Не сохранено: " + err.message, "escalation"); }
    };
    return h("div", { class: "card tpl" + (tpl.active ? "" : " inactive") }, [
      title,
      h("div", { class: "meta" }, [role, kind]),
      wrap,
      h("div", { class: "row-actions" }, [
        h("button", { type: "button", text: "+ пункт", onclick: () => wrap.append(itemRow("", wrap)) }),
        h("button", { type: "button", class: "primary", text: "Сохранить", onclick: () => save(true) }),
        tpl.id ? h("button", { type: "button", class: tpl.active ? "danger" : "", text: tpl.active ? "Отключить" : "Включить", onclick: () => save(!tpl.active) }) : "",
      ]),
    ]);
  }
})();
