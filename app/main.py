import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from . import ai, config, domain, max_bot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
WEB = config.ROOT / "web"


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(max_bot.run())
    yield
    task.cancel()


app = FastAPI(title=config.PROJECT_NAME, lifespan=lifespan)


class ChatIn(BaseModel):
    history: list[dict]


@app.get("/api/health")
async def health():
    return {"ok": True, "ai": ai.enabled(), "max_bot": bool(config.MAX_BOT_TOKEN), "model": config.MODEL}


@app.get("/api/config")
async def cfg():
    return {"name": config.PROJECT_NAME, "welcome": domain.WELCOME, "quick": [t for t, _ in domain.QUICK_ACTIONS]}


@app.post("/api/chat")
async def chat(inp: ChatIn):
    hist = [{"role": m["role"], "content": str(m["content"])[:4000]} for m in inp.history if m.get("role") in ("user", "assistant")]
    return {"answer": await ai.answer(hist)}


app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/")
async def index():
    return FileResponse(WEB / "index.html")
