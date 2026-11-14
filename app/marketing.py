"""Маркетинговый модуль: сегменты базы гостей, предпросмотр и рассылка.

Сообщения получают только гости с действующим согласием на рекламные сообщения.
"""
from . import ai, db, events, guests, notify

ADS_OK = """EXISTS (SELECT 1 FROM consents c WHERE c.guest_id = g.id AND c.kind = 'ads' AND c.granted
              AND c.created_at = (SELECT max(created_at) FROM consents c2 WHERE c2.guest_id = g.id AND c2.kind = 'ads'))"""

LAST_VISIT = """(SELECT max(b.starts_at) FROM bookings b WHERE b.guest_id = g.id AND b.status = 'completed')"""
LAST_PROGRAM = """(SELECT p.name FROM bookings b JOIN programs p ON p.id = b.program_id
                   WHERE b.guest_id = g.id AND b.status = 'completed' ORDER BY b.starts_at DESC LIMIT 1)"""
NO_FUTURE = """NOT EXISTS (SELECT 1 FROM bookings b WHERE b.guest_id = g.id AND b.status = 'confirmed' AND b.starts_at > now())"""

BIRTHDAY_IN = """make_date(extract(year FROM now())::int, extract(month FROM g.birth_date)::int,
                           LEAST(extract(day FROM g.birth_date)::int, 28)) """

SEGMENTS = {
    "birthday_today": {
        "title": "Именинники сегодня",
        "where": "to_char(g.birth_date, 'MM-DD') = to_char(now() AT TIME ZONE 'Asia/Yekaterinburg', 'MM-DD')",
        "template": "{name}, с днём рождения! Пусть этот год будет тёплым и спокойным. В течение недели дарим вам комплимент к любой программе — просто напишите мне, и я подберу время.",
    },
    "birthday_week": {
        "title": "День рождения в ближайшие 7 дней",
        "where": f"{BIRTHDAY_IN} BETWEEN current_date AND current_date + 7",
        "template": "{name}, скоро ваш день рождения! Подарите себе время для отдыха — я помогу выбрать программу и удобное время.",
    },
    "lapsed_90": {
        "title": "Не были больше 90 дней",
        "where": f"{LAST_VISIT} < now() - interval '90 days' AND {NO_FUTURE}",
        "template": "{name}, давно вас не видели. Помните «{last_program}»? Если захочется повторить — я подберу свободное время.",
    },
    "active": {
        "title": "Были за последние 90 дней",
        "where": f"{LAST_VISIT} >= now() - interval '90 days'",
        "template": "{name}, спасибо, что выбираете СПА-парк. Рады рассказать о новых программах — напишите, если интересно.",
    },
    "all": {
        "title": "Все с согласием на рассылку",
        "where": "true",
        "template": "{name}, в СПА-парке новые программы. Напишите мне — расскажу и помогу записаться.",
    },
}


async def segment_guests(segment: str) -> list[dict]:
    seg = SEGMENTS[segment]
    sql = f"""SELECT g.id, g.name, g.phone, g.max_user_id, g.lang, {LAST_VISIT} AS last_visit,
                     {LAST_PROGRAM} AS last_program
              FROM guests g WHERE g.phone IS NOT NULL AND {ADS_OK} AND ({seg['where']})
              ORDER BY g.name"""
    return await db.query(sql)


async def segment_counts() -> list[dict]:
    out = []
    for key, seg in SEGMENTS.items():
        rows = await segment_guests(key)
        out.append({"key": key, "title": seg["title"], "count": len(rows), "template": seg["template"]})
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


async def preview(segment: str, template: str) -> list[dict]:
    rows = await segment_guests(segment)
    return [{"guest_id": g["id"], "name": g["name"], "phone": g["phone"], "text": render(template, g)} for g in rows]


async def send(segment: str, template: str, name: str) -> dict:
    rows = await segment_guests(segment)
    campaign = await db.query_one(
        "INSERT INTO campaigns (name, segment, template, status, sent_at) VALUES (%s,%s,%s,'sent', now()) RETURNING id",
        (name, segment, template),
    )
    sent = 0
    for guest in rows:
        full = await guests.get(guest["id"])
        ok = await notify.to_guest(full, notify.Out(text=render(template, guest), buttons=[[("Записаться", "book")]]), "campaign", campaign_id=campaign["id"])
        sent += int(ok)
    events.publish("campaigns")
    return {"campaign_id": campaign["id"], "sent": sent, "total": len(rows)}


async def generate_template(segment: str, goal: str) -> str:
    """Текст рассылки от модели по шаблону сегмента. Без модели — базовый шаблон."""
    seg = SEGMENTS[segment]
    prompt = (
        "Ты пишешь сообщение рассылки для спа-центра «СПА-парк» (Нижневартовск) в мессенджере MAX.\n"
        f"Сегмент: {seg['title']}. Цель: {goal or 'вернуть гостя и предложить записаться'}.\n"
        "Тон: спокойный, премиальный, на «вы», без давления, канцелярита и обилия эмодзи. 2–3 предложения.\n"
        "Не придумывай скидки, цены и акции. Используй переменные {name} и при необходимости {last_program}.\n"
        "Верни только текст сообщения."
    )
    text = await ai.generate_text(prompt)
    return text or seg["template"]


async def history() -> list[dict]:
    return await db.query(
        """SELECT c.*, (SELECT count(*) FROM outbox o WHERE o.campaign_id = c.id) AS sent
           FROM campaigns c ORDER BY c.id DESC LIMIT 20"""
    )
