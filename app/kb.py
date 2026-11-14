"""База знаний ассистента. Ассистент отвечает только тем, что здесь есть, и данными каталога.

Пункты с пометкой DEMO заполнены для демонстрации и сверяются с заказчиком перед запуском.
"""
from . import config

ADDRESS = "г. Нижневартовск, ул. Индустриальная, 46"

FAQ = {
    "address": {
        "ru": f"Мы находимся по адресу: {ADDRESS}.",
        "en": "We are located at 46 Industrialnaya St., Nizhnevartovsk.",
    },
    "hours": {
        "ru": "Мы работаем ежедневно с 10:00 до 00:00. Онлайн-запись через меня доступна круглосуточно.",
        "en": "We are open daily from 10:00 to midnight. You can book with me 24/7.",
    },
    "parking": {  # DEMO
        "ru": "У входа есть парковка для гостей.",
        "en": "There is guest parking at the entrance.",
    },
    "payment": {
        "ru": (
            "Оплатить визит можно на месте картой или наличными, на ресепшене отеля, "
            f"онлайн на сайте ({config.PAYMENT_URL}) или подарочным сертификатом. "
            "Для некоторых записей нужна предоплата."
        ),
        "en": (
            "You can pay on site by card or cash, at the hotel reception, "
            f"online on our website ({config.PAYMENT_URL}) or with a gift certificate."
        ),
    },
    "certificate": {
        "ru": "Подарочные сертификаты номиналом можно приобрести на ресепшене или на сайте. Сертификатом можно оплатить любую программу.",
        "en": "Gift certificates are available at the reception or on our website and can be used for any program.",
    },
    "rules": {  # DEMO
        "ru": (
            "Правила посещения: приходите за 10–15 минут до начала программы. "
            "При опоздании время программы может сократиться. "
            "Перенести или отменить запись можно здесь, в чате. "
            "Перед первым визитом на ресепшене подписывается информированное согласие."
        ),
        "en": (
            "Please arrive 10–15 minutes before your program. Late arrival may shorten it. "
            "You can reschedule or cancel right here in the chat. "
            "An informed consent form is signed at the reception before your first visit."
        ),
    },
    "contraindications": {  # DEMO: список сверяется с медицинской документацией заказчика
        "ru": (
            "Я не провожу допуск к процедурам и не даю медицинских рекомендаций — только информирую.\n\n"
            "Абсолютные противопоказания к программам с прогревом: острые воспалительные и инфекционные заболевания, "
            "повышенная температура, онкологические заболевания, тяжёлые сердечно-сосудистые заболевания, "
            "кровотечения и склонность к ним.\n\n"
            "Частичные противопоказания (нужна консультация врача): беременность, гипертония, варикоз, "
            "заболевания кожи в зоне воздействия, недавние операции.\n\n"
            "Не рекомендуется: процедуры сразу после плотной еды и употребление алкоголя до визита.\n\n"
            "Пространство «Релакс» — без прогрева: локальный массаж и уход за лицом.\n"
            "Если сомневаетесь, можно ли вам процедуру, — я передам вопрос администратору."
        ),
        "en": (
            "I don't assess admission to treatments or give medical advice — I can only share information.\n\n"
            "Absolute contraindications for heat programs: acute inflammatory or infectious diseases, fever, "
            "cancer, severe cardiovascular diseases, bleeding disorders.\n\n"
            "Partial contraindications (consult your doctor): pregnancy, hypertension, varicose veins, "
            "skin conditions in the treated area, recent surgery.\n\n"
            "Not recommended: treatments right after a heavy meal or after drinking alcohol.\n\n"
            "The Relax space has no heat: local massage and facial care.\n"
            "If you are unsure whether a treatment suits you, I will pass your question to our administrator."
        ),
    },
}

# Термины, которые модель обязана переводить единообразно.
GLOSSARY_EN = {
    "обёртывание": "body wrap",
    "парение": "steaming with brooms (banya)",
    "хаммам": "hammam",
    "молочная ванна": "milk bath",
    "офуро": "ofuro (Japanese hot tub)",
    "кесе": "kese peeling",
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
