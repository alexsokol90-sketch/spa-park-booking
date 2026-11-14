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


def test_phone_masked_for_model():
    from app.ai import mask_pd

    assert mask_pd("мой номер 8 (912) 555-12-34, жду") == "мой номер [телефон], жду"
    assert mask_pd("завтра в 18:00") == "завтра в 18:00"


def test_vk_keyboard_keeps_last_row_within_limits():
    from app.vk_bot import MAX_BUTTONS, MAX_ROWS, fit_rows

    rows = [[(f"item {i}", f"pretog:1:{i}")] for i in range(12)] + [[("Готово", "predone:1")]]
    fitted = fit_rows(rows)
    assert fitted[-1] == [("Готово", "predone:1")]
    assert len(fitted) <= MAX_ROWS
    assert sum(len(r) for r in fitted) <= MAX_BUTTONS


def test_short_words_match_program():
    progs = [*PROGRAMS, {"id": 4, "name": "Массаж головы", "name_en": "Head massage"}, {"id": 5, "name": "Массаж ног", "name_en": "Foot massage"}]
    assert nlu.match_program("хочу массаж ног завтра", progs) == 5
    assert nlu.match_program("массаж головы", progs) == 4


def test_vk_keyboard_packs_rows_instead_of_dropping():
    from app.vk_bot import fit_rows

    rows = [[(f"prog {i}", f"prog:{i}")] for i in range(7)] + [[("Меню", "menu")]]
    fitted = fit_rows(rows)
    assert sum(len(r) for r in fitted) == 8
    assert len(fitted) <= 6
