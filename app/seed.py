"""Каталог и демо-данные.

Пространства, программы, длительности и цены взяты с сайта заказчика spapark86.ru (14.11.2026).
Состав «Релакса» подобран из массажей и уходов сайта по описанию кейса (локальный массаж и лицо, без прогрева).
Время работы мастера внутри программы указано по сайту, где оно есть («мастер 30 мин + чайная церемония»),
иначе — равно длительности. Тайминги уборки, мастера и гости — демонстрационные, их уточняет заказчик.
Запуск: python -m app.seed [--reset]
"""
import asyncio
import json
import random
import sys
from datetime import date, datetime, timedelta

from . import config, db, kb

SPACES = [
    ("turkey", "Турция", "Turkey", "Хаммам и джакузи — подходит и для большой компании", False),
    ("himalaya", "Гималаи", "Himalayas", "Жаркая сауна, гималайская соль и джакузи", False),
    ("india", "Индия", "India", "Восточная зона с хаммамом и мягким паром", False),
    ("china", "Китай", "China", "Приватная зона с бочкой офуро: травяные и молочные ванны", False),
    ("japan", "Япония", "Japan", "Купели с травяными сборами и питательными ваннами", False),
    ("siberia", "Сибирь", "Siberia", "Распаривание в кедровых бочках", False),
    ("relax", "Релакс", "Relax", "Локальный массаж и уход за лицом без прогрева", True),
]

# (space, code, name, name_en, duration, master_min, cleanup, price_1, price_2, max_guests, tags, description, prepay)
PROGRAMS = [
    ("turkey", "tr-rest", "Отдых по-турецки", "Turkish-style rest", 90, 90, 30, 4500, None, 1, "хаммам,джакузи", "Хаммам и джакузи для одного гостя", False),
    ("turkey", "tr-secrets", "Тайны Востока", "Secrets of the East", 240, 240, 30, None, 20000, 2, "хаммам,для двоих,пилинг,массаж", "Ароматное распаривание, пилинг рукавицей кесе, пенный и расслабляющий массаж, джакузи, белое вино, восточные сладости", False),
    ("turkey", "tr-hurrem", "Тайна Хюррем", "Hurrem's secret", 240, 240, 30, 25000, None, 6, "хаммам,джакузи,массаж", "Хаммам, дыхательная практика, очищение кожи арабской рукавицей, Таро, массаж головы, джакузи, чайная церемония", True),
    ("himalaya", "hm-finnish", "Отдых по-фински", "Finnish-style rest", 90, 90, 30, 4500, None, 1, "сауна,джакузи", "Сауна и джакузи для одного гостя", False),
    ("himalaya", "hm-date", "Идеальное свидание", "The perfect date", 240, 240, 30, None, 20000, 2, "сауна,для двоих,соль,массаж", "Прогрев в сауне, спа-уход с гималайской солью, расслабляющий массаж, джакузи, красное вино", False),
    ("himalaya", "hm-reboot", "Спа перезагрузка", "Spa reboot", 180, 180, 30, 12000, None, 1, "пар,парение,массаж", "Индивидуальное парение с чередованием влажного и сухого пара и массажем", False),
    ("himalaya", "hm-rescue", "Отдых во SPAсение", "SPA rescue", 135, 135, 30, None, 12000, 2, "пар,парение,для двоих", "Три захода в парную, лёгкое парение веником, обливание, травяной чай с мёдом, джакузи и сауна", False),
    ("himalaya", "hm-steam", "Терапия паром", "Steam therapy", 120, 120, 30, 9000, None, 1, "пар,парение", "Три захода, парение берёзовым и дубовым веником, обливание, травяной чай с мёдом", False),
    ("himalaya", "hm-herbs", "Магия трав", "Magic of herbs", 240, 240, 30, 17800, None, 6, "сауна,пилинг,травы,джакузи", "Сауна, свой скраб, бесконтактный прогрев травяным настоем, солевой скраб, джакузи, чайная церемония", True),
    ("india", "in-wind", "Шепот восточного ветра", "Whisper of the eastern wind", 120, 120, 30, 5500, 8500, 2, "хаммам,массаж", "Прогрев в хаммаме и массаж", False),
    ("india", "in-marrakesh", "Дыхание Марракеша", "Breath of Marrakesh", 160, 160, 30, 7500, 10500, 2, "хаммам,обёртывание,массаж", "Прогрев в хаммаме, обёртывание и массаж", False),
    ("india", "in-oriental", "SPA по-восточному", "Oriental SPA", 160, 160, 30, 6500, 9500, 2, "хаммам,пилинг,массаж", "Прогрев в хаммаме, пилинг кесе и массаж", False),
    ("india", "in-nights", "Тысяча и одна ночь", "One thousand and one nights", 160, 160, 30, 8000, 11000, 2, "хаммам,пилинг,обёртывание,массаж", "Прогрев в хаммаме, пилинг кесе, обёртывание и массаж", False),
    ("india", "in-indonesia", "Наследие Индонезии", "Heritage of Indonesia", 240, 240, 30, None, 20000, 2, "хаммам,для двоих,пилинг,массаж", "Ароматическая парная процедура, пилинг кесе, расслабляющий массаж, игристое брют, фруктовая тарелка", False),
    ("china", "cn-water", "Гармония воды", "Harmony of water", 160, 160, 30, 9000, 12000, 2, "ванна,молочная ванна,обёртывание,массаж", "Молочная ванна, обёртывание, массаж", False),
    ("china", "cn-cleopatra", "Шепот Клеопатры", "Cleopatra's whisper", 170, 170, 30, 10000, 15000, 2, "ванна,молочная ванна,пилинг,обёртывание,массаж", "Молочная ванна, пилинг, обёртывание, массаж", False),
    ("china", "cn-silence", "Ванна Тишины", "Bath of silence", 140, 140, 30, 9000, 12000, 2, "ванна,пилинг,массаж", "Ванна с хвойным экстрактом, пилинг, массаж", False),
    ("china", "cn-aphrodite", "Объятия Афродиты", "Aphrodite's embrace", 120, 120, 30, 7000, 10000, 2, "ванна,массаж", "Ванна с английской солью и пеной, массаж", False),
    ("china", "cn-symphony", "Китайская симфония", "Chinese symphony", 240, 240, 30, None, 20000, 2, "ванна,для двоих,пилинг,массаж", "Ароматная ванна, пилинг, игристое брют, фруктовая тарелка, чайная церемония, массаж тёплыми камнями и травяными мешочками", False),
    ("japan", "jp-sakura", "Прикосновение Сакуры", "Touch of sakura", 120, 120, 30, 6500, 9500, 2, "ванна,массаж", "Ванна с английской солью и пеной, массаж", False),
    ("japan", "jp-pine", "Хвойная нега", "Pine bliss", 140, 140, 30, 9000, 12000, 2, "ванна,пилинг,массаж", "Ванна с хвойным экстрактом, пилинг, массаж", False),
    ("japan", "jp-sunrise", "Восход солнца", "Sunrise", 170, 170, 30, 10000, 13000, 2, "ванна,молочная ванна,пилинг,обёртывание,массаж", "Молочная ванна, пилинг, обёртывание, массаж", False),
    ("japan", "jp-cleopatra", "Утро Клеопатры", "Cleopatra's morning", 160, 160, 30, 9000, 12000, 2, "ванна,молочная ванна,обёртывание,массаж", "Молочная ванна, обёртывание, массаж", False),
    ("japan", "jp-geisha", "Секрет Гейши", "Geisha's secret", 240, 240, 30, None, 18000, 2, "ванна,для двоих,обёртывание,массаж", "Распаривание в ароматной ванне, ароматическая маска для тела, расслабляющий массаж, игристое брют", False),
    ("siberia", "sb-taiga", "Таёжный дух", "Taiga spirit", 60, 60, 20, 3500, None, 1, "кедровая бочка", "Прогрев в кедровой бочке", False),
    ("siberia", "sb-warmth", "Терапия теплом", "Warmth therapy", 150, 150, 30, 7000, 10000, 2, "кедровая бочка,пилинг,массаж", "Прогрев в кедровой бочке, пилинг, массаж", False),
    ("siberia", "sb-ritual", "Сибирский ритуал красоты", "Siberian beauty ritual", 170, 170, 30, 9000, 12000, 2, "кедровая бочка,пилинг,обёртывание,массаж", "Прогрев в кедровой бочке, пилинг, обёртывание, массаж", False),
    ("siberia", "sb-wood", "Энергия дерева", "Energy of wood", 150, 150, 30, 7000, 10000, 2, "кедровая бочка,обёртывание,массаж", "Прогрев в кедровой бочке, обёртывание, массаж", False),
    ("siberia", "sb-cedar", "Тепло Кедра", "Cedar warmth", 120, 120, 30, 6000, 9000, 2, "кедровая бочка,массаж", "Прогрев в кедровой бочке, массаж", False),
    ("siberia", "sb-love", "Влюбиться в Сибирь", "Fall in love with Siberia", 240, 240, 30, None, 18000, 2, "кедровая бочка,для двоих,массаж", "Распаривание в кедровых бочках, расслабляющий массаж, сет настоек, ассорти из благородных рыб", False),
    ("relax", "rl-back", "Массаж спины тёплыми камнями", "Warm stone back massage", 90, 60, 15, 5300, None, 1, "массаж,локальный", "Мастер 60 минут, затем чайная церемония", False),
    ("relax", "rl-feet", "Массаж ног", "Foot massage", 60, 30, 15, 2900, None, 1, "массаж,локальный", "Мастер 30 минут, затем чайная церемония", False),
    ("relax", "rl-head", "Массаж головы", "Head massage", 60, 30, 15, 2900, None, 1, "массаж,локальный", "Мастер 30 минут, затем чайная церемония", False),
    ("relax", "rl-ice", "Массаж лица «Ледяными камнями»", "Ice stone facial massage", 60, 60, 15, 5000, None, 1, "лицо,массаж", "Массаж лица ледяными камнями", False),
    ("relax", "rl-mask", "Альгинатная маска для лица", "Alginate face mask", 60, 10, 15, 3000, None, 1, "лицо,уход", "Мастер 10 минут, затем отдых и чайная церемония", False),
]

SPACE_DESCR_EN = {
    "turkey": "Hammam and jacuzzi — suitable for a large group as well",
    "himalaya": "Hot sauna, Himalayan salt and jacuzzi",
    "india": "An oriental zone with a hammam and soft steam",
    "china": "A private zone with an ofuro tub: herbal and milk baths",
    "japan": "Hot tubs with herbal blends and nourishing baths",
    "siberia": "Steaming in cedar barrels",
    "relax": "Local massage and facial care without heat",
}

# Описания на английском: термины по глоссарию (hammam, body wrap, milk bath, steaming with brooms).
PROGRAM_DESCR_EN = {
    "tr-rest": "Hammam and jacuzzi for one guest",
    "tr-secrets": "Aromatic steaming, kese peeling mitt scrub, foam and relaxing massage, jacuzzi, white wine, oriental sweets",
    "tr-hurrem": "Hammam, breathing practice, Arabic mitt skin cleansing, tarot reading, head massage, jacuzzi, tea ceremony",
    "hm-finnish": "Sauna and jacuzzi for one guest",
    "hm-date": "Sauna warm-up, Himalayan salt spa treatment, relaxing massage, jacuzzi, red wine",
    "hm-reboot": "Individual steaming session alternating wet and dry steam, with massage",
    "hm-rescue": "Three steam sessions, light steaming with brooms, contrast pouring, herbal tea with honey, jacuzzi and sauna",
    "hm-steam": "Three steam sessions, steaming with birch and oak brooms, contrast pouring, herbal tea with honey",
    "hm-herbs": "Sauna, your own scrub, contactless herbal steam warming, salt body scrub, jacuzzi, tea ceremony",
    "in-wind": "Hammam warm-up and massage",
    "in-marrakesh": "Hammam warm-up, body wrap and massage",
    "in-oriental": "Hammam warm-up, kese peeling and massage",
    "in-nights": "Hammam warm-up, kese peeling, body wrap and massage",
    "in-indonesia": "Aromatic steam procedure, kese peeling, relaxing massage, sparkling brut, fruit plate",
    "cn-water": "Milk bath, body wrap, massage",
    "cn-cleopatra": "Milk bath, body scrub, body wrap, massage",
    "cn-silence": "Bath with pine extract, body scrub, massage",
    "cn-aphrodite": "Bath with Epsom salt and foam, massage",
    "cn-symphony": "Aromatic bath, body scrub, sparkling brut, fruit plate, tea ceremony, warm stone and herbal pouch massage",
    "jp-sakura": "Bath with Epsom salt and foam, massage",
    "jp-pine": "Bath with pine extract, body scrub, massage",
    "jp-sunrise": "Milk bath, body scrub, body wrap, massage",
    "jp-cleopatra": "Milk bath, body wrap, massage",
    "jp-geisha": "Steaming in an aromatic bath, aromatic body mask, relaxing massage, sparkling brut",
    "sb-taiga": "Warming up in a cedar barrel",
    "sb-warmth": "Cedar barrel warm-up, body scrub, massage",
    "sb-ritual": "Cedar barrel warm-up, body scrub, body wrap, massage",
    "sb-wood": "Cedar barrel warm-up, body wrap, massage",
    "sb-cedar": "Cedar barrel warm-up, massage",
    "sb-love": "Steaming in cedar barrels, relaxing massage, a set of tinctures, assorted fine fish",
    "rl-back": "60 minutes with the therapist, followed by a tea ceremony",
    "rl-feet": "30 minutes with the therapist, followed by a tea ceremony",
    "rl-head": "30 minutes with the therapist, followed by a tea ceremony",
    "rl-ice": "Facial massage with ice stones",
    "rl-mask": "10 minutes with the therapist, then rest and a tea ceremony",
}

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

# График (демо): (мастер по порядку, правило дня, начало, конец). Каждый день закрыт 10:00–24:00.
SHIFT_RULES = [
    (1, lambda i, d: i % 4 in (0, 1), 600, 1320),     # Анна, 2/2, 10–22
    (2, lambda i, d: i % 4 in (2, 3), 600, 1320),     # Айгуль, 2/2, 10–22
    (3, lambda i, d: d.weekday() < 5, 720, 1440),      # Виктория, 5/2 (пн–пт), 12–24
    (4, lambda i, d: i % 4 in (0, 1), 840, 1440),     # Ольга, 2/2, 14–24
    (5, lambda i, d: i % 4 in (2, 3), 840, 1440),     # Сергей, 2/2, 14–24
    (6, lambda i, d: d.weekday() >= 4 or d.weekday() == 1, 600, 1440),  # Дмитрий, вт и пт–вс, 10–24
]

# Шаблоны чек-листов (демо, заказчик редактирует их в интерфейсе): (code, название, тип, роль, пункты).
CHECKLISTS = [
    ("opening", "Открытие смены", "opening", "admin", [
        "Проверить температуру хаммамов и саун",
        "Включить подогрев купелей, офуро и кедровых бочек",
        "Проверить запас полотенец, халатов и тапочек",
        "Заварить чай и подготовить предзаказы дня (вкладка «Расход на день»)",
        "Проверить сетку на день и неподтверждённые визиты",
        "Включить музыку и ароматизацию в пространствах",
    ]),
    ("space", "Подготовка", "space", "admin", [
        "Пространство убрано после предыдущего гостя (чек-лист клининга закрыт)",
        "Вода и нагрев готовы к началу программы",
        "Предзаказ гостя подготовлен: {preorders}",
        "Мастер {master} предупреждён о госте",
    ]),
    ("master-prep", "Подготовка мастера", "space", "master", [
        "Прочитать предзаказ и пожелания гостя: {preorders}",
        "Подготовить масла, скрабы и маски для программы",
        "Проверить чистоту инструментов и стола",
    ]),
    ("cleanup", "Уборка после гостя", "cleanup", "cleaning", [
        "Убрать использованное бельё, полотенца и халаты",
        "Вымыть и продезинфицировать купель, лежак, массажный стол",
        "Протереть поверхности и дверные ручки дезсредством",
        "Вымыть пол",
        "Проветрить пространство",
        "Разложить свежие полотенца, халаты и тапочки",
        "Пополнить расходники: шампунь, гель, одноразовые принадлежности",
    ]),
    ("cleaning-common", "Уборка общих зон", "daily", "cleaning", [
        "Ресепшен и зона ожидания",
        "Коридоры и лестницы",
        "Санузлы и душевые: мойка, дезинфекция, расходники",
        "Вынести мусор",
    ]),
    ("cleaning-night", "Генеральная уборка (после закрытия)", "closing", "cleaning", [
        "Генеральная уборка хаммамов и саун",
        "Чистка купелей, офуро и кедровых бочек",
        "Дезинфекция массажных столов",
        "Стирка и сушка текстиля",
        "Обработка полов противогрибковым средством",
    ]),
    ("closing", "Закрытие смены", "closing", "admin", [
        "Выключить нагрев, закрыть все пространства",
        "Сверить оплаты дня с кассой",
        "Отметить по всем броням: пришёл / не пришёл",
        "Записать остатки чая и добавок",
    ]),
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
    for kind, text in kb.CONSENT_TEXTS.items():
        await conn.execute(
            "INSERT INTO consent_texts (version, kind, text) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
            (config.CONSENT_VERSION, kind, text),
        )
    for sort, (code, name, name_en, descr, relax) in enumerate(SPACES):
        await conn.execute(
            "INSERT INTO spaces (code, name, name_en, description, description_en, is_relax, sort) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (code, name, name_en, descr, SPACE_DESCR_EN[code], relax, sort),
        )
    for space, code, name, name_en, dur, master, clean, price, couple, guests, tags, descr, prepay in PROGRAMS:
        await conn.execute(
            """INSERT INTO programs (code, space_id, name, name_en, description, description_en, duration_min,
                   master_min, cleanup_min, price, price_couple, max_guests, tags, prepay)
               SELECT %s, id, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s FROM spaces WHERE code = %s""",
            (code, name, name_en, descr, PROGRAM_DESCR_EN[code], dur, master, clean, price, couple, guests, tags, prepay, space),
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


def _on_shift(master_no: int, day: date, start_min: int, end_min: int) -> bool:
    i = (day - datetime.now(config.TZ).date()).days + 1
    rule = SHIFT_RULES[master_no - 1]
    return rule[1](i, day) and rule[2] <= start_min and end_min <= rule[3]


async def _insert_staff(conn) -> None:
    today = datetime.now(config.TZ).date()
    for offset in range(-1, 30):
        day = today + timedelta(days=offset)
        for master_no, rule, start_min, end_min in SHIFT_RULES:
            if rule(offset + 1, day):
                await conn.execute(
                    "INSERT INTO master_shifts (master_id, day, start_min, end_min) VALUES (%s, %s, %s, %s)",
                    (master_no, day, start_min, end_min),
                )
    for sort, (code, title, kind, role, items) in enumerate(CHECKLISTS):
        await conn.execute(
            "INSERT INTO checklist_templates (code, title, kind, role, items, sort) VALUES (%s, %s, %s, %s, %s, %s)",
            (code, title, kind, role, json.dumps(items, ensure_ascii=False), sort),
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
    master_until = start + timedelta(minutes=prog["master_min"])
    busy = end + timedelta(minutes=prog["cleanup_min"])
    guests = 1 if prog["price"] is not None else 2
    price = prog["price"] if guests == 1 else prog["price_couple"]
    await conn.execute(
        """INSERT INTO bookings (guest_id, program_id, space_id, master_id, starts_at, ends_at, master_until,
               busy_until, status, source, visit_status, confirmed_at, guests_count, price_total)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'admin',%s, now(), %s, %s)""",
        (guest_id, prog["id"], prog["space_id"], master_id, start, end, master_until, busy, status, visit, guests, price),
    )


def _free_master(day: date, start_min: int, end_min: int, taken: list[tuple[int, int, int]]) -> int:
    for master_no in range(1, len(SHIFT_RULES) + 1):
        busy = any(m == master_no and start_min < e and s < end_min for m, s, e in taken)
        if not busy and _on_shift(master_no, day, start_min, end_min):
            return master_no
    raise RuntimeError(f"Нет мастера в смене: {day} {start_min}")


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
    plan_today = [("in-oriental", 0, 14), ("sb-cedar", 1, 16), ("rl-back", 2, 12), ("jp-sunrise", 3, 18), ("hm-steam", 4, 19)]
    plan_tomorrow = [("cn-water", 5, 13), ("hm-reboot", 6, 15), ("jp-sakura", 7, 17), ("in-wind", 8, 20)]
    tomorrow = today + timedelta(days=1)
    for day, plan, visit in ((today, plan_today, "confirmed"), (tomorrow, plan_tomorrow, "none")):
        taken: list[tuple[int, int, int]] = []
        for code, gi, hour in plan:
            prog = progs[code]
            start_min, end_min = hour * 60, hour * 60 + prog["master_min"]
            master = _free_master(day, start_min, end_min, taken)
            taken.append((master, start_min, end_min))
            await _book(conn, guests[gi], prog, master, _local(day, hour), "confirmed", visit)


async def seed(reset: bool = False) -> None:
    await db.open_pool()
    try:
        if not reset:
            await db.apply_schema()
        async with db.tx() as conn:
            if reset:
                await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
                await conn.execute((config.ROOT / "db" / "schema.sql").read_text(encoding="utf-8"))
            exists = await db.fetchone(conn, "SELECT count(*) AS n FROM spaces")
            if exists["n"]:
                print("Каталог уже заполнен, пропускаю (используйте --reset)")
                return
            await _insert_catalog(conn)
            await _insert_staff(conn)
            await _insert_guests(conn)
            await _insert_bookings(conn)
        print("Демо-данные загружены")
    finally:
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(seed(reset="--reset" in sys.argv))
