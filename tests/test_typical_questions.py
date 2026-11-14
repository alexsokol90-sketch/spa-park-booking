"""Типовые вопросы из кейса (цены, адрес, парковка, часы, свободное окно, «что у вас есть»).

Цель кейса — не менее 80% закрываются без человека. Проверяем запасной путь без языковой модели:
если даже он распознаёт ≥ 80% формулировок, с моделью покрытие только выше.
"""
from app import nlu

PROGRAMS = [
    {"id": 1, "name": "Отдых по-турецки", "name_en": "Turkish-style rest"},
    {"id": 2, "name": "Утро Клеопатры", "name_en": "Cleopatra's morning"},
    {"id": 3, "name": "Массаж головы", "name_en": "Head massage"},
    {"id": 4, "name": "Тепло Кедра", "name_en": "Cedar warmth"},
]

TYPICAL = {
    "prices": [
        "Сколько стоит массаж?", "Какие у вас цены?", "прайс скиньте", "Сколько стоит хаммам на двоих?",
        "стоимость программ", "почём молочная ванна", "What are your prices?",
    ],
    "address": [
        "Где вы находитесь?", "Какой адрес?", "как до вас добраться", "Вы где?",
        "адрес спа подскажите", "Where are you located?",
    ],
    "parking": ["Есть парковка?", "Где можно оставить машину?", "парковка бесплатная?", "Is there parking?"],
    "hours": [
        "Во сколько вы открываетесь?", "До скольки работаете?", "режим работы", "вы работаете в воскресенье?",
        "часы работы", "What are your opening hours?",
    ],
    "slots": [
        "Есть свободное время завтра?", "хочу записаться на сегодня вечером", "Можно на Утро Клеопатры завтра в 19?",
        "есть окно на массаж головы в субботу", "запишите на Тепло Кедра", "свободно ли в пятницу",
        "Can I book for tomorrow?",
    ],
    "catalog": [
        "А что у вас есть?", "Расскажите про программы", "какие услуги есть", "что можно для двоих",
        "есть хаммам?", "хочу попариться с веником", "Do you have a milk bath?",
    ],
}


def handled(text: str) -> bool:
    """Без модели ассистент отвечает сам, если понял намерение, программу, пространство или вид процедуры."""
    p = nlu.parse(text, PROGRAMS)
    if p.escalation:
        return False
    return bool(p.intent or p.program_id or p.space_code or p.tag)


def test_typical_questions_coverage_at_least_80_percent():
    questions = [q for group in TYPICAL.values() for q in group]
    missed = [q for q in questions if not handled(q)]
    coverage = 1 - len(missed) / len(questions)
    assert coverage >= 0.8, f"покрытие {coverage:.0%}, не распознаны: {missed}"


def test_each_category_is_covered():
    for category, questions in TYPICAL.items():
        share = sum(handled(q) for q in questions) / len(questions)
        assert share >= 0.75, f"{category}: {share:.0%}"


def test_partial_answer_topics_are_recognized():
    assert nlu.parse("Какой у вас пробковый сбор?", PROGRAMS).intent == "drinks"
    assert nlu.parse("Можно со своим вином?", PROGRAMS).intent == "drinks"
    assert nlu.parse("Есть карта лояльности?", PROGRAMS).intent == "loyalty"
    assert nlu.parse("Можно прийти с ребёнком 12 лет?", PROGRAMS).intent == "children"


def test_booking_deep_links():
    from app.dialog import start_payload

    assert start_payload("book") == "book"
    assert start_payload("prog_23") == "prog:23"
    assert start_payload("space_5") == "space:5"
    assert start_payload("") == "menu"
    assert start_payload("drop table") == "menu"


def test_confirmation_timing_rules():
    from datetime import datetime

    from app import config
    from app.scheduler import confirmation_due

    tz = config.TZ
    visit = datetime(2026, 11, 20, 19, 0, tzinfo=tz)
    assert confirmation_due(visit, datetime(2026, 11, 19, 18, 0, tzinfo=tz))      # накануне, за 25 ч
    assert not confirmation_due(visit, datetime(2026, 11, 18, 18, 0, tzinfo=tz))  # за 49 ч — рано
    assert not confirmation_due(visit, datetime(2026, 11, 20, 18, 0, tzinfo=tz))  # за 1 ч — поздно
    assert confirmation_due(visit, datetime(2026, 11, 20, 14, 0, tzinfo=tz))      # запись «на сегодня», за 5 ч
    assert not confirmation_due(visit, datetime(2026, 11, 19, 23, 0, tzinfo=tz))  # ночью не пишем
