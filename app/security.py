"""Защита сервиса: ограничение частоты запросов, подпись сессий веб-чата, заголовки безопасности, IP клиента.

Ограничения хранятся в памяти процесса (один экземпляр сервиса) — этого достаточно, чтобы не дать
перебирать пароли и тратить бюджет нейросети спамом.
"""
import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque

from fastapi import Request

from . import config

SECRET_KEY = (config.SECRET_KEY or secrets.token_hex(32)).encode()


class RateLimiter:
    """Скользящее окно: не больше limit событий за window секунд на ключ."""

    def __init__(self, limit: int, window: float):
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        if len(self._hits) > 50_000:
            self._hits.clear()
        return True

    def blocked(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits.get(key)
        return bool(hits) and len([h for h in hits if now - h <= self.window]) >= self.limit


LOGIN_FAILS = RateLimiter(limit=10, window=15 * 60)   # 10 неверных входов за 15 минут — блок по IP
CHAT_IP = RateLimiter(limit=40, window=60)            # веб-чат: с одного IP
CHAT_GUEST = RateLimiter(limit=15, window=60)         # любой канал: один гость
VOICE_IP = RateLimiter(limit=8, window=60)            # распознавание голоса дороже
LLM_DAILY_LIMIT = 4000                                # запросов к модели в сутки — защита бюджета
_llm_day: dict[str, int] = {}


def llm_budget_ok() -> bool:
    day = time.strftime("%Y-%m-%d")
    used = _llm_day.get(day, 0)
    if used >= LLM_DAILY_LIMIT:
        return False
    _llm_day.clear()
    _llm_day[day] = used + 1
    return True


def client_ip(request: Request) -> str:
    """IP клиента: за Caddy берём первый адрес из X-Forwarded-For, иначе адрес соединения."""
    peer = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and peer in ("127.0.0.1", "::1"):
        return forwarded.split(",")[0].strip()
    return peer


# ---------- сессии веб-чата ----------

def sign(uid: int) -> str:
    return hmac.new(SECRET_KEY, str(uid).encode(), hashlib.sha256).hexdigest()[:32]


def verify(uid: int, sig: str) -> bool:
    return uid < 0 and hmac.compare_digest(sign(uid), sig or "")


def new_web_session() -> tuple[int, str]:
    """Идентификатор гостя веб-чата выдаёт сервер и подписывает — подобрать чужой диалог нельзя."""
    uid = -secrets.randbelow(9 * 10**14) - 10**6
    return uid, sign(uid)


# ---------- заголовки ----------

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "connect-src 'self'; media-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'self'; "
)
EMBED_ANCESTORS = "frame-ancestors 'self' https://spapark86.ru https://*.spapark86.ru"


def security_headers(path: str) -> dict[str, str]:
    """Страницу помощника (/) можно встроить только на сайт СПА-парка, остальное — нигде."""
    ancestors = EMBED_ANCESTORS if path == "/" else "frame-ancestors 'self'"
    return {
        "Content-Security-Policy": CSP + ancestors,
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "microphone=(self), camera=(), geolocation=(), payment=()",
    }
