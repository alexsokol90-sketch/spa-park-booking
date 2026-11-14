"""Настройки приложения. Секреты читаются только из окружения и файла .env."""
import os
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
MODEL = os.getenv("MODEL", "claude-sonnet-5-5")
# Провайдер модели: gigachat (размещение в РФ) или claude. По умолчанию — тот, для которого задан ключ.
GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY", "").strip()
GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
GIGACHAT_MODEL = os.getenv("GIGACHAT_MODEL", "GigaChat")
# OpenAI-совместимый API: AI-агент Timeweb Cloud (модель — YandexGPT и др. — выбирается в настройках агента).
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").strip()
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "yandexgpt")


def _default_provider() -> str:
    if LLM_BASE_URL and LLM_API_KEY:
        return "openai_compat"
    return "gigachat" if GIGACHAT_AUTH_KEY else "claude"


LLM_PROVIDER = os.getenv("LLM_PROVIDER", "").strip() or _default_provider()
MAX_BOT_TOKEN = os.getenv("MAX_BOT_TOKEN", "").strip()
MAX_API = os.getenv("MAX_API", "https://platform-api.max.ru")
MAX_ADMIN_CHAT_ID = os.getenv("MAX_ADMIN_CHAT_ID", "").strip()
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "").strip()
TG_ADMIN_CHAT_ID = os.getenv("TG_ADMIN_CHAT_ID", "").strip()
# Адрес Bot API. Из РФ api.telegram.org доступен нестабильно — можно указать собственный ретранслятор.
TG_API_BASE = os.getenv("TG_API_BASE", "https://api.telegram.org").rstrip("/")
VK_GROUP_TOKEN = os.getenv("VK_GROUP_TOKEN", "").strip()
VK_GROUP_ID = os.getenv("VK_GROUP_ID", "").strip()
VK_ADMIN_PEER_ID = os.getenv("VK_ADMIN_PEER_ID", "").strip()
PUBLIC_URL = os.getenv("PUBLIC_URL", "")
PORT = int(os.getenv("PORT", "3030"))
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://spa:spa@127.0.0.1:5432/spa")
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()
PROJECT_NAME = "СПА-парк — онлайн-запись и ИИ-ассистент"

# Предметная область «СПА-парк», Нижневартовск.
TZ = ZoneInfo("Asia/Yekaterinburg")
OPEN_TIME = time(10, 0)
CLOSE_HOUR = 24
SLOT_STEP_MIN = 30
HOLD_MINUTES = 15
HOLD_WARN_MINUTES = 2
CONFIRM_REQUEST_TIME = time(10, 0)
NO_ANSWER_REPORT_TIME = time(15, 0)
BIRTHDAY_TIME = time(11, 0)
ESCALATION_RENOTIFY_MIN = 5
CONSENT_VERSION = "pd-2026-11-v1"
PAYMENT_URL = os.getenv("PAYMENT_URL", "https://spapark86.ru/")
