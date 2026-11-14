"""Разбор свободного текста без языковой модели: намерения, программа, дата и время.

Работает как страховка: если модель недоступна или ошиблась, ассистент всё равно понимает
типовые запросы («цены», «где вы», «запишите завтра в 18 на хаммам»).
"""
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from . import config

ESCALATION_PATTERNS = [
    ("complaint", r"жалоб|верн\w* (деньги|оплат)|возврат|ужасн|отвратит|недовол|обман|претензи|хамств|refund|complain|terrible"),
    ("group", r"корпоратив|девичник|мальчишник|компани\w* (из|на)|групп|коллектив|сотрудник|\b(\d{2,}|[5-9]) (человек|чел|гост)|team building|party|group"),
    ("asked_admin", r"администратор|оператор|живо\w* (человек|сотрудник)|позов|соедин|manager|human|administrator"),
    ("health", r"беремен|давлени|гипертон|диабет|сердц|варикоз|после операц|онколог|можно ли мне|мне можно|противопоказан\w* мне|pregnan|blood pressure"),
]

INTENT_PATTERNS = [
    ("cancel", r"отмен|cancel"),
    ("reschedule", r"перенес|перенос|другое время|resched"),
    ("my", r"мои запис|моя запис|когда я записан|my booking"),
    ("contraindications", r"противопоказ|contraindic"),
    ("parking", r"парков|parking"),
    ("address", r"адрес|где (вы|наход)|как (до вас )?добрат|address|location|where are you"),
    ("hours", r"час\w* работ|режим|во сколько|до скольки|открыт|работаете|hours|open"),
    ("payment", r"оплат|карт\w*|наличн|предоплат|pay"),
    ("certificate", r"сертификат|подар|certificate|gift"),
    ("rules", r"правил|опозда|rules"),
    ("prices", r"цен|стоимост|сколько стоит|прайс|price|cost"),
    ("programs", r"что у вас есть|какие (есть )?(программ|услуг)|расскаж|программ|услуг|what do you have|programs"),
    ("book", r"запис|забронир|свобод|окн|хочу|book|reserv|free slot"),
    ("greeting", r"^(привет|здравств|добр\w+ (день|утро|вечер)|hello|hi)\b"),
]

SPACE_STEMS = {
    "turkey": ("турц", "хамма", "turk", "hamma"),
    "himalaya": ("гимал", "солян", "himal", "salt"),
    "india": ("индия", "индий", "аюрв", "india", "ayurv"),
    "china": ("китай", "кита", "china", "chine"),
    "japan": ("япон", "офуро", "japan", "ofuro"),
    "siberia": ("сибир", "парен", "веник", "баня", "siber", "steam"),
    "relax": ("релак", "relax"),
}

DAY_WORDS = {"сегодня": 0, "today": 0, "завтра": 1, "tomorrow": 1, "послезавтра": 2}
WEEKDAY_STEMS = ["понед", "вторн", "сред", "четв", "пятн", "субб", "воскр"]
TIME_RE = re.compile(r"(?:\bв\s*|\bat\s*|\bна\s*)?\b([01]?\d|2[0-3])(?:[:.](\d{2}))?\s*(?:час|ч\b|:00)?", re.I)
DATE_RE = re.compile(r"\b(\d{1,2})[./](\d{1,2})\b")


@dataclass
class Parsed:
    escalation: str | None = None
    intent: str | None = None
    space_code: str | None = None
    program_id: int | None = None
    day: date | None = None
    at: datetime | None = None


def _first_match(text: str, patterns: list[tuple[str, str]]) -> str | None:
    for name, pattern in patterns:
        if re.search(pattern, text, re.I):
            return name
    return None


def _stems(text: str) -> set[str]:
    return {w[:5] for w in re.findall(r"[a-zа-яё]+", text.lower()) if len(w) >= 4}


def parse_day(text: str, today: date) -> date | None:
    low = text.lower()
    for word, delta in sorted(DAY_WORDS.items(), key=lambda kv: -len(kv[0])):
        if word in low:
            return today + timedelta(days=delta)
    match = DATE_RE.search(low)
    if match:
        day, month = int(match.group(1)), int(match.group(2))
        try:
            candidate = date(today.year, month, day)
        except ValueError:
            return None
        return candidate if candidate >= today else date(today.year + 1, month, day)
    for idx, stem in enumerate(WEEKDAY_STEMS):
        if stem in low:
            return today + timedelta(days=(idx - today.weekday()) % 7)
    return None


def parse_time(text: str) -> tuple[int, int] | None:
    cleaned = DATE_RE.sub(" ", text)
    for match in TIME_RE.finditer(cleaned):
        prefix = match.group(0).strip().lower()
        hour = int(match.group(1))
        has_marker = prefix.startswith(("в", "at", "на")) or match.group(2) is not None
        if has_marker and 10 <= hour <= 23:
            return hour, int(match.group(2) or 0)
        if has_marker and 1 <= hour <= 11:
            return hour + 12, int(match.group(2) or 0)
    return None


def match_space(text: str) -> str | None:
    stems = _stems(text)
    for code, keys in SPACE_STEMS.items():
        if any(s.startswith(k[:5]) or k.startswith(s) for s in stems for k in keys):
            return code
    return None


def match_program(text: str, programs: list[dict]) -> int | None:
    """Программа, однозначно лучше других совпавшая по словам названия."""
    stems = _stems(text)
    if not stems:
        return None
    scored = []
    for prog in programs:
        name_stems = _stems(prog["name"] + " " + prog["name_en"])
        hits = len(stems & name_stems)
        if hits:
            scored.append((hits, prog["id"]))
    scored.sort(reverse=True)
    if scored and (len(scored) == 1 or scored[0][0] > scored[1][0]):
        return scored[0][1]
    return None


def parse(text: str, programs: list[dict]) -> Parsed:
    today = datetime.now(config.TZ).date()
    result = Parsed(
        escalation=_first_match(text, ESCALATION_PATTERNS),
        intent=_first_match(text, INTENT_PATTERNS),
        space_code=match_space(text),
        program_id=match_program(text, programs),
        day=parse_day(text, today),
    )
    clock = parse_time(text)
    if clock:
        result.day = result.day or today
        result.at = datetime.combine(result.day, datetime.min.time(), tzinfo=config.TZ).replace(hour=clock[0], minute=clock[1])
    return result


def looks_english(text: str) -> bool:
    letters = re.findall(r"[a-zA-Zа-яА-ЯёЁ]", text)
    latin = re.findall(r"[a-zA-Z]", text)
    return len(letters) >= 4 and len(latin) / len(letters) > 0.7
