"""Маркетинговый модуль: сценарии и сегменты базы гостей, предпросмотр, рассылка, отписка.

Сообщения получают только гости с действующим согласием на рекламные сообщения.
Тексты: шаблон с переменными или персональная генерация моделью по данным гостя — всегда через предпросмотр.
"""
from . import ai, db, events, guests, notify

ADS_OK = """EXISTS (SELECT 1 FROM consents c WHERE c.guest_id = g.id AND c.kind = 'ads' AND c.granted
              AND c.created_at = (SELECT max(created_at) FROM consents c2 WHERE c2.guest_id = g.id AND c2.kind = 'ads'))"""

LAST_VISIT = "(SELECT max(b.starts_at) FROM bookings b WHERE b.guest_id = g.id AND b.status = 'completed')"
VISITS = "(SELECT count(*) FROM bookings b WHERE b.guest_id = g.id AND b.status = 'completed')"
SPENT = "(SELECT COALESCE(sum(b.price_total), 0) FROM bookings b WHERE b.guest_id = g.id AND b.status = 'completed')"
LAST_PROGRAM = """(SELECT p.name FROM bookings b JOIN programs p ON p.id = b.program_id
                   WHERE b.guest_id = g.id AND b.status = 'completed' ORDER BY b.starts_at DESC LIMIT 1)"""
FAVORITE_SPACE = """(SELECT s.code FROM bookings b JOIN spaces s ON s.id = b.space_id
                     WHERE b.guest_id = g.id AND b.status = 'completed'
                     GROUP BY s.code ORDER BY count(*) DESC, max(b.starts_at) DESC LIMIT 1)"""
NO_FUTURE = "NOT EXISTS (SELECT 1 FROM bookings b WHERE b.guest_id = g.id AND b.status = 'confirmed' AND b.starts_at > now())"
BIRTHDAY_THIS_YEAR = """make_date(extract(year FROM current_date)::int, extract(month FROM g.birth_date)::int,
                                  LEAST(extract(day FROM g.birth_date)::int, 28))"""

SEGMENTS = {
    "birthday_soon": {
        "title": "День рождения через 5–7 дней",
        "where": f"{BIRTHDAY_THIS_YEAR} BETWEEN current_date + 5 AND current_date + 7",
        "param": None,
        "template": "{name}, скоро ваш день рождения! В этот день у нас скидка 25% на СПА-услуги и 1000 подарочных баллов. Подберу для вас время — просто напишите.",
    },
    "lapsed": {
        "title": "Реактивация: нет визитов N дней",
        "where": f"{LAST_VISIT} < now() - make_interval(days => %(p)s) AND {NO_FUTURE}",
        "param": {"label": "Дней без визитов", "default": 90, "type": "int"},
        "template": "{name}, давно вас не видели. Помните «{last_program}»? Если захочется повторить — я подберу свободное время.",
    },
    "favorite_space": {
        "title": "Анонс: любимое пространство",
        "where": f"{FAVORITE_SPACE} = %(p)s",
        "param": {"label": "Пространство", "default": "japan", "type": "space"},
        "template": "{name}, для гостей, которые любят это пространство, у нас новости. Напишите — расскажу и помогу записаться.",
    },
    "spend": {
        "title": "Анонс: сумма трат от N ₽",
        "where": f"{SPENT} >= %(p)s",
        "param": {"label": "Сумма трат от, ₽", "default": 10000, "type": "int"},
        "template": "{name}, спасибо, что выбираете СПА-парк. Для постоянных гостей мы подготовили предложение — напишите, расскажу подробнее.",
    },
    "after_visit": {
        "title": "После визита (были вчера)",
        "where": """EXISTS (SELECT 1 FROM bookings b WHERE b.guest_id = g.id AND b.status = 'completed'
                    AND b.ends_at >= current_date - 1 AND b.ends_at < current_date)""",
        "param": None,
        "template": "{name}, спасибо, что были у нас. Будем рады видеть вас снова — я подберу время, когда захотите.",
    },
    "abandoned": {
        "title": "Брошенная бронь (захват истёк за сутки)",
        "where": f"""EXISTS (SELECT 1 FROM bookings b WHERE b.guest_id = g.id AND b.status = 'expired'
                    AND b.source = 'bot' AND b.hold_expires_at > now() - interval '1 day') AND {NO_FUTURE}""",
        "param": None,
        "template": "{name}, вы выбирали время, но запись не завершилась. Окно могло освободиться снова — подобрать?",
    },
    "all": {
        "title": "Все с согласием на рассылку",
        "where": "true",
        "param": None,
        "template": "{name}, в СПА-парке новости. Напишите мне — расскажу и помогу записаться.",
    },
}


def _param(segment: str, value) -> object:
    spec = SEGMENTS[segment]["param"]
    if spec is None:
        return None
    if value in (None, ""):
        return spec["default"]
    return int(value) if spec["type"] == "int" else str(value)


async def segment_guests(segment: str, param=None) -> list[dict]:
    seg = SEGMENTS[segment]
    sql = f"""SELECT g.id, g.name, g.phone, g.max_user_id, g.lang, {LAST_VISIT} AS last_visit,
                     {LAST_PROGRAM} AS last_program, {VISITS} AS visits, {SPENT} AS spent
              FROM guests g WHERE g.phone IS NOT NULL AND g.deleted_at IS NULL AND {ADS_OK} AND ({seg['where']})
              ORDER BY g.name"""
    return await db.query(sql, {"p": _param(segment, param)})


async def segment_counts() -> list[dict]:
    out = []
    for key, seg in SEGMENTS.items():
        rows = await segment_guests(key)
        out.append({"key": key, "title": seg["title"], "count": len(rows), "template": seg["template"], "param": seg["param"]})
    return out


def render(template: str, guest: dict) -> str:
    values = {
        "{name}": guest.get("name") or "Здравствуйте",
        "{last_program}": guest.get("last_program") or "ваш прошлый визит",
    }
    text = template
    for key, value in values.items():
        text = text.replace(key, value)
    return text


async def personalize(template: str, guest: dict, goal: str) -> str:
    """Персональный текст от модели по шаблону и данным гостя. Без модели — шаблон."""
    prompt = (
        "Перепиши сообщение рассылки спа-центра «СПА-парк» под конкретного гостя. "
        "Тон спокойный, премиальный, на «вы», без давления и обилия эмодзи, 2–3 предложения. "
        "Не придумывай скидок, цен и акций, которых нет в шаблоне.\n"
        f"Цель: {goal or 'пригласить снова'}\nШаблон: {render(template, guest)}\n"
        f"Данные гостя: имя {guest.get('name')}, визитов {guest.get('visits')}, последняя программа {guest.get('last_program')}.\n"
        "Верни только текст."
    )
    return await ai.generate_text(prompt, max_tokens=300) or render(template, guest)


async def preview(segment: str, template: str, param=None, goal: str = "", use_ai: bool = False) -> list[dict]:
    rows = await segment_guests(segment, param)
    out = []
    for g in rows[:50]:
        text = await personalize(template, g, goal) if use_ai and ai.enabled() else render(template, g)
        out.append({"guest_id": g["id"], "name": g["name"], "phone": g["phone"], "text": text})
    return out


def _message(text: str) -> notify.Out:
    footer = "\n\nОтписаться: напишите «отписаться»."
    return notify.Out(text=text + footer, buttons=[[("Записаться", "book"), ("Отписаться", "unsub")]])


async def _dispatch(rows: list[dict], segment: str, template: str, name: str, texts: dict[int, str]) -> dict:
    campaign = await db.query_one(
        "INSERT INTO campaigns (name, segment, template, status, sent_at) VALUES (%s,%s,%s,'sent', now()) RETURNING id",
        (name, segment, template),
    )
    sent = 0
    for guest in rows:
        full = await guests.get(guest["id"])
        text = texts.get(guest["id"]) or render(template, guest)
        sent += int(await notify.to_guest(full, _message(text), "campaign", campaign_id=campaign["id"]))
    events.publish("campaigns")
    return {"campaign_id": campaign["id"], "sent": sent, "total": len(rows)}


async def send(segment: str, template: str, name: str, param=None, texts: dict[int, str] | None = None) -> dict:
    """Рассылка по сегменту. texts — проверенные в предпросмотре персональные тексты (guest_id → текст)."""
    return await _dispatch(await segment_guests(segment, param), segment, template, name, texts or {})


async def send_to(segment: str, template: str, name: str, guest_ids: list[int], texts: dict[int, str]) -> dict:
    """Рассылка выбранным гостям сегмента (автосценарии с защитой от повторов)."""
    wanted = set(guest_ids)
    rows = [g for g in await segment_guests(segment) if g["id"] in wanted]
    return await _dispatch(rows, segment, template, name, texts)


async def generate_template(segment: str, goal: str) -> str:
    """Шаблон рассылки от модели. Без модели — базовый шаблон сегмента."""
    seg = SEGMENTS[segment]
    prompt = (
        "Ты пишешь сообщение рассылки для спа-центра «СПА-парк» (Нижневартовск) в мессенджере MAX.\n"
        f"Сегмент: {seg['title']}. Цель: {goal or 'вернуть гостя и предложить записаться'}.\n"
        "Тон: спокойный, премиальный, на «вы», без давления, канцелярита и обилия эмодзи. 2–3 предложения.\n"
        "Не придумывай скидки, цены и акции. Используй переменные {name} и при необходимости {last_program}.\n"
        "Верни только текст сообщения."
    )
    return await ai.generate_text(prompt) or seg["template"]


async def history() -> list[dict]:
    return await db.query(
        """SELECT c.*, (SELECT count(*) FROM outbox o WHERE o.campaign_id = c.id) AS sent
           FROM campaigns c ORDER BY c.id DESC LIMIT 20"""
    )
