"""HTTP-сервис: веб-эмулятор чата гостя, интерфейс администратора, API."""
import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from psycopg import errors
from pydantic import BaseModel, Field

from . import (
    ai,
    automations,
    booking,
    certificates,
    config,
    db,
    dialog,
    escalation,
    events,
    guests,
    loyalty,
    marketing,
    max_bot,
    notify,
    privacy,
    scheduler,
    security,
    speech,
    staff,
    tg_bot,
    vk_bot,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
# httpx пишет в журнал полные URL запросов — в адресе Bot API есть токен, поэтому только предупреждения.
logging.getLogger("httpx").setLevel(logging.WARNING)
WEB = config.ROOT / "web"
basic_auth = HTTPBasic(auto_error=False)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await db.open_pool()
    await db.apply_schema()
    tasks = [asyncio.create_task(job()) for job in (scheduler.loop, max_bot.run, tg_bot.run, vk_bot.run)]
    yield
    for task in tasks:
        task.cancel()
    await db.close_pool()


# Документация API (/docs, /openapi.json) в бою отключена: карта методов не нужна посторонним.
app = FastAPI(title=config.PROJECT_NAME, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    for name, value in security.security_headers(request.url.path).items():
        response.headers.setdefault(name, value)
    return response


OWNER = {"name": "Владелец", "role": "owner"}


async def require_admin(request: Request, creds: Annotated[HTTPBasicCredentials | None, Depends(basic_auth)]) -> dict:
    """Вход в кабинет: владелец (пароль из .env) или сотрудник по логину и PIN-коду (хеш scrypt).
    Пароль не задан — вход закрыт; после 10 неверных попыток за 15 минут IP блокируется."""
    if not config.ADMIN_PASSWORD:
        raise HTTPException(503, "Пароль кабинета не настроен")
    ip = security.client_ip(request)
    if security.LOGIN_FAILS.blocked(ip):
        raise HTTPException(429, "Слишком много неудачных попыток входа. Подождите 15 минут.")
    if creds is not None and secrets.compare_digest(creds.username, config.ADMIN_USER) and secrets.compare_digest(
        creds.password, config.ADMIN_PASSWORD
    ):
        return OWNER
    if creds is not None:
        user = await staff.employee_login(creds.username, creds.password)
        if user:
            return user
        security.LOGIN_FAILS.allow(ip)
    raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})


async def require_full(user: Annotated[dict, Depends(require_admin)]) -> dict:
    """Клиенты, рассылки, сотрудники, ПДн — только управляющий и администратор."""
    if user["role"] not in staff.FULL_ACCESS:
        raise HTTPException(403, "Недостаточно прав")
    return user


ADMIN = [Depends(require_admin)]
FULL = [Depends(require_full)]


# ---------- веб-эмулятор чата гостя (тот же движок, что и в MAX) ----------

class ChatIn(BaseModel):
    uid: int = Field(lt=0, description="Идентификатор гостя веб-чата (выдаёт сервер)")
    sig: str = Field(max_length=64, description="Подпись идентификатора")
    name: str | None = Field(default=None, max_length=60)
    text: str | None = Field(default=None, max_length=2000)
    payload: str | None = Field(default=None, max_length=1024)
    phone: str | None = Field(default=None, max_length=30)


def _web_guard(request: Request, uid: int, sig: str, limiter: security.RateLimiter = security.CHAT_IP) -> None:
    if not security.verify(uid, sig):
        raise HTTPException(403, "Сессия чата недействительна — обновите страницу")
    if not limiter.allow(security.client_ip(request)):
        raise HTTPException(429, "Слишком много сообщений. Подождите минуту.")


@app.post("/api/chat/session")
async def chat_session(request: Request):
    """Новая сессия веб-чата: сервер выдаёт идентификатор гостя и подпись."""
    if not security.CHAT_IP.allow(security.client_ip(request)):
        raise HTTPException(429, "Слишком много запросов. Подождите минуту.")
    uid, sig = security.new_web_session()
    return {"uid": uid, "sig": sig}


@app.post("/api/chat")
async def chat(inp: ChatIn, request: Request):
    _web_guard(request, inp.uid, inp.sig)
    guest = await guests.by_channel(inp.uid, inp.name)
    inp.text = (inp.text or "").strip() or None
    if not (inp.text or inp.payload or inp.phone):
        outs = await dialog.handle(guest, payload="menu")
    else:
        outs = await dialog.handle(guest, text=inp.text, payload=inp.payload, phone=inp.phone)
    return {"messages": [o.as_dict() for o in outs]}


class ConsentIn(BaseModel):
    uid: int = Field(lt=0)
    sig: str = Field(max_length=64)
    pd: bool
    ads: bool = False


@app.post("/api/chat/consent")
async def chat_consent(inp: ConsentIn, request: Request):
    """Согласия, отмеченные гостем перед началом чата на сайте (канал web, текущая версия текстов)."""
    _web_guard(request, inp.uid, inp.sig)
    if not inp.pd:
        raise HTTPException(400, "Без согласия на обработку персональных данных чат недоступен")
    guest = await guests.by_channel(inp.uid)
    await guests.add_consent(guest["id"], "pd", True, channel="web")
    await guests.add_consent(guest["id"], "ads", inp.ads, channel="web")
    return {"ok": True}


@app.get("/api/public/spaces")
async def public_spaces():
    rows = await db.query(
        """SELECT s.id, s.code, s.name, s.description, count(p.id) AS programs,
                  min(COALESCE(p.price, p.price_couple)) AS min_price
           FROM spaces s JOIN programs p ON p.space_id = s.id AND p.active
           GROUP BY s.id ORDER BY s.sort"""
    )
    return {"spaces": rows}


@app.post("/api/chat/voice")
async def chat_voice(uid: int, sig: str, request: Request):
    """Голосовое из чата на сайте: тело запроса — аудио (webm/ogg), до 10 МБ."""
    _web_guard(request, uid, sig, security.VOICE_IP)
    audio = await request.body()
    if len(audio) > speech.MAX_BYTES:
        raise HTTPException(413, "Слишком длинное сообщение")
    guest = await guests.by_channel(uid)
    outs = await dialog.handle_voice(guest, audio, "voice.webm")
    return {"messages": [o.as_dict() for o in outs]}


@app.get("/api/chat/inbox")
async def chat_inbox(uid: int, sig: str):
    if not security.verify(uid, sig):
        return {"messages": []}
    guest = await db.query_one("SELECT id FROM guests WHERE max_user_id = %s", (uid,))
    if not guest or uid >= 0:
        return {"messages": []}
    items = notify.web_inbox.pop(guest["id"], [])
    return {"messages": items}


@app.get("/api/health")
async def health():
    return {"ok": True, "ai": ai.provider(), "channels": notify.active_channels()}


# ---------- администратор ----------

@app.get("/api/admin/grid", dependencies=ADMIN)
async def admin_grid(day: date | None = None):
    day = day or booking.now().date()
    spaces = await db.query("SELECT id, name, is_relax FROM spaces ORDER BY sort")
    masters = await db.query("SELECT id, name FROM masters WHERE active ORDER BY id")
    items = await booking.day_bookings(day)
    return {"day": day.isoformat(), "now": booking.now().isoformat(), "spaces": spaces, "masters": masters, "bookings": items}


@app.get("/api/admin/stream", dependencies=ADMIN)
async def admin_stream():
    queue = events.subscribe()

    async def gen():
        try:
            yield "event: hello\ndata: ok\n\n"
            while True:
                try:
                    kind = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"event: change\ndata: {kind}\n\n"
                except TimeoutError:
                    yield ": ping\n\n"
        finally:
            events.unsubscribe(queue)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/api/admin/catalog", dependencies=ADMIN)
async def admin_catalog():
    programs = await db.query(
        "SELECT p.*, s.name AS space_name FROM programs p JOIN spaces s ON s.id = p.space_id WHERE p.active ORDER BY s.sort, p.price"
    )
    return {"programs": programs}


@app.get("/api/admin/slots", dependencies=ADMIN)
async def admin_slots(program_id: int, day: date):
    slots = await booking.free_slots_public(program_id, day)
    return {"slots": [s.as_dict() for s in slots]}


class AdminHoldIn(BaseModel):
    program_id: int
    start: datetime
    phone: str = Field(max_length=30)
    name: str | None = Field(default=None, max_length=60)
    master_id: int | None = None


@app.post("/api/admin/hold", dependencies=ADMIN)
async def admin_hold(inp: AdminHoldIn):
    phone = guests.normalize_phone(inp.phone)
    if not phone:
        raise HTTPException(400, "Неверный телефон")
    guest = await db.query_one("SELECT * FROM guests WHERE phone = %s", (phone,))
    if not guest:
        guest = await db.query_one(
            "INSERT INTO guests (phone, name, loyalty_card) VALUES (%s, %s, NULL) RETURNING *", (phone, inp.name)
        )
    try:
        return await booking.create_hold(guest["id"], inp.program_id, inp.start, inp.master_id, "admin")
    except booking.SlotTaken as exc:
        alts = await booking.alternatives(inp.program_id, inp.start)
        raise HTTPException(409, {"message": "Окно занято", "alternatives": [a.as_dict() for a in alts]}) from exc


@app.get("/api/admin/bookings/{booking_id}", dependencies=ADMIN)
async def admin_booking(booking_id: int):
    bk = await booking.get_booking(booking_id)
    await privacy.audit(config.ADMIN_USER, "view_booking", bk["guest_id"], f"бронь №{booking_id}")
    return bk


@app.post("/api/admin/bookings/{booking_id}/confirm", dependencies=ADMIN)
async def admin_confirm(booking_id: int):
    try:
        return await booking.confirm(booking_id)
    except booking.BookingError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/admin/bookings/{booking_id}/cancel", dependencies=ADMIN)
async def admin_cancel(booking_id: int):
    return {"ok": await booking.cancel(booking_id)}


class PaymentIn(BaseModel):
    status: str = Field(pattern="^(unpaid|prepaid|paid|certificate)$")
    method: str | None = Field(default=None, max_length=40)


@app.post("/api/admin/bookings/{booking_id}/payment", dependencies=ADMIN)
async def admin_payment(booking_id: int, inp: PaymentIn):
    await db.query(
        "UPDATE bookings SET payment_status = %s, payment_method = %s WHERE id = %s RETURNING id",
        (inp.status, inp.method, booking_id),
    )
    events.publish("grid")
    return await booking.get_booking(booking_id)


@app.get("/api/admin/escalations", dependencies=ADMIN)
async def admin_escalations():
    items = await escalation.open_list()
    for item in items:
        await privacy.audit(config.ADMIN_USER, "view_dialog", item["guest_id"], f"запрос №{item['id']}")
    return {"items": items}


@app.get("/api/admin/stats", dependencies=ADMIN)
async def admin_stats(days: int = 7):
    return await escalation.self_service_stats(max(1, min(days, 90)))


@app.post("/api/admin/escalations/{esc_id}/accept", dependencies=ADMIN)
async def admin_esc_accept(esc_id: int):
    await escalation.accept(esc_id)
    return {"ok": True}


@app.post("/api/admin/escalations/{esc_id}/close", dependencies=ADMIN)
async def admin_esc_close(esc_id: int):
    await escalation.close(esc_id)
    return {"ok": True}


class ReplyIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@app.post("/api/admin/escalations/{esc_id}/reply", dependencies=ADMIN)
async def admin_esc_reply(esc_id: int, inp: ReplyIn):
    esc = await db.query_one("SELECT guest_id FROM escalations WHERE id = %s", (esc_id,))
    if not esc:
        raise HTTPException(404)
    guest = await guests.get(esc["guest_id"])
    await escalation.accept(esc_id)
    await guests.log(guest["id"], "admin", inp.text)
    await notify.deliver(guest, notify.Out(text=f"Администратор: {inp.text}"))
    events.publish("escalations")
    return {"ok": True}


@app.get("/api/admin/no-answer", dependencies=ADMIN)
async def admin_no_answer():
    return {"items": await scheduler.no_answer_list()}


@app.get("/api/admin/feed", dependencies=ADMIN)
async def admin_feed():
    return {"items": list(reversed(notify.admin_feed))}


@app.get("/api/admin/consumption", dependencies=ADMIN)
async def admin_consumption(day: date | None = None):
    """Расход предзаказов на день — для подготовки чая и добавок."""
    day = day or booking.now().date()
    start, end = booking.day_bounds(day)
    rows = await db.query(
        """SELECT i.name, i.category, sum(bp.qty) AS qty, i.stock FROM booking_preorders bp
           JOIN bookings b ON b.id = bp.booking_id JOIN preorder_items i ON i.id = bp.item_id
           WHERE b.status = 'confirmed' AND b.starts_at >= %s AND b.starts_at < %s
           GROUP BY i.id ORDER BY i.category, i.name""",
        (start, end),
    )
    return {"items": rows}


@app.get("/api/admin/guests", dependencies=ADMIN)
async def admin_guests(q: str = ""):
    like = f"%{q.strip()}%"
    rows = await db.query(
        f"""SELECT g.id, g.name, g.phone, g.birth_date, g.loyalty_card, g.loyalty_points, g.lang,
                  {marketing.LAST_VISIT} AS last_visit,
                  (SELECT count(*) FROM bookings b WHERE b.guest_id = g.id AND b.status = 'completed') AS visits,
                  {marketing.ADS_OK} AS ads_ok
           FROM guests g WHERE g.phone IS NOT NULL AND g.deleted_at IS NULL AND (g.name ILIKE %s OR g.phone LIKE %s)
           ORDER BY g.name LIMIT 100""",
        (like, like),
    )
    await privacy.audit(config.ADMIN_USER, "list_guests", None, f"поиск «{q}», строк: {len(rows)}")
    return {"items": rows}


@app.get("/api/admin/guests/{guest_id}", dependencies=ADMIN)
async def admin_guest_card(guest_id: int):
    card = await privacy.guest_card(guest_id)
    if not card:
        raise HTTPException(404)
    await privacy.audit(config.ADMIN_USER, "view_guest", guest_id)
    return card


@app.get("/api/admin/guests/{guest_id}/export", dependencies=ADMIN)
async def admin_guest_export(guest_id: int):
    data = await privacy.export(guest_id)
    if not data:
        raise HTTPException(404)
    await privacy.audit(config.ADMIN_USER, "export", guest_id, "выгрузка по запросу субъекта ПДн")
    return JSONResponse(
        jsonable_encoder(data), headers={"Content-Disposition": f'attachment; filename="guest-{guest_id}.json"'}
    )


@app.post("/api/admin/guests/{guest_id}/erase", dependencies=ADMIN)
async def admin_guest_erase(guest_id: int):
    done = await privacy.erase(guest_id)
    await privacy.audit(config.ADMIN_USER, "erase", guest_id, "удаление по запросу субъекта ПДн" if done else "уже удалён")
    return {"ok": done}


@app.get("/api/admin/pd-log", dependencies=ADMIN)
async def admin_pd_log():
    return {"items": await privacy.access_log()}


@app.get("/api/admin/marketing/segments", dependencies=ADMIN)
async def mk_segments():
    return {"segments": await marketing.segment_counts(), "history": await marketing.history()}


class CampaignIn(BaseModel):
    segment: str
    template: str = Field(min_length=5, max_length=1500)
    name: str = Field(default="Рассылка", max_length=100)
    goal: str = Field(default="", max_length=300)
    param: str | None = Field(default=None, max_length=40)
    use_ai: bool = False
    texts: dict[int, str] | None = None


def _check_segment(segment: str) -> None:
    if segment not in marketing.SEGMENTS:
        raise HTTPException(400, "Неизвестный сегмент")


@app.post("/api/admin/marketing/preview", dependencies=ADMIN)
async def mk_preview(inp: CampaignIn):
    _check_segment(inp.segment)
    items = await marketing.preview(inp.segment, inp.template, inp.param, inp.goal, inp.use_ai)
    return {"items": items, "ai": ai.enabled()}


@app.post("/api/admin/marketing/send", dependencies=ADMIN)
async def mk_send(inp: CampaignIn):
    _check_segment(inp.segment)
    await privacy.audit(config.ADMIN_USER, "campaign", None, f"рассылка {inp.segment}")
    return await marketing.send(inp.segment, inp.template, inp.name, inp.param, inp.texts)


@app.post("/api/admin/marketing/generate", dependencies=ADMIN)
async def mk_generate(inp: CampaignIn):
    _check_segment(inp.segment)
    return {"template": await marketing.generate_template(inp.segment, inp.goal), "ai": ai.enabled()}


# ---------- график мастеров ----------

@app.get("/api/admin/schedule", dependencies=ADMIN)
async def admin_schedule(start: date | None = None, days: int = 14):
    return await staff.schedule(start or booking.now().date(), max(1, min(days, 31)))


class ShiftIn(BaseModel):
    master_id: int
    day: date
    start: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    end: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    note: str = Field(default="", max_length=100)


def _conflict_view(rows: list[dict]) -> list[dict]:
    return [{"id": r["id"], "starts_at": r["starts_at"], "program_name": r["program_name"], "guest_name": r["guest_name"]} for r in rows]


@app.put("/api/admin/schedule", dependencies=ADMIN)
async def admin_set_shift(inp: ShiftIn):
    try:
        found = await staff.set_shift(inp.master_id, inp.day, inp.start, inp.end, inp.note)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "conflicts": _conflict_view(found)}


class PatternIn(BaseModel):
    master_id: int
    first_day: date
    days: int = Field(default=14, ge=1, le=62)
    pattern: str = Field(pattern=r"^(2/2|5/2|3/1|1/1)$")
    start: str = Field(pattern=r"^\d{2}:\d{2}$")
    end: str = Field(pattern=r"^\d{2}:\d{2}$")


@app.post("/api/admin/schedule/pattern", dependencies=ADMIN)
async def admin_shift_pattern(inp: PatternIn):
    try:
        changed = await staff.apply_pattern(inp.master_id, inp.first_day, inp.days, inp.pattern, inp.start, inp.end)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "changed": changed}


# ---------- чек-листы ----------

@app.get("/api/admin/checklists", dependencies=ADMIN)
async def admin_checklists(day: date | None = None, role: str | None = None):
    return {"items": await staff.checklists(day or booking.now().date(), role or None)}


class TemplateIn(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    role: str = Field(pattern="^(admin|master|cleaning)$")
    kind: str = Field(pattern="^(opening|daily|space|cleanup|closing)$")
    items: list[str] = Field(min_length=1, max_length=40)
    active: bool = True


@app.get("/api/admin/checklist-templates", dependencies=ADMIN)
async def admin_templates():
    return {"items": await staff.templates()}


@app.post("/api/admin/checklist-templates", dependencies=ADMIN)
async def admin_template_create(inp: TemplateIn):
    try:
        return await staff.create_template(inp.title, inp.role, inp.kind, inp.items)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.put("/api/admin/checklist-templates/{template_id}", dependencies=ADMIN)
async def admin_template_update(template_id: int, inp: TemplateIn):
    try:
        return await staff.update_template(template_id, inp.title, inp.role, inp.kind, inp.items, inp.active)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


class ToggleIn(BaseModel):
    index: int = Field(ge=0)
    who: str = Field(default="администратор", max_length=40)


@app.post("/api/admin/checklists/{run_id}/toggle", dependencies=ADMIN)
async def admin_checklist_toggle(run_id: int, inp: ToggleIn):
    try:
        return await staff.toggle(run_id, inp.index, inp.who)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


# ---------- текущий пользователь ----------

@app.get("/api/admin/me")
async def admin_me(user: Annotated[dict, Depends(require_admin)]):
    return {"name": user["name"], "role": user["role"], "tabs": staff.ROLE_TABS.get(user["role"])}


# ---------- клиенты и лояльность ----------

class PeriodFilterIn(BaseModel):
    filters: list[dict] = Field(default_factory=list, max_length=20)
    match: str = Field(default="all", pattern="^(all|any)$")
    date_from: date | None = None
    date_to: date | None = None


@app.get("/api/admin/clients/analytics", dependencies=FULL)
async def clients_analytics(date_from: date | None = None, date_to: date | None = None):
    return await loyalty.analytics(date_from, date_to)


@app.post("/api/admin/clients/search", dependencies=FULL)
async def clients_search(inp: PeriodFilterIn):
    try:
        rows = await loyalty.clients(inp.filters, inp.date_from, inp.date_to, limit=300, match=inp.match)
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc
    await privacy.audit(config.ADMIN_USER, "list_guests", None, f"клиенты по фильтру, строк: {len(rows)}")
    return {"items": rows}


@app.get("/api/admin/filter-fields", dependencies=FULL)
async def filter_fields():
    return {
        "fields": [{"key": k, "label": v[2], "type": v[1]} for k, v in loyalty.FIELDS.items()],
        "operators": loyalty.OPERATORS,
        "variables": automations.VARIABLES,
        "reply_buttons": automations.REPLY_BUTTONS,
        "triggers": automations.TRIGGERS,
        "actions": automations.ACTIONS,
    }


class BonusIn(BaseModel):
    delta: int = Field(ge=-100000, le=100000)
    note: str = Field(default="корректировка", max_length=200)


@app.post("/api/admin/guests/{guest_id}/bonus", dependencies=FULL)
async def guest_bonus(guest_id: int, inp: BonusIn):
    return {"balance": await loyalty.add_bonus(guest_id, inp.delta, "adjust", inp.note)}


class VisitIn(BaseModel):
    attended: bool
    paid: int | None = Field(default=None, ge=0)
    bonus_spent: int = Field(default=0, ge=0)


@app.post("/api/admin/bookings/{booking_id}/visit", dependencies=ADMIN)
async def booking_visit(booking_id: int, inp: VisitIn):
    try:
        return await loyalty.mark_visit(booking_id, inp.attended, inp.paid, inp.bonus_spent)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


# ---------- рассылки (конструктор) и автоматизации ----------

class CampaignBuildIn(BaseModel):
    name: str = Field(default="Рассылка", max_length=100)
    filters: list[dict] = Field(default_factory=list, max_length=20)
    template: str = Field(min_length=3, max_length=2000)
    buttons: list[dict] = Field(default_factory=list, max_length=5)
    scheduled_at: datetime | None = None


@app.post("/api/admin/campaigns/preview", dependencies=FULL)
async def campaign_preview(inp: CampaignBuildIn):
    try:
        return await automations.preview(inp.filters, inp.template)
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/admin/campaigns", dependencies=FULL)
async def campaign_create(inp: CampaignBuildIn):
    try:
        row = await automations.save_campaign(inp.name, inp.filters, inp.template, inp.buttons, inp.scheduled_at)
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc
    await privacy.audit(config.ADMIN_USER, "campaign", None, f"рассылка «{inp.name}»")
    return row


@app.get("/api/admin/campaigns", dependencies=FULL)
async def campaign_history():
    return {"items": await db.query(
        """SELECT c.id, c.name, c.status, c.scheduled_at, c.sent_at, c.created_at,
                  (SELECT count(*) FROM outbox o WHERE o.campaign_id = c.id) AS sent
           FROM campaigns c ORDER BY c.id DESC LIMIT 50""")}


class AutomationIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    trigger: str
    days: int = Field(default=0, ge=0, le=365)
    filters: list[dict] = Field(default_factory=list, max_length=20)
    match: str = Field(default="all", pattern="^(all|any)$")
    actions: list[str] = Field(default_factory=list, max_length=6)
    action: str | None = None
    staff_message: str = Field(default="", max_length=500)
    bonus_amount: int = Field(default=0, ge=0, le=100000)
    bonus_days: int = Field(default=14, ge=1, le=365)
    message: str = Field(default="", max_length=1500)
    segment: str = Field(default="", max_length=60)
    active: bool = True


@app.get("/api/admin/automations", dependencies=FULL)
async def automation_list():
    return {"items": await automations.listing()}


@app.post("/api/admin/automations", dependencies=FULL)
async def automation_create(inp: AutomationIn):
    try:
        return await automations.save(inp.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.put("/api/admin/automations/{auto_id}", dependencies=FULL)
async def automation_update(auto_id: int, inp: AutomationIn):
    try:
        return await automations.save(inp.model_dump(), auto_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/admin/automations/run", dependencies=FULL)
async def automation_run():
    return {"done": await automations.run_all()}


# ---------- сертификаты ----------

class CertificateIn(BaseModel):
    number: str = Field(min_length=3, max_length=40)
    amount: int = Field(gt=0, le=1000000)
    kind: str = Field(default="nominal", pattern="^(nominal|program)$")
    program_name: str | None = Field(default=None, max_length=120)
    buyer_name: str = Field(default="", max_length=120)
    buyer_phone: str = Field(default="", max_length=30)
    owner_name: str = Field(default="", max_length=120)
    valid_days: int = Field(default=180, ge=1, le=1100)


class RedeemIn(BaseModel):
    amount: int = Field(gt=0)
    booking_id: int | None = None
    note: str = Field(default="", max_length=200)


@app.get("/api/admin/certificates", dependencies=ADMIN)
async def certificate_list(status: str | None = None):
    return await certificates.listing(status)


@app.post("/api/admin/certificates", dependencies=ADMIN)
async def certificate_issue(inp: CertificateIn, user: Annotated[dict, Depends(require_admin)]):
    try:
        return await certificates.issue(inp.number, inp.amount, inp.kind, inp.program_name, inp.buyer_name,
                                        inp.buyer_phone, inp.owner_name, inp.valid_days, user["name"])
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/admin/certificates/{number}", dependencies=ADMIN)
async def certificate_get(number: str):
    cert = await certificates.find(number)
    if not cert:
        raise HTTPException(404, "Сертификат не найден")
    return cert


@app.post("/api/admin/certificates/{number}/redeem", dependencies=ADMIN)
async def certificate_redeem(number: str, inp: RedeemIn, user: Annotated[dict, Depends(require_admin)]):
    try:
        return await certificates.redeem(number, inp.amount, inp.booking_id, user["name"], inp.note)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/admin/certificates/{number}/cancel", dependencies=FULL)
async def certificate_cancel(number: str, user: Annotated[dict, Depends(require_admin)]):
    try:
        return await certificates.cancel(number, user["name"])
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


# ---------- сотрудники ----------

class EmployeeIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    phone: str | None = Field(default=None, max_length=30)
    position: str = Field(pattern="^(manager|admin|master|cleaning)$")
    skills: str = Field(default="", max_length=120)
    login: str | None = Field(default=None, max_length=40, pattern=r"^[a-zA-Z0-9_.-]*$")
    pin: str | None = Field(default=None, max_length=12, pattern=r"^\d{0,12}$")
    active: bool = True


@app.get("/api/admin/employees", dependencies=FULL)
async def employee_list():
    return {"items": await staff.employees(), "positions": staff.POSITIONS}


@app.post("/api/admin/employees", dependencies=FULL)
async def employee_create(inp: EmployeeIn):
    try:
        return await staff.save_employee(inp.model_dump())
    except (ValueError, errors.UniqueViolation) as exc:
        raise HTTPException(400, "Логин уже занят" if isinstance(exc, errors.UniqueViolation) else str(exc)) from exc


@app.put("/api/admin/employees/{emp_id}", dependencies=FULL)
async def employee_update(emp_id: int, inp: EmployeeIn):
    try:
        return await staff.save_employee(inp.model_dump(), emp_id)
    except (ValueError, errors.UniqueViolation) as exc:
        raise HTTPException(400, "Логин уже занят" if isinstance(exc, errors.UniqueViolation) else str(exc)) from exc


@app.post("/api/admin/jobs/{name}", dependencies=ADMIN)
async def run_job(name: str):
    """Ручной запуск ежедневной задачи (для демонстрации и проверки)."""
    job = scheduler.JOBS_BY_NAME.get(name)
    if not job:
        raise HTTPException(404)
    return {"result": await job()}


# ---------- статика ----------

app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/")
async def index():
    return FileResponse(WEB / "index.html")


@app.get("/links")
async def links_page():
    return FileResponse(WEB / "links.html")


@app.get("/legal")
async def legal_page():
    return FileResponse(WEB / "legal.html")


@app.get("/admin", dependencies=ADMIN)
async def admin_page():
    return FileResponse(WEB / "admin.html")
