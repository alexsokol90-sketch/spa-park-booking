"""Диалоговый движок ассистента — общий для MAX и веб-эмулятора.

Вход: гость + текст / payload кнопки / телефон. Выход: список сообщений с кнопками.
Пятишаговая запись: запрос → 3–5 реальных окон → захват на 15 минут → данные гостя и согласия → бронь.
Правила: окно не обещается до фактического захвата; бронь не подтверждается, если она не создана в БД;
медицинских решений ассистент не принимает; сложные случаи передаются администратору.
"""
import logging
import re
from datetime import date, datetime, timedelta

from . import (
    ai,
    booking,
    certificates,
    config,
    db,
    escalation,
    guests,
    kb,
    loyalty,
    nlu,
    notify,
    speech,
    staff,
)
from .notify import Out
from .texts import fmt_day, fmt_time, fmt_when, t

log = logging.getLogger("dialog")

MAX_SLOTS = 5
MAX_MISUNDERSTOOD = 2
REQUIRED_CONSENTS = ("pd", "rules")
Buttons = list[list[tuple[str, str]]]


class Ctx:
    """Контекст обработки одного входящего сообщения."""

    def __init__(self, guest: dict, state: dict):
        self.guest = guest
        self.state = state
        self.out: list[Out] = []

    @property
    def lang(self) -> str:
        return self.guest.get("lang") or "ru"

    @property
    def gid(self) -> int:
        return self.guest["id"]

    def say(self, text: str, buttons: Buttons | None = None, **kw) -> None:
        self.out.append(Out(text=text, buttons=buttons or [], **kw))

    def tr(self, key: str, **kw) -> str:
        return t(key, self.lang, **kw)


def is_night() -> bool:
    return datetime.now(config.TZ).time() < config.OPEN_TIME


# ---------- точка входа ----------

async def handle(guest: dict, text: str | None = None, payload: str | None = None, phone: str | None = None) -> list[Out]:
    state = await guests.get_state(guest["id"])
    ctx = Ctx(guest, state)
    await guests.log(ctx.gid, "guest", text or phone or f"[кнопка] {payload}")
    try:
        if phone:
            await on_phone(ctx, phone)
        elif payload:
            await on_payload(ctx, payload)
        else:
            await on_text(ctx, text or "")
    except Exception:
        log.exception("dialog failure")
        ctx.say(ctx.tr("not_understood"), main_menu(ctx))
    await guests.save_state(ctx.gid, ctx.state)
    for item in ctx.out:
        await guests.log(ctx.gid, "bot", item.text)
    return ctx.out


async def handle_voice(guest: dict, audio: bytes | None, filename: str = "voice.ogg", text: str | None = None) -> list[Out]:
    """Голосовое сообщение: распознаём (или берём готовую расшифровку мессенджера) и обрабатываем как текст."""
    lang = guest.get("lang") or "ru"
    heard = text or (await speech.transcribe(audio, filename) if audio else None)
    if not heard:
        return [Out(text=speech.not_heard(lang), buttons=main_menu(Ctx(guest, {})))]
    return [Out(text=speech.heard(heard, lang)), *await handle(guest, text=heard)]


START_PARAM = re.compile(r"^(book|couple|staff|prices|(prog|space)_\d{1,4}|ref_[a-z0-9]{3,12})$")


def start_payload(param: str | None) -> str:
    """Параметр ссылки «Забронировать онлайн» (t.me/bot?start=book, max.ru/bot?start=book) → действие в диалоге."""
    param = (param or "").strip().lower()
    if not START_PARAM.match(param):
        return "menu"
    return param.replace("_", ":", 1)


def main_menu(ctx: Ctx) -> Buttons:
    return [
        [(ctx.tr("btn_book"), "book"), (ctx.tr("btn_programs"), "prices")],
        [(ctx.tr("btn_my"), "my"), (ctx.tr("btn_promo_main"), "faq:promo")],
        [(ctx.tr("btn_couple"), "couple"), (ctx.tr("btn_bonuses"), "bonuses")],
        [(ctx.tr("btn_info"), "faq:address"), (ctx.tr("btn_contra"), "faq:contraindications")],
        [(ctx.tr("btn_more"), "more"), (ctx.tr("btn_admin"), "admin")],
        [(ctx.tr("btn_lang"), "lang")],
    ]


def menu_row(ctx: Ctx) -> list[tuple[str, str]]:
    return [(ctx.tr("btn_menu"), "menu")]


async def greet(ctx: Ctx) -> None:
    ctx.state.pop("await", None)
    ctx.state.pop("master_id", None)
    name = ctx.guest.get("name")
    text = ctx.tr("greet_known", name=name) if name else ctx.tr("greet_new")
    if _birthday_soon(ctx.guest.get("birth_date")):
        text += "\n\n" + ctx.tr("birthday_soon")
    if (ctx.guest.get("max_user_id") or 0) > 0:
        text += "\n\n" + ctx.tr("max_voice_note")
    if is_night():
        text += "\n\n" + ctx.tr("night_note")
    ctx.say(text, main_menu(ctx))


# ---------- кнопки ----------

async def on_payload(ctx: Ctx, payload: str) -> None:
    head, _, rest = payload.partition(":")
    handler = PAYLOAD_HANDLERS.get(head)
    if handler is None:
        await greet(ctx)
        return
    ctx.state["misunderstood"] = 0
    await handler(ctx, rest)


async def p_menu(ctx: Ctx, _: str) -> None:
    await greet(ctx)


async def p_more(ctx: Ctx, _: str) -> None:
    buttons = [
        [(ctx.tr("btn_route"), "faq:parking"), (ctx.tr("btn_hours"), "faq:hours")],
        [(ctx.tr("btn_cert"), "faq:certificate"), (ctx.tr("btn_promo"), "faq:promo")],
        [(ctx.tr("btn_groups"), "groups"), (ctx.tr("btn_etiquette"), "faq:etiquette")],
        [(ctx.tr("btn_payment"), "faq:payment"), (ctx.tr("btn_staff"), "staff")],
        [(ctx.tr("btn_cert_check"), "certcheck"), (ctx.tr("btn_invite"), "invite")],
        menu_row(ctx),
    ]
    ctx.say(ctx.tr("more_title"), buttons)


async def p_lang(ctx: Ctx, _: str) -> None:
    new = "en" if ctx.lang == "ru" else "ru"
    await guests.set_lang(ctx.gid, new)
    ctx.guest["lang"] = new
    ctx.say(ctx.tr("lang_set"), main_menu(ctx))


# ---------- каталог ----------

async def p_book(ctx: Ctx, _: str) -> None:
    ctx.state.pop("reschedule_of", None)
    ctx.state.pop("master_id", None)
    spaces = await db.query("SELECT id, name, name_en FROM spaces ORDER BY sort")
    rows = _pairs([(_name(ctx, s), f"space:{s['id']}") for s in spaces])
    ctx.say(ctx.tr("choose_space"), rows + [[(ctx.tr("btn_couple"), "couple")], menu_row(ctx)])


def _price_text(ctx: Ctx, prog: dict) -> str:
    parts = []
    if prog["price"] is not None:
        parts.append(ctx.tr("price_line_1", price=_money(prog["price"])))
    if prog["price_couple"] is not None:
        parts.append(ctx.tr("price_line_2", price=_money(prog["price_couple"])))
    return " / ".join(parts)


async def p_space(ctx: Ctx, arg: str) -> None:
    space = await db.query_one("SELECT * FROM spaces WHERE id = %s", (int(arg),))
    progs = await db.query(
        "SELECT * FROM programs WHERE space_id = %s AND active ORDER BY COALESCE(price, price_couple)", (int(arg),)
    )
    minutes = "мин" if ctx.lang == "ru" else "min"
    lines = [f"• {_name(ctx, p)} — {p['duration_min']} {minutes}, {_price_text(ctx, p)}" for p in progs]
    buttons = [[(_name(ctx, p), f"prog:{p['id']}")] for p in progs]
    text = ctx.tr("choose_program", space=_name(ctx, space)) + "\n" + _name(ctx, space, "description") + "\n\n" + "\n".join(lines)
    ctx.say(text, buttons + [[(ctx.tr("btn_back"), "book")] + menu_row(ctx)])


async def p_couple(ctx: Ctx, _: str) -> None:
    progs = await db.query(
        """SELECT p.*, s.name AS space_name, s.name_en AS space_name_en FROM programs p
           JOIN spaces s ON s.id = p.space_id
           WHERE p.active AND p.price_couple IS NOT NULL AND p.price IS NULL ORDER BY s.sort"""
    )
    lines = [f"• {_name(ctx, p)} ({_name(ctx, p, 'space_name')}) — {p['duration_min']} мин, {_money(p['price_couple'])} ₽" for p in progs]
    buttons = [[(_name(ctx, p), f"prog:{p['id']}")] for p in progs]
    ctx.say(ctx.tr("couple_title") + "\n" + "\n".join(lines), buttons + [menu_row(ctx)])


async def p_prog(ctx: Ctx, arg: str) -> None:
    async with db.tx() as conn:
        prog = await booking.get_program(conn, int(arg))
    text = ctx.tr(
        "program_card",
        name=_name(ctx, prog),
        descr=_name(ctx, prog, "description"),
        dur=prog["duration_min"],
        price=_price_text(ctx, prog),
        guests=prog["max_guests"],
    )
    if prog["prepay"]:
        text += "\n\n" + ctx.tr("prepay_note")
    row = []
    if prog["price"] is not None:
        row.append((ctx.tr("btn_one_guest", price=_money(prog["price"])), f"days:{prog['id']}:1"))
    if prog["price_couple"] is not None:
        row.append((ctx.tr("btn_two_guests", price=_money(prog["price_couple"])), f"days:{prog['id']}:2"))
    ctx.say(text, [row, [(ctx.tr("btn_back"), f"space:{prog['space_id']}")] + menu_row(ctx)])


# ---------- шаг 2: окна ----------

async def p_days(ctx: Ctx, arg: str) -> None:
    prog_id, _, guests_count = arg.partition(":")
    await show_days(ctx, int(prog_id), _guests(guests_count))


async def show_days(ctx: Ctx, program_id: int, guests_count: int = 1, text: str | None = None) -> None:
    days = await booking.nearest_days_with_slots(program_id, days=7, master_id=ctx.state.get("master_id"))
    if not days:
        await escalate(ctx, "no_slots", f"Нет окон на неделю, программа #{program_id}")
        return
    buttons = _pairs([(fmt_day(d, ctx.lang), f"slots:{program_id}:{d.isoformat()}:{guests_count}") for d in days])
    ctx.say(text or ctx.tr("choose_day"), buttons + [menu_row(ctx)])


async def p_slots(ctx: Ctx, arg: str) -> None:
    prog_id, day, *rest = arg.split(":")
    await show_slots(ctx, int(prog_id), date.fromisoformat(day), guests_count=_guests(rest[0] if rest else ""))


async def show_slots(ctx: Ctx, program_id: int, day: date, around: datetime | None = None, guests_count: int | None = None) -> None:
    async with db.tx() as conn:
        prog = await booking.get_program(conn, program_id)
    guests_count = guests_count or booking.default_guests(prog)
    slots = await booking.find_slots(
        program_id, day, around=around, limit=MAX_SLOTS, guests=guests_count, master_id=ctx.state.get("master_id")
    )
    if not slots:
        await show_days(ctx, program_id, guests_count, ctx.tr("no_slots_day", day=fmt_day(day, ctx.lang)))
        return
    buttons = _pairs([(fmt_time(s.start), _slot_payload(s)) for s in slots], per_row=3)
    text = ctx.tr("choose_slot", day=fmt_day(day, ctx.lang), name=_name(ctx, prog))
    ctx.say(text, buttons + [[(ctx.tr("btn_back"), f"days:{program_id}:{guests_count}")] + menu_row(ctx)])


def _slot_payload(slot: booking.Slot) -> str:
    return f"hold:{slot.program_id}:{int(slot.start.timestamp())}:{slot.master_id}:{slot.guests}"


# ---------- шаг 3: захват ----------

async def p_hold(ctx: Ctx, arg: str) -> None:
    parts = [int(x) for x in arg.split(":")]
    prog_id, ts, master_id = parts[:3]
    guests_count = parts[3] if len(parts) > 3 else None
    start = datetime.fromtimestamp(ts, tz=config.TZ)
    await try_hold(ctx, prog_id, start, master_id, guests_count)


async def try_hold(ctx: Ctx, program_id: int, start: datetime, master_id: int | None, guests_count: int | None = None) -> None:
    """Окно обещается гостю только после успешного захвата в БД."""
    try:
        hold = await booking.create_hold(ctx.gid, program_id, start, master_id, "bot", guests_count)
    except booking.SlotTaken:
        await offer_alternatives(ctx, program_id, start, guests_count or 1)
        return
    ctx.state["hold_id"] = hold["id"]
    text = ctx.tr(
        "held",
        until=fmt_time(hold["hold_expires_at"]),
        name=_name(ctx, hold, "program_name"),
        when=fmt_when(hold["starts_at"], ctx.lang),
        master=hold["master_name"],
        price=_money(hold["price"]),
    )
    buttons = [
        [(ctx.tr("btn_confirm"), f"confirm:{hold['id']}")],
        [(ctx.tr("btn_other_time"), f"days:{program_id}:{hold['guests_count']}")],
    ]
    ctx.say(text, buttons)


async def offer_alternatives(ctx: Ctx, program_id: int, wanted: datetime, guests_count: int = 1) -> None:
    options = await booking.alternatives(program_id, wanted, guests=guests_count)
    if not options:
        await escalate(ctx, "no_slots", f"Желаемое время: программа #{program_id}, {fmt_when(wanted, 'ru')}", silent=True)
        ctx.say(ctx.tr("slot_taken_none"), [menu_row(ctx)])
        return
    ids = [o.program_id for o in options]
    names = {r["id"]: r for r in await db.query("SELECT id, name, name_en FROM programs WHERE id = ANY(%s)", (ids,))}
    buttons = [[(f"{fmt_time(o.start)} · {_name(ctx, names[o.program_id])}", _slot_payload(o))] for o in options]
    ctx.say(ctx.tr("slot_taken"), buttons + [menu_row(ctx)])


# ---------- шаг 4: данные гостя и согласия ----------

async def p_confirm(ctx: Ctx, arg: str) -> None:
    ctx.state["hold_id"] = int(arg)
    await proceed_confirm(ctx)


async def proceed_confirm(ctx: Ctx) -> None:
    """Телефон (с автоподтягиванием гостя из базы) → имя → галочки согласий → бронь."""
    hold_id = ctx.state.get("hold_id")
    if not hold_id:
        await greet(ctx)
        return
    guest = await guests.get(ctx.gid)
    ctx.guest = guest
    if not guest["phone"]:
        ctx.state["await"] = "phone"
        ctx.say(ctx.tr("need_phone"), [menu_row(ctx)], request_contact=True)
        return
    if not guest["name"]:
        ctx.state["await"] = "name"
        ctx.say(ctx.tr("need_name"), [menu_row(ctx)])
        return
    if not all([await guests.has_consent(ctx.gid, kind) for kind in REQUIRED_CONSENTS]):
        await show_consents(ctx)
        return
    await finish_booking(ctx, hold_id)


async def show_consents(ctx: Ctx) -> None:
    boxes = ctx.state.get("cb")
    if boxes is None:
        boxes = {kind: await guests.has_consent(ctx.gid, kind) for kind in ("pd", "rules", "ads")}
        ctx.state["cb"] = boxes
    buttons = [[(("☑ " if boxes[k] else "☐ ") + ctx.tr(f"cb_{k}"), f"cb:{k}")] for k in ("pd", "rules", "ads")]
    buttons.append([(ctx.tr("btn_consent_texts"), "cbtexts"), (ctx.tr("btn_continue"), "cbok")])
    ctx.say(ctx.tr("consent_title"), buttons)


async def p_checkbox(ctx: Ctx, kind: str) -> None:
    boxes = ctx.state.get("cb") or {"pd": False, "rules": False, "ads": False}
    if kind in boxes:
        boxes[kind] = not boxes[kind]
    ctx.state["cb"] = boxes
    await show_consents(ctx)


async def p_consent_texts(ctx: Ctx, _: str) -> None:
    text = "\n\n".join(f"{ctx.tr('cb_' + kind)}:\n{body}" for kind, body in kb.CONSENT_TEXTS.items())
    ctx.say(text + "\n\n" + kb.faq("etiquette", ctx.lang))
    await show_consents(ctx)


async def p_consent_ok(ctx: Ctx, _: str) -> None:
    boxes = ctx.state.get("cb") or {}
    if not all(boxes.get(k) for k in REQUIRED_CONSENTS):
        ctx.say(ctx.tr("consent_required"))
        await show_consents(ctx)
        return
    for kind in ("pd", "rules", "ads"):
        if boxes.get(kind) != await guests.has_consent(ctx.gid, kind) or kind in REQUIRED_CONSENTS:
            await guests.add_consent(ctx.gid, kind, bool(boxes.get(kind)))
    ctx.state.pop("cb", None)
    await proceed_confirm(ctx)


async def on_phone(ctx: Ctx, raw: str) -> None:
    phone = guests.normalize_phone(raw)
    if not phone:
        ctx.say(ctx.tr("need_phone"), [menu_row(ctx)], request_contact=True)
        return
    ctx.guest = await guests.attach_phone(ctx.gid, phone)
    ctx.state.pop("await", None)
    await proceed_confirm(ctx)


async def on_name(ctx: Ctx, text: str) -> None:
    await guests.set_name(ctx.gid, text.strip()[:60])
    ctx.state.pop("await", None)
    await proceed_confirm(ctx)


# ---------- шаг 5: бронь и подтверждение ----------

async def finish_booking(ctx: Ctx, hold_id: int) -> None:
    try:
        bk = await booking.confirm(hold_id, replaces_id=ctx.state.pop("reschedule_of", None))
    except booking.BookingError:
        ctx.state.pop("hold_id", None)
        bk = await booking.get_booking(hold_id)
        await show_days(ctx, bk["program_id"], bk["guests_count"], ctx.tr("hold_expired"))
        return
    ctx.state.pop("hold_id", None)
    text = ctx.tr(
        "confirmed_full",
        name=ctx.guest.get("name") or "",
        program=_name(ctx, bk, "program_name"),
        when=fmt_when(bk["starts_at"], ctx.lang),
        dur=bk["duration_min"],
        guests=bk["guests_count"],
        master=bk["master_name"],
        price=_money(bk["price"]),
        rules=kb.faq("cancel_rules", ctx.lang),
    )
    if bk["prepay"]:
        text += "\n\n" + ctx.tr("prepay_note")
    if is_night():
        text += "\n\n" + ctx.tr("night_note")
    buttons = [[(ctx.tr("btn_preorder"), f"pre:{bk['id']}")], [(ctx.tr("btn_etiquette_full"), "faq:etiquette")], menu_row(ctx)]
    ctx.say(text, buttons, link=(ctx.tr("btn_pay"), config.PAYMENT_URL))
    await notify.to_admin(
        f"Новая бронь из бота: {bk['program_name']}, {fmt_when(bk['starts_at'], 'ru')}, {bk['guest_name']} {bk['guest_phone']}",
        kind="booking",
    )
    guest = await guests.get(ctx.gid)
    if not guest["survey_done"]:
        await start_survey(ctx, guest)


# ---------- мои записи, отмена, перенос ----------

async def p_my(ctx: Ctx, _: str) -> None:
    items = await booking.guest_upcoming(ctx.gid)
    if not items:
        ctx.say(ctx.tr("my_none"), [[(ctx.tr("btn_book"), "book")], menu_row(ctx)])
        return
    for bk in items:
        text = f"*{_name(ctx, bk, 'program_name')}*\n{fmt_when(bk['starts_at'], ctx.lang)} · {bk['master_name']}"
        ctx.say(
            text,
            [
                [(ctx.tr("btn_reschedule"), f"resched:{bk['id']}"), (ctx.tr("btn_cancel"), f"cancel:{bk['id']}")],
                [(ctx.tr("btn_preorder"), f"pre:{bk['id']}")],
            ],
        )
    ctx.say(ctx.tr("my_list"), [menu_row(ctx)])


async def _own_booking(ctx: Ctx, arg: str) -> dict | None:
    bk = await booking.get_booking(int(arg))
    return bk if bk["guest_id"] == ctx.gid else None


async def p_cancel(ctx: Ctx, arg: str) -> None:
    bk = await _own_booking(ctx, arg)
    if not bk:
        await greet(ctx)
        return
    text = ctx.tr("cancel_ask", name=_name(ctx, bk, "program_name"), when=fmt_when(bk["starts_at"], ctx.lang))
    ctx.say(text + "\n\n" + kb.faq("cancel_rules", ctx.lang), [[(ctx.tr("btn_cancel_yes"), f"cancelok:{bk['id']}")], [(ctx.tr("btn_back"), "my")]])


async def p_cancel_ok(ctx: Ctx, arg: str) -> None:
    if await booking.cancel(int(arg), guest_id=ctx.gid):
        await notify.to_admin(f"Гость отменил бронь №{arg} через бота", kind="booking")
    ctx.say(ctx.tr("cancelled"), [[(ctx.tr("btn_book"), "book")], menu_row(ctx)])


async def p_resched(ctx: Ctx, arg: str) -> None:
    bk = await _own_booking(ctx, arg)
    if not bk:
        await greet(ctx)
        return
    ctx.state["reschedule_of"] = bk["id"]
    await show_days(ctx, bk["program_id"], bk["guests_count"], ctx.tr("reschedule_pick", name=_name(ctx, bk, "program_name")))


# ---------- подтверждение визита и предзаказ ----------

async def p_visit(ctx: Ctx, arg: str) -> None:
    bk = await _own_booking(ctx, arg)
    if not bk:
        await greet(ctx)
        return
    await db.query("UPDATE bookings SET visit_status = 'confirmed' WHERE id = %s RETURNING id", (bk["id"],))
    ctx.say(ctx.tr("visit_thanks"), [[(ctx.tr("btn_preorder"), f"pre:{bk['id']}")], menu_row(ctx)])


async def p_preorder(ctx: Ctx, arg: str) -> None:
    bk = await _own_booking(ctx, arg)
    if not bk:
        await greet(ctx)
        return
    await show_preorder(ctx, bk)


async def show_preorder(ctx: Ctx, bk: dict) -> None:
    items = await db.query(
        """SELECT i.* FROM preorder_items i JOIN program_preorders pp ON pp.item_id = i.id
           WHERE pp.program_id = %s AND i.active AND i.stock > 0 ORDER BY i.category, i.id""",
        (bk["program_id"],),
    )
    if not items:
        ctx.say(ctx.tr("preorder_none"), [menu_row(ctx)])
        return
    chosen = {p["id"] for p in bk["preorders"]}
    buttons = []
    for item in items:
        mark = "✓ " if item["id"] in chosen else ""
        price = f" · {item['price']} ₽" if item["price"] else ""
        buttons.append([(f"{mark}{_name(ctx, item)}{price}", f"pretog:{bk['id']}:{item['id']}")])
    buttons.append([(ctx.tr("btn_done"), f"predone:{bk['id']}")])
    ctx.say(ctx.tr("preorder_intro"), buttons)


async def p_pretoggle(ctx: Ctx, arg: str) -> None:
    bk_id, item_id = arg.split(":")
    bk = await _own_booking(ctx, bk_id)
    if not bk:
        await greet(ctx)
        return
    async with db.tx() as conn:
        cur = await conn.execute(
            "DELETE FROM booking_preorders WHERE booking_id = %s AND item_id = %s RETURNING item_id", (bk["id"], int(item_id))
        )
        if await cur.fetchone() is None:
            await conn.execute("INSERT INTO booking_preorders (booking_id, item_id) VALUES (%s, %s)", (bk["id"], int(item_id)))
    await show_preorder(ctx, await booking.get_booking(bk["id"]))


async def p_predone(ctx: Ctx, arg: str) -> None:
    bk = await _own_booking(ctx, arg)
    if not bk:
        await greet(ctx)
        return
    names = ", ".join(_name(ctx, p) for p in bk["preorders"])
    text = ctx.tr("preorder_saved", items=names) if names else ctx.tr("preorder_empty")
    ctx.say(text, [menu_row(ctx)])


# ---------- справка, группы, отписка, эскалация ----------

async def p_faq(ctx: Ctx, key: str) -> None:
    answer = kb.faq(key, ctx.lang)
    if key == "address":
        answer += "\n\n" + kb.faq("hours", ctx.lang) + "\n" + kb.faq("parking", ctx.lang)
    ctx.say(answer, [[(ctx.tr("btn_book"), "book")], menu_row(ctx)])


async def p_prices(ctx: Ctx, _: str) -> None:
    rows = await db.query(
        """SELECT s.id AS space_id, s.name AS space, s.name_en AS space_en,
                  min(COALESCE(p.price, p.price_couple)) AS min_price, count(*) AS n
           FROM programs p JOIN spaces s ON s.id = p.space_id WHERE p.active GROUP BY s.id ORDER BY s.sort"""
    )
    rub, since, progs = ("₽", "от", "программ") if ctx.lang == "ru" else ("RUB", "from", "programs")
    lines = [f"• {r['space_en'] if ctx.lang == 'en' else r['space']}: {r['n']} {progs}, {since} {_money(r['min_price'])} {rub}" for r in rows]
    buttons = _pairs([(r["space_en"] if ctx.lang == "en" else r["space"], f"space:{r['space_id']}") for r in rows])
    ctx.say(ctx.tr("prices_intro") + "\n" + "\n".join(lines), buttons + [[(ctx.tr("btn_couple"), "couple")], menu_row(ctx)])


async def p_groups(ctx: Ctx, _: str) -> None:
    ctx.state["await"] = "group_wishes"
    ctx.say(kb.faq("groups", ctx.lang) + "\n\n" + ctx.tr("groups_ask"), [menu_row(ctx)])


async def p_unsubscribe(ctx: Ctx, _: str) -> None:
    await guests.add_consent(ctx.gid, "ads", False)
    await db.query("UPDATE guests SET unsubscribed = true WHERE id = %s RETURNING id", (ctx.gid,))
    ctx.say(ctx.tr("unsubscribed"), [menu_row(ctx)])


async def p_admin(ctx: Ctx, _: str) -> None:
    await escalate(ctx, "asked_admin", "Гость нажал «Администратор»")


async def escalate(ctx: Ctx, reason: str, details: str = "", silent: bool = False) -> None:
    await escalation.create(ctx.gid, reason, details)
    if silent:
        return
    if reason == "group":
        when = (" " + ("after 10:00" if ctx.lang == "en" else "после 10:00")) if is_night() else ""
        ctx.say(ctx.tr("escalated_group", when=when), [[(ctx.tr("btn_groups"), "groups")], menu_row(ctx)])
        return
    ctx.say(ctx.tr("escalated_night" if is_night() else "escalated"), [menu_row(ctx)])


async def p_staff(ctx: Ctx, arg: str) -> None:
    """Кто из мастеров работает в день (по графику управляющего)."""
    day = date.fromisoformat(arg) if arg else booking.now().date()
    team = await staff.on_duty(day)
    tomorrow = (day + timedelta(days=1)).isoformat()
    if not team:
        ctx.say(ctx.tr("staff_none", day=fmt_day(day, ctx.lang)), [[(ctx.tr("btn_tomorrow"), f"staff:{tomorrow}")], menu_row(ctx)])
        return
    lines = [f"• {m['name']} — {m['start']}–{m['end']} ({m['skills']})" for m in team]
    buttons = _pairs([(ctx.tr("btn_book_master", name=m["name"]), f"master:{m['id']}") for m in team])
    ctx.say(
        ctx.tr("staff_title", day=fmt_day(day, ctx.lang)) + "\n" + "\n".join(lines),
        buttons + [[(ctx.tr("btn_tomorrow"), f"staff:{tomorrow}")], menu_row(ctx)],
    )


async def p_master(ctx: Ctx, arg: str) -> None:
    """Запись к конкретному мастеру: дальше окна подбираются только в его смены."""
    master = await db.query_one("SELECT id, name FROM masters WHERE id = %s AND active", (int(arg),))
    if not master:
        await greet(ctx)
        return
    ctx.state["master_id"] = master["id"]
    shifts = await staff.master_days(master["id"])
    days = ", ".join(f"{fmt_day(s['day'], ctx.lang)} {s['start']}–{s['end']}" for s in shifts[:5]) or "—"
    spaces = await db.query("SELECT id, name, name_en FROM spaces ORDER BY sort")
    rows = _pairs([(_name(ctx, s), f"space:{s['id']}") for s in spaces])
    text = ctx.tr("master_pick", name=master["name"]) + "\n\n" + ctx.tr("master_days", name=master["name"], days=days)
    ctx.say(text, rows + [menu_row(ctx)])


# ---------- мини-анкета, бонусы, приглашения, сертификаты ----------

def _birthday_soon(birth: date | None, days: int = 7) -> bool:
    if not birth:
        return False
    today = booking.now().date()
    try:
        this_year = birth.replace(year=today.year)
    except ValueError:
        this_year = date(today.year, 3, 1)
    return 0 <= (this_year - today).days <= days


def parse_birth(text: str) -> date | None:
    match = re.search(r"(\d{1,2})[./\- ](\d{1,2})[./\- ](\d{4})", text)
    if not match:
        return None
    try:
        value = date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
    except ValueError:
        return None
    today = booking.now().date()
    return value if date(1920, 1, 1) <= value <= today.replace(year=today.year - 10) else None


async def start_survey(ctx: Ctx, guest: dict) -> None:
    """Мини-анкета после первой брони: дата рождения, обращение, откуда узнали. Всё по желанию."""
    if guest.get("birth_date"):
        await ask_gender(ctx)
        return
    ctx.state["await"] = "survey_birth"
    ctx.say(ctx.tr("survey_birth"), [[(ctx.tr("btn_skip"), "srv:birth_skip")]])


async def ask_gender(ctx: Ctx) -> None:
    ctx.state.pop("await", None)
    ctx.say(ctx.tr("survey_gender"), [[(ctx.tr("btn_female"), "srv:g_f"), (ctx.tr("btn_male"), "srv:g_m")], [(ctx.tr("btn_skip"), "srv:g_skip")]])


async def ask_source(ctx: Ctx) -> None:
    keys = ["site", "social", "referral", "ads", "reception", "qr"]
    buttons = _pairs([(ctx.tr("src_" + k), "srv:s_" + k) for k in keys]) + [[(ctx.tr("btn_skip"), "srv:s_skip")]]
    ctx.say(ctx.tr("survey_source"), buttons)


async def p_survey(ctx: Ctx, arg: str) -> None:
    if arg == "birth_skip":
        await ask_gender(ctx)
    elif arg.startswith("g_"):
        if arg in ("g_f", "g_m"):
            await db.query("UPDATE guests SET gender = %s WHERE id = %s RETURNING id", (arg[-1], ctx.gid))
        await ask_source(ctx)
    elif arg.startswith("s_"):
        source = arg[2:]
        if source != "skip":
            await db.query(
                "UPDATE guests SET reg_source = %s WHERE id = %s AND reg_source <> 'referral' RETURNING id", (source, ctx.gid)
            )
        await db.query("UPDATE guests SET survey_done = true WHERE id = %s RETURNING id", (ctx.gid,))
        await loyalty.ensure_referral_code(ctx.gid)
        ctx.say(ctx.tr("survey_done", name=ctx.guest.get("name") or ""), [[(ctx.tr("btn_bonuses"), "bonuses")], menu_row(ctx)])


async def on_birth(ctx: Ctx, text: str) -> bool:
    birth = parse_birth(text)
    if not birth:
        ctx.say(ctx.tr("survey_birth_bad"), [[(ctx.tr("btn_skip"), "srv:birth_skip")]])
        return True
    await db.query("UPDATE guests SET birth_date = %s WHERE id = %s RETURNING id", (birth, ctx.gid))
    await ask_gender(ctx)
    return True


async def p_bonuses(ctx: Ctx, _: str) -> None:
    from .automations import referral_link

    guest = await guests.get(ctx.gid)
    if not guest["phone"]:
        ctx.state["await"] = "phone"
        ctx.say(ctx.tr("bonuses_need_phone"), [menu_row(ctx)], request_contact=True)
        return
    code = await loyalty.ensure_referral_code(ctx.gid)
    names = {"gold": "Gold", "platinum": "Platinum"} if ctx.lang == "en" else {"gold": "Золотая", "platinum": "Платиновая"}
    text = ctx.tr("bonuses_info", points=guest["loyalty_points"], level=names.get(guest["card_level"], guest["card_level"]),
                  cashback=int(loyalty.CASHBACK.get(guest["card_level"], 0.05) * 100), link=referral_link(code))
    ctx.say(text, [[(ctx.tr("btn_book"), "book")], menu_row(ctx)])


async def p_ref(ctx: Ctx, code: str) -> None:
    if await loyalty.apply_referral(ctx.gid, code):
        ctx.say(ctx.tr("ref_ok"))
    await greet(ctx)


async def p_certcheck(ctx: Ctx, _: str) -> None:
    ctx.state["await"] = "certificate"
    ctx.say(ctx.tr("cert_ask"), [menu_row(ctx)])


async def on_certificate(ctx: Ctx, text: str) -> bool:
    match = re.search(r"[A-Za-zА-Яа-я]{0,3}-?\d{4,12}", text)
    if not match:
        return False
    ctx.state.pop("await", None)
    cert = await certificates.find(match.group(0))
    if not cert:
        ctx.say(ctx.tr("cert_missing"), [[(ctx.tr("btn_admin"), "admin")], menu_row(ctx)])
        return True
    until = fmt_day(cert["expires_at"], ctx.lang)
    if cert["status"] == "active":
        ctx.say(ctx.tr("cert_found", number=cert["number"], balance=_money(cert["balance"]), amount=_money(cert["amount"]), until=until),
                [[(ctx.tr("btn_book"), "book")], menu_row(ctx)])
        return True
    status = {"used": "уже использован", "expired": "срок действия истёк", "cancelled": "аннулирован"}[cert["status"]]
    ctx.say(ctx.tr("cert_inactive", number=cert["number"], status=status), [[(ctx.tr("btn_admin"), "admin")], menu_row(ctx)])
    return True


PAYLOAD_HANDLERS = {
    "menu": p_menu,
    "more": p_more,
    "lang": p_lang,
    "book": p_book,
    "space": p_space,
    "couple": p_couple,
    "prog": p_prog,
    "days": p_days,
    "slots": p_slots,
    "hold": p_hold,
    "confirm": p_confirm,
    "cb": p_checkbox,
    "cbtexts": p_consent_texts,
    "cbok": p_consent_ok,
    "my": p_my,
    "cancel": p_cancel,
    "cancelok": p_cancel_ok,
    "resched": p_resched,
    "visit": p_visit,
    "pre": p_preorder,
    "pretog": p_pretoggle,
    "predone": p_predone,
    "faq": p_faq,
    "prices": p_prices,
    "groups": p_groups,
    "unsub": p_unsubscribe,
    "admin": p_admin,
    "staff": p_staff,
    "master": p_master,
    "srv": p_survey,
    "bonuses": p_bonuses,
    "invite": p_bonuses,
    "ref": p_ref,
    "certcheck": p_certcheck,
}


# ---------- свободный текст ----------

async def on_awaited(ctx: Ctx, text: str) -> bool:
    """Ответ на вопрос, который ассистент задал последним (телефон, имя, пожелания, отзыв)."""
    waiting = ctx.state.get("await")
    if waiting == "phone" and guests.normalize_phone(text):
        await on_phone(ctx, text)
        return True
    if waiting == "name" and 1 < len(text.strip()) <= 60:
        await on_name(ctx, text)
        return True
    if waiting == "survey_birth":
        return await on_birth(ctx, text)
    if waiting == "certificate" and await on_certificate(ctx, text):
        return True
    if waiting == "group_wishes":
        ctx.state.pop("await", None)
        await escalate(ctx, "group", text)
        return True
    if waiting == "review":
        ctx.state.pop("await", None)
        await notify.to_admin(f"Отзыв гостя {ctx.guest.get('name') or ''}: {text}", kind="review")
        ctx.say(ctx.tr("review_thanks"), [menu_row(ctx)])
        return True
    return False


async def on_text(ctx: Ctx, text: str) -> None:
    low = text.strip().lower()
    if low in ("/start", "start", "/menu", "начать", "меню", "menu"):
        await greet(ctx)
        return
    if nlu.is_unsubscribe(low):
        await p_unsubscribe(ctx, "")
        return
    detected = nlu.detect_lang(text)
    if detected and detected != ctx.lang:
        await guests.set_lang(ctx.gid, detected)
        ctx.guest["lang"] = detected
    programs = await db.query("SELECT id, name, name_en FROM programs WHERE active")
    for prog in programs:
        PROGRAM_STEMS.setdefault(prog["id"], nlu.stems_of(prog["name"] + " " + prog["name_en"]))
    parsed = nlu.parse(text, programs)
    if parsed.escalation:
        await on_escalation_trigger(ctx, parsed.escalation, text)
        return
    if await on_awaited(ctx, text):
        return
    if parsed.intent == "drinks":
        await answer_and_escalate(ctx, "drinks", text)
        return
    masters = await db.query("SELECT id, name FROM masters WHERE active")
    named = nlu.match_master(text, masters)
    if named:
        ctx.state["master_id"] = named
        if not (parsed.program_id or parsed.intent == "staff"):
            await p_master(ctx, str(named))
            return
    if ai.enabled() and await ai.agent_reply(ctx, text):
        ctx.state["misunderstood"] = 0
        return
    await rule_reply(ctx, parsed, text)


async def on_escalation_trigger(ctx: Ctx, reason: str, text: str) -> None:
    if reason == "health":
        await escalation.create(ctx.gid, "health", text)
        ctx.say(ctx.tr("health_note") + "\n\n" + kb.faq("contraindications", ctx.lang), [menu_row(ctx)])
        return
    if reason == "group":
        await escalate(ctx, "group", text)
        ctx.state["await"] = "group_wishes"
        return
    await escalate(ctx, reason, text)


SPACE_INTENTS = (None, "book", "programs", "prices")
INTENT_TO_PAYLOAD = {
    "cancel": "my",
    "reschedule": "my",
    "my": "my",
    "contraindications": "faq:contraindications",
    "parking": "faq:parking",
    "address": "faq:address",
    "hours": "faq:hours",
    "payment": "faq:payment",
    "certificate": "faq:certificate",
    "etiquette": "faq:etiquette",
    "promo": "faq:promo",
    "couple": "couple",
    "prices": "prices",
    "programs": "prices",
    "book": "book",
    "greeting": "menu",
    "staff": "staff",
    "loyalty": "faq:loyalty",
    "children": "faq:children",
    "hotel": "faq:hotel",
}


async def rule_reply(ctx: Ctx, parsed: nlu.Parsed, text: str) -> None:
    """Ответ без модели: программа/дата/время из текста или типовое намерение."""
    if parsed.tag and not _strong_program_match(parsed, text):
        ctx.state["misunderstood"] = 0
        await show_by_tag(ctx, parsed.tag)
        return
    if parsed.program_id and (parsed.day or parsed.intent == "book"):
        ctx.state["misunderstood"] = 0
        await show_slots(ctx, parsed.program_id, parsed.day or booking.now().date(), around=parsed.at)
        return
    if parsed.program_id:
        ctx.state["misunderstood"] = 0
        await p_prog(ctx, str(parsed.program_id))
        return
    if parsed.space_code and parsed.intent in SPACE_INTENTS:
        space = await db.query_one("SELECT id FROM spaces WHERE code = %s", (parsed.space_code,))
        ctx.state["misunderstood"] = 0
        await p_space(ctx, str(space["id"]))
        return
    if parsed.intent == "drinks":
        await answer_and_escalate(ctx, "drinks", text)
        return
    if parsed.intent == "staff":
        await p_staff(ctx, (parsed.day or booking.now().date()).isoformat())
        return
    if parsed.intent:
        await on_payload(ctx, INTENT_TO_PAYLOAD[parsed.intent])
        return
    await not_understood(ctx, text)


def _strong_program_match(parsed: nlu.Parsed, text: str) -> bool:
    """Название программы названо явно (а не только вид процедуры)."""
    if not parsed.program_id:
        return False
    tag_words = {k for keys in nlu.TAG_STEMS.values() for k in keys} | nlu.GENERIC_STEMS
    other = {w for w in nlu.stems_of(text) if not any(w.startswith(k) or k.startswith(w) for k in tag_words)}
    return bool(other & PROGRAM_STEMS.get(parsed.program_id, set()))


PROGRAM_STEMS: dict[int, set[str]] = {}


async def show_by_tag(ctx: Ctx, tag: str) -> None:
    progs = await db.query(
        """SELECT p.*, s.name AS space_name, s.name_en AS space_name_en FROM programs p
           JOIN spaces s ON s.id = p.space_id WHERE p.active AND p.tags LIKE %s ORDER BY s.sort, p.price""",
        (f"%{tag}%",),
    )
    minutes = "мин" if ctx.lang == "ru" else "min"
    lines = [f"• {_name(ctx, p)} ({_name(ctx, p, 'space_name')}) — {p['duration_min']} {minutes}, {_price_text(ctx, p)}" for p in progs]
    buttons = [[(_name(ctx, p), f"prog:{p['id']}")] for p in progs[:10]]
    ctx.say(ctx.tr("by_tag_title") + "\n" + "\n".join(lines), buttons + [menu_row(ctx)])


async def answer_and_escalate(ctx: Ctx, faq_key: str, text: str) -> None:
    """Частичный ответ: то, что есть в базе знаний, — сразу; остальное уточняет администратор.
    Так гость не остаётся без ответа, а ассистент ничего не придумывает."""
    ctx.state["misunderstood"] = 0
    await escalation.create(ctx.gid, "out_of_kb", text)
    later = ctx.tr("partial_night") if is_night() else ctx.tr("partial_day")
    ctx.say(kb.faq(faq_key, ctx.lang) + "\n\n" + later, [[(ctx.tr("btn_book"), "book")], menu_row(ctx)])


async def not_understood(ctx: Ctx, text: str) -> None:
    attempts = ctx.state.get("misunderstood", 0) + 1
    ctx.state["misunderstood"] = attempts
    history = ctx.state.setdefault("failed", [])
    history.append(text[:200])
    del history[:-MAX_MISUNDERSTOOD]
    if attempts >= MAX_MISUNDERSTOOD:
        ctx.state["misunderstood"] = 0
        details = "Попытки понять: " + " | ".join(history)
        ctx.state["failed"] = []
        await escalate(ctx, "not_understood", details)
        return
    ctx.say(ctx.tr("not_understood"), main_menu(ctx))


# ---------- утилиты ----------

def _name(ctx: Ctx, row: dict, key: str = "name") -> str:
    if ctx.lang == "en":
        return row.get(f"{key}_en") or row.get(key) or ""
    return row.get(key) or ""


def _money(value: int | None) -> str:
    return f"{value:,}".replace(",", " ") if value is not None else "—"


def _guests(raw: str) -> int:
    return 2 if raw == "2" else 1


def _pairs(items: list[tuple[str, str]], per_row: int = 2) -> Buttons:
    return [items[i : i + per_row] for i in range(0, len(items), per_row)]
