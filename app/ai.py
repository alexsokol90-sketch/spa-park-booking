"""ИИ-ассистент на Claude с инструментами поверх движка брони.

Модель не придумывает окна и цены: всё берётся из инструментов. Окно показывается гостю только
после захвата в БД, а бронь подтверждается кнопкой — молча принятых заявок не бывает.
Без ключа API работает разбор текста по правилам (nlu.py).
"""
import logging
import re
from datetime import date, datetime

import anthropic

from . import config, db, kb
from .notify import Out
from .texts import fmt_when

log = logging.getLogger("ai")
_client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY) if config.ANTHROPIC_API_KEY else None
MAX_STEPS = 5

TOOLS = [
    {
        "name": "find_slots",
        "description": "Реальные свободные окна для программы на дату. Гостю покажутся кнопки с временем.",
        "input_schema": {
            "type": "object",
            "properties": {
                "program_id": {"type": "integer"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "time": {"type": "string", "description": "Желаемое время HH:MM, если гость его назвал"},
            },
            "required": ["program_id", "date"],
        },
    },
    {
        "name": "hold_slot",
        "description": "Захватить окно на 15 минут, когда гость явно выбрал программу, дату и время. Подтверждение брони гость делает кнопкой.",
        "input_schema": {
            "type": "object",
            "properties": {
                "program_id": {"type": "integer"},
                "start": {"type": "string", "description": "YYYY-MM-DDTHH:MM, местное время"},
            },
            "required": ["program_id", "start"],
        },
    },
    {
        "name": "show_programs",
        "description": "Показать гостю кнопки программ пространства или карточку программы.",
        "input_schema": {
            "type": "object",
            "properties": {"space_id": {"type": "integer"}, "program_id": {"type": "integer"}},
        },
    },
    {
        "name": "my_bookings",
        "description": "Показать гостю его предстоящие записи с кнопками переноса и отмены.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "escalate",
        "description": (
            "Передать диалог администратору. Причины: asked_admin, out_of_kb, complaint, group, health. "
            "Обязательно при жалобе, возврате денег, группах, сомнениях о здоровье, вопросах вне базы знаний."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string"}, "details": {"type": "string"}},
            "required": ["reason", "details"],
        },
    },
]


def enabled() -> bool:
    return _client is not None


async def _catalog_text() -> str:
    rows = await db.query(
        """SELECT p.id, p.name, p.duration_min, p.price, p.max_guests, p.description, s.id AS sid, s.name AS space
           FROM programs p JOIN spaces s ON s.id = p.space_id WHERE p.active ORDER BY s.sort, p.price"""
    )
    return "\n".join(
        f"#{r['id']} [{r['space']} sid={r['sid']}] {r['name']} — {r['duration_min']} мин, {r['price']} ₽, "
        f"до {r['max_guests']} гостей. {r['description']}"
        for r in rows
    )


async def system_prompt(ctx) -> str:
    now = datetime.now(config.TZ)
    lang = "английском" if ctx.lang == "en" else "русском"
    return f"""Ты — ассистент спа-центра «СПА-парк» в Нижневартовске в мессенджере MAX.
Сейчас {now:%Y-%m-%d %H:%M}, {fmt_when(now, 'ru')}. Гость: {ctx.guest.get('name') or 'имя неизвестно'}.
Отвечай на {lang} языке. Тон: спокойный, премиальный, на «вы», по имени, без канцелярита, давления и обилия эмодзи. Коротко: 1–4 предложения.

Правила:
- Называй только программы, цены и условия из каталога и базы знаний ниже. Скидок и акций не придумывай.
- Не обещай свободное окно сам: используй find_slots, а при выборе гостем времени — hold_slot.
- Никогда не пиши, что гость записан: бронь подтверждается только кнопкой «Подтвердить».
- Не давай медицинских рекомендаций и не решай, можно ли гостю процедуру. При сомнениях о здоровье — escalate(health).
- Жалоба, негатив, возврат денег — сразу escalate(complaint). Группы, корпоративы, девичники — escalate(group) с пожеланиями, сам не бронируй.
- Вопрос вне базы знаний — escalate(out_of_kb). Не спорь и не оправдывайся пространно.
- Для английского используй глоссарий терминов.
- «Релакс» — отдельное пространство без прогрева (локальный массаж и лицо).

Каталог программ:
{await _catalog_text()}

База знаний:
{kb.knowledge_text()}
"""


async def _run_tool(ctx, name: str, args: dict) -> str:
    from . import dialog  # локальный импорт: dialog зависит от ai

    if name == "find_slots":
        around = None
        day = date.fromisoformat(args["date"])
        if args.get("time"):
            hour, minute = (int(x) for x in args["time"].split(":"))
            around = datetime.combine(day, datetime.min.time(), tzinfo=config.TZ).replace(hour=hour, minute=minute)
        await dialog.show_slots(ctx, int(args["program_id"]), day, around=around)
        return "Гостю показаны кнопки свободного времени (или другие дни, если этот занят)."
    if name == "hold_slot":
        start = datetime.fromisoformat(args["start"]).replace(tzinfo=config.TZ)
        await dialog.try_hold(ctx, int(args["program_id"]), start, None)
        return "Результат захвата показан гостю (закреплено с кнопкой подтверждения либо предложены альтернативы)."
    if name == "show_programs":
        if args.get("program_id"):
            await dialog.p_prog(ctx, str(args["program_id"]))
        elif args.get("space_id"):
            await dialog.p_space(ctx, str(args["space_id"]))
        else:
            await dialog.p_book(ctx, "")
        return "Показано."
    if name == "my_bookings":
        await dialog.p_my(ctx, "")
        return "Показано."
    if name == "escalate":
        await dialog.escalate(ctx, args.get("reason", "out_of_kb"), args.get("details", ""), silent=True)
        return "Передано администратору. Сообщи гостю, что администратор свяжется (ночью — с 10:00)."
    return "Неизвестный инструмент"


PHONE_MASK = re.compile(r"\+?\d[\d\s\-()]{8,}\d")


def mask_pd(text: str) -> str:
    """В модель не уходят телефоны: персональные данные остаются в нашей БД."""
    return PHONE_MASK.sub("[телефон]", text)


async def _history(ctx, text: str) -> list[dict]:
    rows = await db.query(
        "SELECT role, text FROM messages WHERE guest_id = %s ORDER BY id DESC LIMIT 12", (ctx.gid,)
    )
    msgs = []
    for row in reversed(rows[1:]):
        role = "user" if row["role"] == "guest" else "assistant"
        if msgs and msgs[-1]["role"] == role:
            msgs[-1]["content"] += "\n" + mask_pd(row["text"])
        else:
            msgs.append({"role": role, "content": mask_pd(row["text"])})
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    if msgs and msgs[-1]["role"] == "user":
        msgs[-1]["content"] += "\n" + mask_pd(text)
    else:
        msgs.append({"role": "user", "content": mask_pd(text)})
    return msgs


async def agent_reply(ctx, text: str) -> bool:
    """Ответ модели с вызовом инструментов. False — модель недоступна, нужен запасной путь."""
    messages = await _history(ctx, text)
    system = await system_prompt(ctx)
    ui_before = len(ctx.out)
    final_text = ""
    try:
        for _ in range(MAX_STEPS):
            msg = await _client.messages.create(
                model=config.MODEL, max_tokens=1024, system=system, tools=TOOLS, messages=messages
            )
            final_text = "".join(b.text for b in msg.content if b.type == "text").strip()
            if msg.stop_reason != "tool_use":
                break
            messages.append({"role": "assistant", "content": msg.content})
            results = []
            for block in msg.content:
                if block.type == "tool_use":
                    output = await _run_tool(ctx, block.name, block.input)
                    results.append({"type": "tool_result", "tool_use_id": block.id, "content": output})
            messages.append({"role": "user", "content": results})
    except anthropic.APIError as exc:
        log.warning("Claude API error: %s", exc)
        return len(ctx.out) > ui_before
    if final_text:
        ctx.out.insert(ui_before, Out(text=final_text))
    return len(ctx.out) > ui_before


async def generate_text(prompt: str, max_tokens: int = 600) -> str | None:
    """Свободная генерация (маркетинговые тексты). None — модель недоступна."""
    if _client is None:
        return None
    try:
        msg = await _client.messages.create(
            model=config.MODEL, max_tokens=max_tokens, messages=[{"role": "user", "content": prompt}]
        )
    except anthropic.APIError as exc:
        log.warning("Claude API error: %s", exc)
        return None
    return "".join(b.text for b in msg.content if b.type == "text").strip() or None

