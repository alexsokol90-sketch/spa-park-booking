"""Распознавание голосовых сообщений гостей (Whisper large-v3 через Timeweb Cloud AI, размещение в РФ).

Голос не хранится: файл скачивается в память, передаётся на распознавание и сразу отбрасывается.
В диалог попадает только текст. Подсказка с терминами помогает модели правильно писать названия программ.
"""
import asyncio
import logging

import httpx

from . import config

log = logging.getLogger("speech")
MAX_BYTES = 10 * 1024 * 1024
VOCABULARY = (
    "СПА-парк, хаммам, офуро, кедровая бочка, молочная ванна, обёртывание, парение, пилинг кесе, "
    "Гималаи, Сибирь, Япония, Китай, Индия, Турция, Релакс, Утро Клеопатры, Шепот Клеопатры, Тепло Кедра, "
    "Секрет Гейши, Идеальное свидание, Терапия паром, массаж головы, массаж ног."
)


def enabled() -> bool:
    return bool(config.LLM_BASE_URL and config.LLM_API_KEY)


async def to_ogg(audio: bytes) -> bytes | None:
    """Любой формат браузера (webm, mp4 с iPhone, wav) → ogg/opus, который стабильно принимает распознавание."""
    if audio[:4] == b"OggS":
        return audio
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-loglevel", "error", "-i", "pipe:0", "-vn", "-ac", "1", "-ar", "16000", "-c:a", "libopus", "-f", "ogg", "pipe:1",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, err = await asyncio.wait_for(proc.communicate(audio), timeout=30)
    except (OSError, TimeoutError) as exc:
        log.warning("ffmpeg failed: %s", exc)
        return None
    if proc.returncode != 0 or not out:
        log.warning("ffmpeg error: %s", err.decode(errors="ignore")[:200])
        return None
    return out


async def transcribe(audio: bytes, filename: str = "voice.ogg") -> str | None:
    """Текст голосового сообщения или None, если распознать не удалось."""
    if not enabled() or not audio or len(audio) > MAX_BYTES:
        return None
    audio = await to_ogg(audio)
    if not audio:
        return None
    filename = "voice.ogg"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            resp = await client.post(
                f"{config.LLM_BASE_URL.rstrip('/')}/audio/transcriptions",
                headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
                data={"model": config.STT_MODEL, "language": "ru", "prompt": VOCABULARY},
                files={"file": (filename, audio)},
            )
            if resp.status_code >= 400:
                log.warning("speech recognition HTTP %s: %s", resp.status_code, resp.text[:200])
                return None
            text = (resp.json().get("text") or "").strip()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("speech recognition failed: %s", exc)
        return None
    return text or None


async def download(url: str, headers: dict | None = None) -> bytes | None:
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), follow_redirects=True) as client:
            resp = await client.get(url, headers=headers or {})
            resp.raise_for_status()
            return resp.content[: MAX_BYTES + 1]
    except httpx.HTTPError as exc:
        log.warning("voice download failed: %s", exc)
        return None


def heard(text: str, lang: str = "ru") -> str:
    """Что услышал ассистент — показываем гостю, чтобы он мог поправить."""
    return f"🎙 {'Heard' if lang == 'en' else 'Распознала'}: «{text}»"


def not_heard(lang: str = "ru") -> str:
    if lang == "en":
        return "Sorry, I couldn't make out the voice message. Could you type it, please?"
    return "Простите, не получилось разобрать голосовое. Напишите, пожалуйста, текстом — или запишите ещё раз."
