"""Демо-данные каталога и гостей.

ВНИМАНИЕ: названия программ, цены, длительности и мастера — демонстрационные.
Перед запуском в работу их заменяют на прайс и штат заказчика (таблица programs/masters).
Запуск: python -m app.seed [--reset]
"""
import asyncio
import random
import sys
from datetime import date, datetime, timedelta

from . import config, db

SPACES = [
    ("turkey", "Турция", "Turkey", "Хаммам, пенный массаж, кесе-пилинг", False),
    ("himalaya", "Гималаи", "Himalayas", "Гималайская соль, тёплые камни, поющие чаши", False),
    ("india", "Индия", "India", "Аюрведа, масляные массажи, широдхара", False),
    ("china", "Китай", "China", "Туйна, гуаша, чайная церемония", False),
    ("japan", "Япония", "Japan", "Офуро, молочная ванна, шиацу", False),
    ("siberia", "Сибирь", "Siberia", "Парение вениками, кедровая бочка, мёд", False),
    ("relax", "Релакс", "Relax", "Локальный массаж и уход за лицом без прогрева", True),
]

# (space, code, name, name_en, duration, cleanup, price, max_guests, tags, description)
PROGRAMS = [
    ("turkey", "tr-sultan", "Хаммам-ритуал «Султан»", "Sultan hammam ritual", 120, 30, 6900, 2, "хаммам,пилинг,массаж", "Прогрев на гёбек-таши, кесе-пилинг, пенный массаж, чай"),
    ("turkey", "tr-foam", "Пенный массаж", "Foam massage", 60, 20, 3900, 1, "хаммам,массаж", "Классический турецкий пенный массаж на тёплом камне"),
    ("turkey", "tr-couple", "Хаммам для двоих", "Hammam for two", 150, 30, 12900, 2, "хаммам,для двоих,массаж", "Ритуал хаммама для пары с пенным массажем"),
    ("turkey", "tr-kese", "Кесе-пилинг", "Kese peeling", 60, 20, 3500, 1, "хаммам,пилинг", "Глубокое очищение кожи рукавицей кесе"),
    ("turkey", "tr-palace", "Ритуал «Дворец»", "Palace ritual", 180, 30, 9900, 2, "хаммам,массаж,обёртывание", "Хаммам, пилинг, пенный массаж и обёртывание"),
    ("himalaya", "hm-salt", "«Гималайская соль»", "Himalayan salt", 90, 20, 5900, 1, "массаж,соль", "Массаж мешочками с гималайской солью"),
    ("himalaya", "hm-stones", "Массаж тёплыми соляными камнями", "Warm salt stone massage", 90, 20, 6200, 1, "массаж,камни", "Массаж нагретыми блоками гималайской соли"),
    ("himalaya", "hm-wrap", "Соляной скраб и обёртывание", "Salt scrub and wrap", 120, 30, 6900, 1, "пилинг,обёртывание", "Скраб на основе гималайской соли и обёртывание"),
    ("himalaya", "hm-tibet", "Ритуал «Тибет» для двоих", "Tibet ritual for two", 150, 30, 13500, 2, "массаж,для двоих", "Поющие чаши, соляной массаж, травяной чай"),
    ("himalaya", "hm-bowls", "Поющие чаши", "Singing bowls", 60, 15, 3900, 1, "медитация", "Звуковая релаксация тибетскими чашами"),
    ("india", "in-abhyanga", "Абхьянга", "Abhyanga", 90, 20, 6500, 1, "массаж,масло,аюрведа", "Аюрведический масляный массаж всего тела"),
    ("india", "in-shirodhara", "Широдхара", "Shirodhara", 60, 20, 5500, 1, "аюрведа,масло", "Тонкая струя тёплого масла на лоб"),
    ("india", "in-couple", "«Аюрведа для двоих»", "Ayurveda for two", 150, 30, 13900, 2, "массаж,для двоих,аюрведа", "Синхронная абхьянга для пары"),
    ("india", "in-pinda", "Пинда-сведа", "Pinda sweda", 120, 30, 7500, 1, "массаж,травы,аюрведа", "Массаж горячими мешочками с травами"),
    ("india", "in-maharani", "Ритуал «Махарани»", "Maharani ritual", 180, 30, 10900, 1, "массаж,аюрведа,обёртывание", "Абхьянга, широдхара и обёртывание"),
    ("china", "cn-tuina", "Туйна", "Tui na", 60, 15, 4500, 1, "массаж", "Китайский лечебно-оздоровительный массаж"),
    ("china", "cn-tea", "Чайная церемония и массаж", "Tea ceremony and massage", 120, 20, 7200, 2, "массаж,чай", "Чайная церемония и расслабляющий массаж"),
    ("china", "cn-emperor", "«Императорский»", "Emperor's ritual", 150, 30, 9500, 1, "массаж,гуаша", "Туйна, гуаша и массаж лица"),
    ("china", "cn-guasha", "Гуаша лица и тела", "Gua sha", 60, 15, 4200, 1, "гуаша,лицо", "Скребковый массаж камнем нефрит"),
    ("china", "cn-yinyang", "Ритуал «Инь-Ян» для двоих", "Yin-Yang ritual for two", 150, 30, 13900, 2, "массаж,для двоих,чай", "Парный массаж и чайная церемония"),
    ("japan", "jp-ofuro", "Офуро и массаж", "Ofuro and massage", 120, 30, 7500, 1, "ванна,массаж,прогрев", "Японская бочка офуро и массаж"),
    ("japan", "jp-shiatsu", "Шиацу", "Shiatsu", 60, 15, 4500, 1, "массаж", "Японский точечный массаж"),
    ("japan", "jp-geisha", "Молочная ванна «Гейша»", "Geisha milk bath", 90, 30, 6900, 1, "ванна,молочная ванна", "Молочная ванна с добавками на выбор"),
    ("japan", "jp-sakura", "Ритуал «Сакура» для двоих", "Sakura ritual for two", 150, 30, 14500, 2, "ванна,для двоих,массаж", "Офуро, молочная ванна и массаж для пары"),
    ("japan", "jp-sento", "Сэнто-ритуал", "Sento ritual", 180, 30, 10500, 1, "ванна,массаж,пилинг", "Офуро, пилинг, массаж и молочная ванна"),
    ("siberia", "sb-steam", "«Сибирский пар»", "Siberian steam", 90, 30, 5900, 2, "парение,баня", "Парение берёзовыми и дубовыми вениками"),
    ("siberia", "sb-cedar", "Кедровая бочка", "Cedar barrel", 60, 20, 3500, 1, "прогрев,фитобочка", "Фитобочка из кедра с травами"),
    ("siberia", "sb-honey", "Медовое обёртывание", "Honey wrap", 90, 20, 5200, 1, "обёртывание,мёд", "Прогрев и обёртывание сибирским мёдом"),
    ("siberia", "sb-taiga", "Ритуал «Тайга» для двоих", "Taiga ritual for two", 180, 30, 15900, 2, "парение,для двоих,массаж", "Парение, кедровая бочка, медовый массаж"),
    ("siberia", "sb-steam-massage", "Парение и массаж", "Steam and massage", 150, 30, 8900, 1, "парение,массаж", "Парение вениками и классический массаж"),
    ("relax", "rl-back", "Массаж спины и шеи", "Back and neck massage", 45, 15, 2900, 1, "массаж,локальный", "Локальный массаж без прогрева"),
    ("relax", "rl-feet", "Массаж стоп", "Foot massage", 45, 15, 2700, 1, "массаж,локальный", "Рефлекторный массаж стоп"),
    ("relax", "rl-face-massage", "Массаж лица", "Face massage", 45, 15, 3200, 1, "лицо,массаж", "Скульптурирующий массаж лица"),
    ("relax", "rl-face-care", "Уход за лицом", "Facial care", 60, 15, 3900, 1, "лицо,уход", "Очищение, маска, массаж лица"),
    ("relax", "rl-head", "Массаж головы и шеи", "Head and neck massage", 30, 15, 1900, 1, "массаж,локальный", "Снятие напряжения, 30 минут"),
]

MASTERS = [
    ("Анна", "массаж, аюрведа"),
    ("Айгуль", "хаммам, пилинг"),
    ("Виктория", "уход за лицом, гуаша"),
    ("Ольга", "ванны, обёртывания"),
    ("Сергей", "парение, массаж"),
    ("Дмитрий", "массаж, туйна, шиацу"),
]

# (name, name_en, category, price, stock)
PREORDER_ITEMS = [
    ("Пуэр", "Pu-erh tea", "tea", 0, 50),
    ("Молочный улун", "Milk oolong", "tea", 0, 50),
    ("Иван-чай с чабрецом", "Fireweed tea with thyme", "tea", 0, 40),
    ("Масала-чай", "Masala chai", "tea", 0, 30),
    ("Сибирский травяной сбор", "Siberian herbal tea", "tea", 0, 40),
    ("Мёд в молочную ванну", "Honey for milk bath", "bath", 400, 20),
    ("Лепестки роз", "Rose petals", "bath", 500, 15),
    ("Масло лаванды", "Lavender oil", "bath", 300, 25),
    ("Морская соль", "Sea salt", "bath", 300, 25),
    ("Фруктовая тарелка", "Fruit plate", "extra", 900, 10),
    ("Свежевыжатый сок", "Fresh juice", "extra", 450, 20),
]

DEMO_GUESTS = [
    ("+79000000001", "Елена", date(1990, 11, 14)),
    ("+79000000002", "Ирина", date(1985, 11, 17)),
    ("+79000000003", "Мария", date(1993, 3, 2)),
    ("+79000000004", "Алексей", date(1988, 7, 21)),
    ("+79000000005", "Наталья", date(1979, 1, 9)),
    ("+79000000006", "Ксения", date(1996, 11, 20)),
    ("+79000000007", "Дмитрий", date(1983, 5, 30)),
    ("+79000000008", "Ольга", date(1991, 9, 12)),
    ("+79000000009", "Светлана", date(1975, 12, 1)),
    ("+79000000010", "Анастасия", date(1999, 2, 18)),
    ("+79000000011", "Татьяна", date(1987, 6, 6)),
    ("+79000000012", "Юлия", date(1994, 4, 25)),
]


def _local(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=config.TZ)


async def _insert_catalog(conn) -> None:
    for sort, (code, name, name_en, descr, relax) in enumerate(SPACES):
        await conn.execute(
            "INSERT INTO spaces (code, name, name_en, description, is_relax, sort) VALUES (%s,%s,%s,%s,%s,%s)",
            (code, name, name_en, descr, relax, sort),
        )
    for space, code, name, name_en, dur, clean, price, guests, tags, descr in PROGRAMS:
        await conn.execute(
            """INSERT INTO programs (code, space_id, name, name_en, description, duration_min,
                   cleanup_min, price, max_guests, tags)
               SELECT %s, id, %s, %s, %s, %s, %s, %s, %s, %s FROM spaces WHERE code = %s""",
            (code, name, name_en, descr, dur, clean, price, guests, tags, space),
        )
    for name, skills in MASTERS:
        await conn.execute("INSERT INTO masters (name, skills) VALUES (%s, %s)", (name, skills))
    for name, name_en, cat, price, stock in PREORDER_ITEMS:
        await conn.execute(
            "INSERT INTO preorder_items (name, name_en, category, price, stock) VALUES (%s,%s,%s,%s,%s)",
            (name, name_en, cat, price, stock),
        )
    # Чай и допы — ко всем программам, добавки в ванну — к программам с ванной.
    await conn.execute(
        """INSERT INTO program_preorders (program_id, item_id)
           SELECT p.id, i.id FROM programs p CROSS JOIN preorder_items i
           WHERE i.category IN ('tea', 'extra') OR (i.category = 'bath' AND p.tags LIKE '%%ванна%%')"""
    )


async def _insert_guests(conn) -> None:
    for n, (phone, name, birth) in enumerate(DEMO_GUESTS, start=1):
        row = await db.fetchone(
            conn,
            "INSERT INTO guests (phone, name, birth_date, loyalty_card, loyalty_points) VALUES (%s,%s,%s,%s,%s) RETURNING id",
            (phone, name, birth, f"SP-{100000 + n}", n * 150),
        )
        for kind in ("pd", "rules"):
            await conn.execute(
                "INSERT INTO consents (guest_id, kind, granted, text_version, channel) VALUES (%s,%s,true,%s,'reception')",
                (row["id"], kind, config.CONSENT_VERSION),
            )
        await conn.execute(
            "INSERT INTO consents (guest_id, kind, granted, text_version, channel) VALUES (%s,'ads',%s,%s,'reception')",
            (row["id"], n % 4 != 0, config.CONSENT_VERSION),
        )


async def _book(conn, guest_id: int, prog: dict, master_id: int, start: datetime, status: str, visit: str = "none") -> None:
    end = start + timedelta(minutes=prog["duration_min"])
    busy = end + timedelta(minutes=prog["cleanup_min"])
    await conn.execute(
        """INSERT INTO bookings (guest_id, program_id, space_id, master_id, starts_at, ends_at, busy_until,
               status, source, visit_status, confirmed_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'admin',%s, now())""",
        (guest_id, prog["id"], prog["space_id"], master_id, start, end, busy, status, visit),
    )


async def _insert_bookings(conn) -> None:
    progs = {p["code"]: p for p in await db.fetch(conn, "SELECT * FROM programs")}
    guests = [g["id"] for g in await db.fetch(conn, "SELECT id FROM guests ORDER BY id")]
    today = datetime.now(config.TZ).date()
    rnd = random.Random(42)
    # История визитов: у части гостей последний визит давно (сегмент реактивации).
    for i, gid in enumerate(guests):
        months_ago = 5 if i % 3 == 0 else 1
        day = today - timedelta(days=30 * months_ago + rnd.randint(0, 10))
        code = rnd.choice(list(progs))
        await _book(conn, gid, progs[code], (i % 6) + 1, _local(day, 12 + i % 8), "completed")
    plan_today = [("tr-sultan", 0, 14), ("sb-steam", 1, 16), ("rl-back", 2, 12), ("jp-geisha", 3, 18), ("in-abhyanga", 4, 19)]
    plan_tomorrow = [("cn-tea", 5, 13), ("hm-salt", 6, 15), ("jp-ofuro", 7, 17), ("tr-foam", 8, 20)]
    for n, (code, gi, hour) in enumerate(plan_today):
        await _book(conn, guests[gi], progs[code], n % 6 + 1, _local(today, hour), "confirmed", "confirmed")
    tomorrow = today + timedelta(days=1)
    for n, (code, gi, hour) in enumerate(plan_tomorrow):
        await _book(conn, guests[gi], progs[code], (n + 2) % 6 + 1, _local(tomorrow, hour), "confirmed")


async def seed(reset: bool = False) -> None:
    await db.open_pool()
    try:
        await db.apply_schema()
        async with db.tx() as conn:
            if reset:
                await conn.execute(
                    """TRUNCATE outbox, campaigns, escalations, messages, sessions, booking_preorders,
                       program_preorders, preorder_items, bookings, consents, guests, programs, masters,
                       spaces, job_runs RESTART IDENTITY CASCADE"""
                )
            exists = await db.fetchone(conn, "SELECT count(*) AS n FROM spaces")
            if exists["n"]:
                print("Каталог уже заполнен, пропускаю (используйте --reset)")
                return
            await _insert_catalog(conn)
            await _insert_guests(conn)
            await _insert_bookings(conn)
        print("Демо-данные загружены")
    finally:
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(seed(reset="--reset" in sys.argv))
