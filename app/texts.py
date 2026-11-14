"""Тексты ассистента на русском и английском. Тон: спокойный, премиальный, на «вы», без канцелярита."""
from datetime import date, datetime

from . import config

T = {
    "greet_known": {
        "ru": "Здравствуйте, {name}! Рада вас видеть в СПА-парке. Чем могу помочь?",
        "en": "Hello, {name}! Welcome back to SPA-park. How can I help you?",
    },
    "greet_new": {
        "ru": "Здравствуйте! Я ассистент СПА-парка. Помогу подобрать программу, записаться на свободное время и отвечу на вопросы. Чем могу помочь?",
        "en": "Hello! I'm the SPA-park assistant. I can help you choose a program, book a free time slot and answer your questions. How can I help?",
    },
    "night_note": {
        "ru": "Сейчас ночь, но записаться можно прямо сейчас. Администратор на связи с 10:00.",
        "en": "It's night now, but you can book right away. Our administrator is available from 10:00.",
    },
    "btn_book": {"ru": "Записаться", "en": "Book"},
    "btn_programs": {"ru": "Программы и цены", "en": "Programs & prices"},
    "btn_my": {"ru": "Мои записи", "en": "My bookings"},
    "btn_info": {"ru": "Адрес и часы", "en": "Address & hours"},
    "btn_contra": {"ru": "Противопоказания", "en": "Contraindications"},
    "btn_admin": {"ru": "Администратор", "en": "Administrator"},
    "btn_lang": {"ru": "English", "en": "Русский"},
    "btn_menu": {"ru": "В меню", "en": "Menu"},
    "btn_back": {"ru": "Назад", "en": "Back"},
    "choose_space": {
        "ru": "У нас семь SPA-пространств. Какое вам ближе?",
        "en": "We have seven SPA spaces. Which one do you like?",
    },
    "choose_program": {"ru": "Программы пространства «{space}»:", "en": "Programs in the {space} space:"},
    "program_card": {
        "ru": "*{name}*\n{descr}\nДлительность: {dur} мин · {price} ₽ · до {guests} гостей",
        "en": "*{name}*\n{descr}\nDuration: {dur} min · {price} RUB · up to {guests} guests",
    },
    "btn_pick_time": {"ru": "Выбрать время", "en": "Choose time"},
    "choose_day": {"ru": "На какой день вас записать?", "en": "Which day would you like?"},
    "no_days": {
        "ru": "На ближайшую неделю свободных окон для этой программы нет. Передам администратору — он предложит варианты.",
        "en": "There are no free slots for this program in the coming week. I'll pass this to our administrator.",
    },
    "choose_slot": {
        "ru": "Свободное время на {day} ({name}):",
        "en": "Free time on {day} ({name}):",
    },
    "no_slots_day": {
        "ru": "На {day} свободных окон уже нет. Выберите другой день:",
        "en": "No free slots left on {day}. Please choose another day:",
    },
    "held": {
        "ru": (
            "Это время я закрепила за вами до {until}.\n\n"
            "*{name}*\n{when}\nМастер: {master}\nСтоимость: {price} ₽\n\nПодтвердить запись?"
        ),
        "en": (
            "I'm holding this time for you until {until}.\n\n"
            "*{name}*\n{when}\nTherapist: {master}\nPrice: {price} RUB\n\nConfirm the booking?"
        ),
    },
    "btn_confirm": {"ru": "Подтвердить", "en": "Confirm"},
    "btn_other_time": {"ru": "Другое время", "en": "Other time"},
    "need_phone": {
        "ru": "Чтобы закрепить запись за вами, поделитесь, пожалуйста, номером телефона — кнопкой ниже или сообщением.",
        "en": "To confirm the booking, please share your phone number — with the button below or as a message.",
    },
    "btn_share_phone": {"ru": "Поделиться номером", "en": "Share phone number"},
    "need_consent": {
        "ru": (
            "Последний шаг: подтвердите согласие на обработку персональных данных и ознакомление "
            "с правилами посещения и противопоказаниями (версия {version})."
        ),
        "en": (
            "One last step: please confirm your consent to personal data processing and that you have read "
            "the visiting rules and contraindications (version {version})."
        ),
    },
    "btn_consent_yes": {"ru": "Согласен(на)", "en": "I agree"},
    "btn_read_rules": {"ru": "Правила и противопоказания", "en": "Rules & contraindications"},
    "ask_ads": {
        "ru": "Можно присылать вам поздравления и информацию об акциях? От рассылки можно отказаться в любой момент.",
        "en": "May we send you greetings and news about special offers? You can unsubscribe at any time.",
    },
    "btn_yes": {"ru": "Да", "en": "Yes"},
    "btn_no": {"ru": "Нет, спасибо", "en": "No, thanks"},
    "confirmed": {
        "ru": (
            "Вы записаны.\n\n*{name}*\n{when}\nМастер: {master}\nСтоимость: {price} ₽\n\n"
            "Ждём вас по адресу: ул. Индустриальная, 46. Оплатить можно на месте или онлайн. "
            "Накануне я напомню о визите."
        ),
        "en": (
            "You're booked.\n\n*{name}*\n{when}\nTherapist: {master}\nPrice: {price} RUB\n\n"
            "Our address: 46 Industrialnaya St. You can pay on site or online. I'll remind you the day before."
        ),
    },
    "btn_pay": {"ru": "Оплатить онлайн", "en": "Pay online"},
    "btn_preorder": {"ru": "Чай и добавки", "en": "Tea & extras"},
    "slot_taken": {
        "ru": "Это время только что заняли. Вот ближайшие свободные варианты:",
        "en": "This time has just been taken. Here are the nearest free options:",
    },
    "slot_taken_none": {
        "ru": "Это время только что заняли, а похожих окон рядом нет. Я передала ваш запрос администратору — он свяжется с вами.",
        "en": "This time has just been taken and there are no similar slots nearby. I've passed your request to our administrator.",
    },
    "hold_expired": {
        "ru": "Время закрепления истекло, окно освободилось. Давайте подберём время заново.",
        "en": "The hold has expired and the slot was released. Let's choose a time again.",
    },
    "my_none": {"ru": "У вас нет предстоящих записей.", "en": "You have no upcoming bookings."},
    "my_list": {"ru": "Ваши записи:", "en": "Your bookings:"},
    "btn_reschedule": {"ru": "Перенести", "en": "Reschedule"},
    "btn_cancel": {"ru": "Отменить", "en": "Cancel"},
    "cancel_ask": {"ru": "Отменить запись «{name}», {when}?", "en": "Cancel {name}, {when}?"},
    "btn_cancel_yes": {"ru": "Да, отменить", "en": "Yes, cancel"},
    "cancelled": {
        "ru": "Запись отменена. Будем рады видеть вас в другой раз.",
        "en": "Your booking is cancelled. We hope to see you another time.",
    },
    "reschedule_pick": {
        "ru": "Подберём новое время для «{name}». Какой день удобен?",
        "en": "Let's find a new time for {name}. Which day suits you?",
    },
    "preorder_intro": {
        "ru": "Что приготовить к вашему визиту? Мастер увидит выбор заранее.",
        "en": "What should we prepare for your visit? Your therapist will see it in advance.",
    },
    "preorder_none": {"ru": "Для этой программы предзаказ не предусмотрен.", "en": "No pre-orders for this program."},
    "btn_done": {"ru": "Готово", "en": "Done"},
    "preorder_saved": {"ru": "Записала: {items}. Ждём вас!", "en": "Noted: {items}. See you soon!"},
    "preorder_empty": {"ru": "Хорошо, без предзаказа. Ждём вас!", "en": "Fine, no pre-order. See you soon!"},
    "visit_ask": {
        "ru": "{name}, напоминаю: завтра в {time} — «{program}», мастер {master}. Подтвердите, пожалуйста, визит.",
        "en": "{name}, a reminder: tomorrow at {time} — {program}, therapist {master}. Please confirm your visit.",
    },
    "btn_visit_yes": {"ru": "Подтверждаю", "en": "I'll be there"},
    "visit_thanks": {"ru": "Спасибо! Ждём вас завтра.", "en": "Thank you! See you tomorrow."},
    "escalated": {
        "ru": "Передала ваш вопрос администратору вместе с нашей перепиской. Он ответит вам в ближайшее время.",
        "en": "I've passed your question and our conversation to the administrator. They will reply shortly.",
    },
    "escalated_night": {
        "ru": "Передала ваш вопрос администратору вместе с нашей перепиской. Он на связи с 10:00 и ответит вам утром.",
        "en": "I've passed your question to the administrator. They are available from 10:00 and will reply in the morning.",
    },
    "escalated_group": {
        "ru": "Для групп мы готовим отдельное предложение. Передала администратору ваши пожелания: {details}. Он свяжется с вами.",
        "en": "We prepare a special offer for groups. I've passed your wishes to the administrator: {details}.",
    },
    "health_note": {
        "ru": "Я не могу решать, подходит ли вам процедура. Вот общая информация, а ваш вопрос я передала администратору.",
        "en": "I can't decide whether a treatment suits you. Here is general information; I've passed your question to the administrator.",
    },
    "not_understood": {
        "ru": "Простите, не совсем поняла. Выберите, пожалуйста, вариант ниже или напишите иначе.",
        "en": "Sorry, I didn't quite understand. Please choose an option below or rephrase.",
    },
    "prices_intro": {"ru": "Наши программы:", "en": "Our programs:"},
    "lang_set": {"ru": "Хорошо, продолжаем на русском.", "en": "Sure, let's continue in English."},
}

WEEKDAYS = {
    "ru": ["пн", "вт", "ср", "чт", "пт", "сб", "вс"],
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
}
MONTHS = {
    "ru": ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"],
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
}


def t(key: str, lang: str, **kwargs) -> str:
    entry = T[key]
    text = entry.get(lang) or entry["ru"]
    return text.format(**kwargs) if kwargs else text


def fmt_day(day: date, lang: str) -> str:
    today = datetime.now(config.TZ).date()
    delta = (day - today).days
    rel = {0: {"ru": "сегодня", "en": "today"}, 1: {"ru": "завтра", "en": "tomorrow"}}.get(delta)
    base = f"{WEEKDAYS[lang][day.weekday()]}, {day.day} {MONTHS[lang][day.month - 1]}"
    return f"{rel[lang]}, {base}" if rel else base


def fmt_when(dt: datetime, lang: str) -> str:
    local = dt.astimezone(config.TZ)
    return f"{fmt_day(local.date(), lang)}, {local:%H:%M}"


def fmt_time(dt: datetime) -> str:
    return f"{dt.astimezone(config.TZ):%H:%M}"
