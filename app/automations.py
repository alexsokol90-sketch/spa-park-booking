"""Автоматизации маркетинга и конструктор рассылок.

Автоматизация: событие (день рождения через N дней, N дней после визита, нет визитов N дней, регистрация)
+ условия (те же фильтры, что в рассылках) → действие (начислить бонусы со сроком, отправить сообщение,
добавить в сегмент / убрать из сегмента). Каждое срабатывание для гостя фиксируется — повторов не будет.
Рекламные сообщения уходят только гостям с согласием на рекламу.
"""
import json
from datetime import date, datetime

from . import config, db, events, guests, loyalty, notify

TRIGGERS = {
    "birthday_before": "За N дней до дня рождения",
    "after_visit": "Через N дней после визита",
    "inactive": "Нет визитов N дней",
    "registration": "После регистрации",
}
ACTIONS = {"bonus": "Начислить бонусы", "message": "Отправить сообщение", "segment_add": "Добавить в сегмент",
           "segment_remove": "Удалить из сегмента"}
# Кнопки рассылок: текстовые ответы ведут в сценарии бота.
REPLY_BUTTONS = {"book": "Записаться", "invite": "Пригласить друга", "bonuses": "Мои бонусы", "faq:promo": "Акции"}
VARIABLES = {
    "{name}": "имя", "{surname}": "фамилия", "{bonuses}": "бонусы клиента",
    "{referral_code}": "реферальный промокод", "{referral_link}": "реферальная ссылка",
}


def referral_link(code: str) -> str:
    return f"https://max.ru/id860333297559_bot?start=ref_{code}"


async def render(template: str, client: dict) -> str:
    code = client.get("referral_code") or await loyalty.ensure_referral_code(client["id"])
    values = {
        "{name}": client.get("name") or "Здравствуйте",
        "{surname}": client.get("surname") or "",
        "{bonuses}": str(client.get("bonus_balance") or 0),
        "{referral_code}": code,
        "{referral_link}": referral_link(code),
        "{last_program}": client.get("last_program") or "ваш прошлый визит",
    }
    text = template
    for key, value in values.items():
        text = text.replace(key, value)
    return " ".join(text.split(" ")).strip()


def build_out(text: str, buttons: list[dict]) -> notify.Out:
    link, rows = None, []
    for btn in buttons or []:
        title = str(btn.get("text") or "")[:40]
        if btn.get("type") == "link" and btn.get("url") and not link:
            link = (title or "Открыть", str(btn["url"])[:500])
        elif btn.get("type") == "reply" and btn.get("payload") in REPLY_BUTTONS:
            rows.append([(title or REPLY_BUTTONS[btn["payload"]], btn["payload"])])
    rows.append([("Отписаться", "unsub")])
    return notify.Out(text=text + "\n\nОтписаться: напишите «отписаться».", buttons=rows, link=link)


# ---------- конструктор рассылок ----------

async def audience(filters: list[dict]) -> list[dict]:
    return await loyalty.clients(filters, only_ads=True, limit=5000)


async def preview(filters: list[dict], template: str, limit: int = 20) -> dict:
    rows = await audience(filters)
    return {
        "total": len(rows),
        "items": [{"name": r["name"], "phone": r["phone"], "text": await render(template, r)} for r in rows[:limit]],
    }


async def save_campaign(name: str, filters: list[dict], template: str, buttons: list[dict],
                        scheduled_at: datetime | None) -> dict:
    status = "scheduled" if scheduled_at else "draft"
    row = await db.query_one(
        """INSERT INTO campaigns (name, segment, template, filters, buttons, scheduled_at, status)
           VALUES (%s, 'constructor', %s, %s, %s, %s, %s) RETURNING *""",
        (name, template, json.dumps(filters, ensure_ascii=False), json.dumps(buttons, ensure_ascii=False), scheduled_at, status),
    )
    if not scheduled_at:
        await send_campaign(row["id"])
    return row


async def send_campaign(campaign_id: int) -> int:
    camp = await db.query_one(
        "UPDATE campaigns SET status = 'sent', sent_at = now() WHERE id = %s AND status <> 'sent' RETURNING *", (campaign_id,)
    )
    if not camp:
        return 0
    sent = 0
    for client in await audience(camp["filters"]):
        guest = await guests.get(client["id"])
        out = build_out(await render(camp["template"], client), camp["buttons"])
        sent += int(await notify.to_guest(guest, out, "campaign", campaign_id=campaign_id))
    events.publish("campaigns")
    return sent


async def send_due_campaigns() -> int:
    due = await db.query("SELECT id FROM campaigns WHERE status = 'scheduled' AND scheduled_at <= now()")
    return sum([await send_campaign(c["id"]) for c in due])


# ---------- автоматизации ----------

def _trigger_sql(trigger: str) -> str:
    """Отбор гостей по событию; %(days)s — параметр автоматизации, ключ повтора — run_key."""
    if trigger == "birthday_before":
        return """SELECT c.id, extract(year FROM current_date)::text AS run_key FROM clients c
                  WHERE c.birth_date IS NOT NULL AND make_date(extract(year FROM current_date)::int,
                        extract(month FROM c.birth_date)::int, LEAST(extract(day FROM c.birth_date)::int, 28))
                        BETWEEN current_date AND current_date + %(days)s"""
    if trigger == "after_visit":
        return """SELECT c.id, c.last_purchase::date::text AS run_key FROM clients c
                  WHERE c.last_purchase IS NOT NULL AND c.last_purchase::date = current_date - %(days)s"""
    if trigger == "inactive":
        return """SELECT c.id, c.last_purchase::date::text AS run_key FROM clients c
                  WHERE c.last_purchase < now() - make_interval(days => %(days)s)"""
    return """SELECT c.id, 'reg' AS run_key FROM clients c WHERE c.registered_at > now() - interval '1 day'"""


async def _candidates(auto: dict) -> list[dict]:
    params = loyalty.period(None, None) | {"days": auto["days"]}
    where = [loyalty.condition(i, f, params) for i, f in enumerate(auto["filters"] or [])]
    sql = loyalty.CLIENTS_CTE + "SELECT t.id, t.run_key FROM (" + _trigger_sql(auto["trigger"]) + ") t"
    if where:
        sql += " JOIN clients c ON c.id = t.id WHERE " + " AND ".join(where)
    return await db.query(sql, params)


async def _act(auto: dict, guest_id: int) -> bool:
    if auto["action"] == "bonus":
        await loyalty.gift(guest_id, auto["bonus_amount"], auto["bonus_days"], auto["name"])
    elif auto["action"] == "segment_add":
        await db.query(
            "INSERT INTO guest_segments (guest_id, segment) VALUES (%s, %s) ON CONFLICT DO NOTHING RETURNING guest_id",
            (guest_id, auto["segment"]),
        )
    elif auto["action"] == "segment_remove":
        await db.query("DELETE FROM guest_segments WHERE guest_id = %s AND segment = %s RETURNING guest_id", (guest_id, auto["segment"]))
    client = await loyalty.client(guest_id)
    if auto["message"] and client and client["ads_ok"]:
        text = await render(auto["message"], client)
        await notify.to_guest(await guests.get(guest_id), build_out(text, [{"type": "reply", "payload": "book"}]), "automation")
    return True


async def run_automation(auto: dict) -> int:
    done = 0
    for cand in await _candidates(auto):
        claimed = await db.query_one(
            """INSERT INTO automation_runs (automation_id, guest_id, run_key) VALUES (%s, %s, %s)
               ON CONFLICT DO NOTHING RETURNING guest_id""",
            (auto["id"], cand["id"], cand["run_key"] or "-"),
        )
        if claimed and await _act(auto, cand["id"]):
            done += 1
    return done


async def run_all() -> int:
    autos = await db.query("SELECT * FROM automations WHERE active ORDER BY id")
    total = 0
    for auto in autos:
        total += await run_automation(auto)
    events.publish("clients")
    return total


async def listing() -> list[dict]:
    return await db.query(
        """SELECT a.*, (SELECT count(*) FROM automation_runs r WHERE r.automation_id = a.id) AS runs
           FROM automations a ORDER BY a.id"""
    )


async def save(data: dict, auto_id: int | None = None) -> dict:
    if data["trigger"] not in TRIGGERS or data["action"] not in ACTIONS:
        raise ValueError("Неизвестное событие или действие")
    values = (data["name"].strip()[:120], data["trigger"], int(data.get("days") or 0),
              json.dumps(data.get("filters") or [], ensure_ascii=False), data["action"], int(data.get("bonus_amount") or 0),
              int(data.get("bonus_days") or 14), str(data.get("message") or "")[:1500], str(data.get("segment") or "")[:60],
              bool(data.get("active", True)))
    if auto_id:
        return await db.query_one(
            """UPDATE automations SET name=%s, trigger=%s, days=%s, filters=%s, action=%s, bonus_amount=%s, bonus_days=%s,
                   message=%s, segment=%s, active=%s WHERE id=%s RETURNING *""",
            (*values, auto_id),
        )
    return await db.query_one(
        """INSERT INTO automations (name, trigger, days, filters, action, bonus_amount, bonus_days, message, segment, active)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        values,
    )


def today_local() -> date:
    return datetime.now(config.TZ).date()
