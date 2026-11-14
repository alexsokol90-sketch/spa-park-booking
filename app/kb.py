"""База знаний ассистента. Ассистент отвечает только тем, что здесь есть, и данными каталога.

Источник — сайт заказчика spapark86.ru (страницы «Контакты», «Спа-этикет», «Акции», «СПА для компаний»,
«Сертификаты»), 14.11.2026. Пункты с пометкой DEMO на сайте не опубликованы: их подтверждает заказчик.
"""
from . import config

ADDRESS = "г. Нижневартовск, ул. Индустриальная, 46"
PHONES = "+7 (3466) 49-11-47, +7 (982) 200-00-86"

FAQ = {
    "address": {
        "ru": f"СПА-парк находится в комплексе Park Side Inn: {ADDRESS}. Телефоны: {PHONES}.",
        "en": f"SPA-park is located in the Park Side Inn complex: 46 Industrialnaya St., Nizhnevartovsk. Phones: {PHONES}.",
    },
    "hours": {
        "ru": "Мы работаем ежедневно с 10:00 до 00:00. Записаться через меня можно круглосуточно, администратор на связи с 10:00 до 00:00.",
        "en": "We are open daily from 10:00 to midnight. You can book with me 24/7; our administrator is available from 10:00 to midnight.",
    },
    "parking": {
        "ru": f"Подъехать можно прямо к комплексу Park Side Inn: {ADDRESS}. Актуальные условия парковки подскажет администратор: {PHONES}.",
        "en": f"You can drive right up to the Park Side Inn complex, 46 Industrialnaya St. Our administrator will tell you about parking: {PHONES}.",
    },
    "payment": {
        "ru": (
            "Оплатить визит можно на месте картой или наличными, на ресепшене отеля, "
            f"онлайн на сайте ({config.PAYMENT_URL}) или подарочным сертификатом. "
            "Программы для компаний бронируются только с предоплатой или полной оплатой."
        ),
        "en": (
            "You can pay on site by card or cash, at the hotel reception, "
            f"online on our website ({config.PAYMENT_URL}) or with a gift certificate. "
            "Group programs are booked only with a prepayment or full payment."
        ),
    },
    "certificate": {
        "ru": (
            "Подарочные сертификаты:\n"
            "• номиналом 3 000, 5 000, 10 000 и 20 000 ₽ — на любые услуги;\n"
            "• на программы: «Утро невесты» 7 300 ₽, «Королева красоты» 7 500 ₽, «Экспресс детокс» 15 000 ₽, "
            "«Мужская привилегия» 20 000 ₽, «Креольский ритм» 20 000 ₽, «Энергия травяных канн» 25 000 ₽, "
            "«Антистресс» 30 000 ₽, «Шикарная» 35 000 ₽, «Сантиметры исчезают» 50 000 ₽.\n"
            "Купить можно на сайте или на ресепшене."
        ),
        "en": (
            "Gift certificates:\n"
            "• face value 3,000, 5,000, 10,000 and 20,000 RUB — for any services;\n"
            "• for programs from 7,300 to 50,000 RUB (e.g. Bride's Morning, Beauty Queen, Anti-stress).\n"
            "Available on our website or at the reception."
        ),
    },
    "promo": {
        "ru": (
            "Действующие акции:\n"
            "• скидка 25% в день рождения — на СПА-услуги и меню ресторана;\n"
            "• 1000 подарочных баллов в честь дня рождения;\n"
            "• программа «Послеполётный массаж» — снимает отёки и усталость после перелёта;\n"
            "• уход «Утро невесты» — прогрев, пилинг, маски для тела и лица, уход за руками, чайная церемония;\n"
            "• сертификат в СПА на 5 000 ₽ и номер в подарок при бронировании банкетного зала на свадьбу.\n"
            "Сроки и детали уточнит администратор."
        ),
        "en": (
            "Current offers:\n"
            "• 25% off on your birthday — for SPA services and the restaurant menu;\n"
            "• 1,000 bonus points for your birthday;\n"
            "• the After-flight massage program — relieves swelling and fatigue after a flight;\n"
            "• Bride's Morning care — warm-up, peeling, body and face masks, hand care, tea ceremony;\n"
            "• a 5,000 RUB SPA certificate and a hotel room as a gift when booking a wedding banquet hall.\n"
            "Our administrator will confirm dates and details."
        ),
    },
    "etiquette": {
        "ru": (
            "Спа-этикет:\n"
            "• Время лучше бронировать заранее.\n"
            "• При опоздании время сеанса сокращается на время опоздания.\n"
            "• Если планы изменились, предупредите нас не позднее чем за 24 часа — здесь в чате или по телефону.\n"
            "• Если гость не отвечает на подтверждение брони за 3 часа до начала, администрация может отменить визит.\n"
            "• Специалист может отказать в сеансе при несоблюдении гигиенических норм или в состоянии опьянения.\n"
            "• Гостям 14–17 лет услуги оказываются в сокращённом формате и в присутствии родителя; детям до 14 лет СПА-услуги не оказываются."
        ),
        "en": (
            "Spa etiquette:\n"
            "• We recommend booking in advance.\n"
            "• If you are late, the session is shortened by the time of the delay.\n"
            "• If your plans change, please let us know at least 24 hours in advance — here in the chat or by phone.\n"
            "• If a guest does not respond to the booking confirmation 3 hours before the start, the visit may be cancelled.\n"
            "• A therapist may refuse a session if hygiene rules are not followed or the guest is intoxicated.\n"
            "• Guests aged 14–17 receive shortened treatments with a parent present; SPA services are not provided to children under 14."
        ),
    },
    "groups": {
        "ru": (
            "СПА для компаний и девичников:\n"
            "• «Ян» — «Турция», хаммам и джакузи, до 10 гостей, 4 часа — 18 000 ₽;\n"
            "• «Инь» — «Гималаи», сауна и джакузи, до 6 гостей, 4 часа — 14 000 ₽;\n"
            "• «Тайна Хюррем» — «Турция», 4 часа — 25 000 ₽;\n"
            "• «Магия трав» — «Гималаи», 4 часа — 17 800 ₽.\n"
            "Дополнительный час — 3 500 ₽, дополнительный гость — 2 500 ₽. Бронирование только с предоплатой.\n"
            "Групповые визиты оформляет администратор: расскажите, сколько вас, на какую дату и что хотелось бы, — я передам."
        ),
        "en": (
            "SPA for groups and hen parties:\n"
            "• Yang — Turkey space, hammam and jacuzzi, up to 10 guests, 4 hours — 18,000 RUB;\n"
            "• Yin — Himalayas space, sauna and jacuzzi, up to 6 guests, 4 hours — 14,000 RUB;\n"
            "• Hurrem's secret — Turkey space, 4 hours — 25,000 RUB;\n"
            "• Magic of herbs — Himalayas space, 4 hours — 17,800 RUB.\n"
            "Extra hour 3,500 RUB, extra guest 2,500 RUB. Booking only with a prepayment.\n"
            "Group visits are arranged by our administrator: tell me how many guests, the date and your wishes, and I'll pass them on."
        ),
    },
    "loyalty": {
        "ru": (
            "Карты лояльности SPA Park:\n"
            "• Золотая — кешбэк 5% от чека в СПА и ресторане, скидка 10% на проживание в отеле;\n"
            "• Платиновая — кешбэк 10%, скидка 20% на проживание.\n"
            "Бонусами можно оплатить до 50% суммы. Карту оформляют по анкете на сайте или на ресепшене; "
            "виртуальная карта привязывается к номеру телефона."
        ),
        "en": (
            "SPA Park loyalty cards:\n"
            "• Gold — 5% cashback on SPA and restaurant bills, 10% off hotel stays;\n"
            "• Platinum — 10% cashback, 20% off hotel stays.\n"
            "Points can cover up to 50% of a bill. The card is issued via a form on the website or at the reception "
            "and is linked to your phone number."
        ),
    },
    "children": {
        "ru": (
            "Гостям 14–17 лет СПА-услуги оказываются в сокращённом формате, по решению специалиста и в присутствии родителя. "
            "Детям до 14 лет СПА-услуги не оказываются."
        ),
        "en": "Guests aged 14–17 receive shortened treatments at the therapist's discretion with a parent present. SPA services are not provided to children under 14.",
    },
    "drinks": {
        "ru": (
            "В часть программ для двоих напитки уже входят: «Тайны Востока» — белое вино, «Идеальное свидание» — красное вино, "
            "«Наследие Индонезии», «Китайская симфония» и «Секрет Гейши» — игристое брют, «Влюбиться в Сибирь» — сет настоек. "
            "В остальных программах — травяной чай. В комплексе работает ресторан Park Side Inn. "
            "Специалист может отказать в процедуре гостю в состоянии опьянения."
        ),
        "en": (
            "Some programs for two already include drinks: Secrets of the East — white wine, The perfect date — red wine, "
            "Heritage of Indonesia, Chinese symphony and Geisha's secret — sparkling brut, Fall in love with Siberia — a set of tinctures. "
            "Other programs include herbal tea. There is a Park Side Inn restaurant in the complex."
        ),
    },
    "hotel": {
        "ru": "СПА-парк находится в комплексе Park Side Inn: отель на 120 номеров, ресторан и спортзал. По карте лояльности — скидка на проживание 10–20%.",
        "en": "SPA-park is part of the Park Side Inn complex: a 120-room hotel, a restaurant and a gym. Loyalty card holders get 10–20% off hotel stays.",
    },
    "cancel_rules": {  # DEMO в части предоплаты: на сайте условия возврата не опубликованы
        "ru": (
            "Условия: при опоздании программа сокращается на время опоздания. Отменить или перенести запись можно "
            "здесь не позднее чем за 24 часа — предоплата в этом случае переносится на новую дату или возвращается. "
            "Центр может отменить запись, если гость не ответил на подтверждение за 3 часа до начала."
        ),
        "en": (
            "Terms: if you are late, the program is shortened by the time of the delay. You can cancel or reschedule here "
            "at least 24 hours in advance — any prepayment is then moved to the new date or refunded. "
            "The center may cancel a booking if the guest does not respond to the confirmation 3 hours before the start."
        ),
    },
    "contraindications": {  # DEMO: список сверяется с медицинской документацией заказчика
        "ru": (
            "Я не провожу допуск к процедурам и не даю медицинских рекомендаций — только информирую. "
            "Информированное согласие подписывается на ресепшене при визите.\n\n"
            "Абсолютные противопоказания к программам с прогревом (хаммам, сауна, парение, кедровая бочка, ванны): "
            "острые воспалительные и инфекционные заболевания, повышенная температура, онкологические заболевания, "
            "тяжёлые сердечно-сосудистые заболевания, кровотечения и склонность к ним.\n\n"
            "Частичные противопоказания (нужна консультация врача): беременность, гипертония, варикоз, "
            "заболевания кожи в зоне воздействия, недавние операции.\n\n"
            "Не рекомендуется: процедуры сразу после плотной еды, алкоголь до и во время визита.\n\n"
            "Пространство «Релакс» — без прогрева: локальный массаж и уход за лицом.\n"
            "Если сомневаетесь, подходит ли вам процедура, — я передам вопрос администратору."
        ),
        "en": (
            "I don't assess admission to treatments or give medical advice — I can only share information. "
            "An informed consent form is signed at the reception.\n\n"
            "Absolute contraindications for heat programs (hammam, sauna, steaming with brooms, cedar barrel, baths): "
            "acute inflammatory or infectious diseases, fever, cancer, severe cardiovascular diseases, bleeding disorders.\n\n"
            "Partial contraindications (consult your doctor): pregnancy, hypertension, varicose veins, "
            "skin conditions in the treated area, recent surgery.\n\n"
            "Not recommended: treatments right after a heavy meal, alcohol before or during the visit.\n\n"
            "The Relax space has no heat: local massage and facial care.\n"
            "If you are unsure whether a treatment suits you, I will pass your question to our administrator."
        ),
    },
}

# Тексты согласий: версия хранится в БД вместе с каждой отметкой гостя.
CONSENT_TEXTS = {
    "pd": (
        "Я даю ООО «Парк Сайд инн» согласие на обработку персональных данных (имя, телефон, дата рождения, "
        "история визитов) для записи на услуги и исполнения договора в соответствии с 152-ФЗ. "
        "Согласие можно отозвать, написав администратору."
    ),
    "rules": "Я ознакомлен(а) с правилами посещения (спа-этикетом) и перечнем противопоказаний.",
    "ads": (
        "Я согласен(на) получать поздравления, информацию об акциях и персональные предложения в мессенджере MAX. "
        "Отписаться можно в любой момент командой «отписаться»."
    ),
}

# Термины, которые модель обязана переводить единообразно (проверяется на приёмке).
GLOSSARY_EN = {
    "обёртывание": "body wrap",
    "парение": "steaming with brooms (banya)",
    "хаммам": "hammam",
    "молочная ванна": "milk bath",
    "офуро": "ofuro (Japanese hot tub)",
    "кесе": "kese peeling mitt",
    "кедровая бочка": "cedar barrel",
    "пилинг": "body scrub",
}


def faq(key: str, lang: str) -> str:
    item = FAQ.get(key)
    if not item:
        return ""
    return item.get(lang) or item["ru"]


def knowledge_text() -> str:
    """База знаний одним текстом — для системного промпта модели."""
    parts = [f"[{key}] {val['ru']}" for key, val in FAQ.items()]
    glossary = "; ".join(f"{ru} → {en}" for ru, en in GLOSSARY_EN.items())
    return "\n".join(parts) + f"\n\nГлоссарий для английского: {glossary}"
