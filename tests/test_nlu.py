"""Юнит-тесты разбора свободного текста (без базы данных)."""
from datetime import date

from app import guests, nlu

PROGRAMS = [
    {"id": 1, "name": "Пенный массаж", "name_en": "Foam massage"},
    {"id": 2, "name": "Молочная ванна «Гейша»", "name_en": "Geisha milk bath"},
    {"id": 3, "name": "Массаж стоп", "name_en": "Foot massage"},
]
TODAY = date(2026, 11, 14)


def test_escalation_triggers():
    assert nlu.parse("Хочу вернуть деньги, это ужасно", PROGRAMS).escalation == "complaint"
    assert nlu.parse("Нас 8 человек, девичник", PROGRAMS).escalation == "group"
    assert nlu.parse("Позовите администратора", PROGRAMS).escalation == "asked_admin"
    assert nlu.parse("Я беременна, можно ли мне хаммам?", PROGRAMS).escalation == "health"
    assert nlu.parse("Сколько стоит массаж?", PROGRAMS).escalation is None


def test_intents():
    assert nlu.parse("Где вы находитесь?", PROGRAMS).intent == "address"
    assert nlu.parse("Есть парковка?", PROGRAMS).intent == "parking"
    assert nlu.parse("Во сколько вы открываетесь", PROGRAMS).intent == "hours"
    assert nlu.parse("А что у вас есть?", PROGRAMS).intent == "programs"


def test_program_match_is_unambiguous():
    assert nlu.match_program("хочу молочную ванну", PROGRAMS) == 2
    assert nlu.match_program("пенный массаж", PROGRAMS) == 1
    assert nlu.match_program("массаж", PROGRAMS) is None


def test_day_and_time():
    assert nlu.parse_day("завтра вечером", TODAY) == date(2026, 11, 15)
    assert nlu.parse_day("послезавтра", TODAY) == date(2026, 11, 16)
    assert nlu.parse_day("на 20.11", TODAY) == date(2026, 11, 20)
    assert nlu.parse_time("завтра в 18") == (18, 0)
    assert nlu.parse_time("в 19:30") == (19, 30)
    assert nlu.parse_time("в 7") == (19, 0)


def test_space_and_language():
    assert nlu.match_space("хочу в хаммам") == "turkey"
    assert nlu.match_space("попариться с веником") == "siberia"
    assert nlu.looks_english("do you have a hammam?")
    assert not nlu.looks_english("есть ли у вас хаммам?")


def test_phone_normalization():
    assert guests.normalize_phone("8 (912) 555-12-34") == "+79125551234"
    assert guests.normalize_phone("+7 900 000 00 01") == "+79000000001"
    assert guests.normalize_phone("нет телефона") is None
