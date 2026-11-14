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
MAX_BOT_TOKEN = os.getenv("MAX_BOT_TOKEN", "").strip()
MAX_API = os.getenv("MAX_API", "https://platform-api2.max.ru")
MAX_ADMIN_CHAT_ID = os.getenv("MAX_ADMIN_CHAT_ID", "").strip()
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
PAYMENT_URL = os.getenv("PAYMENT_URL", "https://spa-park.example/pay")
