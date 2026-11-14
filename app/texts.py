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
        "ru": "*{name}*\n{descr}\nДлительность: {dur} мин · {price}",
        "en": "*{name}*\n{descr}\nDuration: {dur} min · {price}",
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
    "btn_more": {"ru": "Ещё", "en": "More"},
    "more_title": {"ru": "Что вас интересует?", "en": "What would you like to know?"},
    "btn_route": {"ru": "Как добраться и парковка", "en": "Directions & parking"},
    "btn_hours": {"ru": "Часы работы", "en": "Opening hours"},
    "btn_cert": {"ru": "Сертификаты", "en": "Gift certificates"},
    "btn_couple": {"ru": "СПА для двоих", "en": "SPA for two"},
    "btn_groups": {"ru": "Компании и девичники", "en": "Groups & hen parties"},
    "btn_etiquette": {"ru": "Спа-этикет", "en": "Spa etiquette"},
    "btn_promo": {"ru": "Акции", "en": "Special offers"},
    "btn_payment": {"ru": "Оплата", "en": "Payment"},
    "couple_title": {"ru": "Программы для двоих:", "en": "Programs for two:"},
    "groups_ask": {
        "ru": "Напишите одним сообщением: сколько будет гостей, на какую дату и время и что хотелось бы. Я передам администратору — он подберёт программу и свяжется с вами.",
        "en": "Please write in one message: how many guests, the date and time, and your wishes. I'll pass it to our administrator who will contact you.",
    },
    "btn_one_guest": {"ru": "1 гость · {price} ₽", "en": "1 guest · {price} RUB"},
    "btn_two_guests": {"ru": "Для двоих · {price} ₽", "en": "For two · {price} RUB"},
    "price_line_1": {"ru": "{price} ₽", "en": "{price} RUB"},
    "price_line_2": {"ru": "для двоих {price} ₽", "en": "for two {price} RUB"},
    "prepay_note": {
        "ru": "Эта программа бронируется только с предоплатой — администратор свяжется с вами для оплаты.",
        "en": "This program requires a prepayment — our administrator will contact you about payment.",
    },
    "need_name": {"ru": "Как к вам обращаться?", "en": "How may I address you?"},
    "consent_title": {
        "ru": "Отметьте, пожалуйста, согласия (версия {version}). Первые два нужны для записи, третье — по желанию.",
        "en": "Please tick the consents (version {version}). The first two are required for booking, the third is optional.",
    },
    "cb_pd": {"ru": "Обработка персональных данных", "en": "Personal data processing"},
    "cb_rules": {"ru": "Правила и противопоказания", "en": "Rules & contraindications"},
    "cb_ads": {"ru": "Поздравления и акции", "en": "Greetings & offers"},
    "btn_continue": {"ru": "Продолжить", "en": "Continue"},
    "btn_consent_texts": {"ru": "Тексты согласий", "en": "Consent texts"},
    "consent_required": {
        "ru": "Для записи нужны первые два согласия. Отметьте их, пожалуйста.",
        "en": "The first two consents are required for booking. Please tick them.",
    },
    "confirmed_full": {
        "ru": (
            "Вы записаны, {name}.\n\n"
            "*{program}*\n{when}\nДлительность: {dur} мин · гостей: {guests}\nМастер: {master}\nСтоимость: {price} ₽\n"
            "Адрес: ул. Индустриальная, 46 (Park Side Inn)\n\n"
            "Приходите за 10–15 минут. {rules}\n\nНакануне в 10:00 я попрошу подтвердить визит."
        ),
        "en": (
            "You're booked, {name}.\n\n"
            "*{program}*\n{when}\nDuration: {dur} min · guests: {guests}\nTherapist: {master}\nPrice: {price} RUB\n"
            "Address: 46 Industrialnaya St. (Park Side Inn)\n\n"
            "Please arrive 10–15 minutes early. {rules}\n\nThe day before at 10:00 I'll ask you to confirm your visit."
        ),
    },
    "btn_etiquette_full": {"ru": "Спа-этикет полностью", "en": "Full spa etiquette"},
    "unsubscribed": {
        "ru": "Готово, вы отписаны от поздравлений и акций. Напоминания о ваших записях продолжат приходить.",
        "en": "Done, you've unsubscribed from greetings and offers. Booking reminders will still arrive.",
    },
    "reminder_soon": {
        "ru": "{name}, ждём вас сегодня в {time}: «{program}». Адрес: ул. Индустриальная, 46 (Park Side Inn). Приходите за 10–15 минут.",
        "en": "{name}, we look forward to seeing you today at {time}: {program}. Address: 46 Industrialnaya St. (Park Side Inn). Please arrive 10–15 minutes early.",
    },
    "after_visit": {
        "ru": "{name}, спасибо, что были у нас вчера. Как вам «{program}»? Будем благодарны за отзыв — просто напишите его сюда. А когда захочется снова отдохнуть, я подберу время.",
        "en": "{name}, thank you for visiting us yesterday. How was {program}? We'd appreciate your feedback — just write it here. Whenever you'd like to relax again, I'll find a time.",
    },
    "abandoned": {
        "ru": "Окно на «{program}» освободилось, но его можно выбрать снова — я подберу свободное время, если захотите.",
        "en": "The slot for {program} was released, but you can choose it again — I'll find a free time whenever you like.",
    },
    "btn_unsubscribe": {"ru": "Отписаться", "en": "Unsubscribe"},
    "review_thanks": {"ru": "Спасибо за отзыв! Передам команде.", "en": "Thank you for your feedback! I'll pass it on to the team."},
    "by_tag_title": {"ru": "Вот что у нас есть:", "en": "Here is what we have:"},
    "btn_staff": {"ru": "Наши мастера", "en": "Our therapists"},
    "staff_title": {"ru": "Мастера на {day}:", "en": "Therapists on {day}:"},
    "staff_none": {"ru": "На {day} график ещё не составлен. Подскажу другой день?", "en": "The schedule for {day} is not ready yet. Shall I check another day?"},
    "btn_book_master": {"ru": "Записаться к: {name}", "en": "Book with {name}"},
    "btn_tomorrow": {"ru": "Следующий день", "en": "Next day"},
    "master_pick": {"ru": "Записываю к мастеру {name}. Выберите пространство и программу — покажу время в смены мастера.", "en": "Booking with {name}. Choose a space and a program — I'll show times within their shifts."},
    "master_days": {"ru": "{name} работает: {days}", "en": "{name} works: {days}"},
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
