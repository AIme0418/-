import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import (
    clients,
    dev_chat,
    healy,
    line_webhook,
    oracle_pages,
    persona,
    public_chat,
    security,
)

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Healy Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins or ["*"],
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["*"],
)

app.include_router(line_webhook.router)
app.include_router(healy.router)
app.include_router(persona.router)
app.include_router(dev_chat.router)
app.include_router(public_chat.router)
app.include_router(security.router)
app.include_router(clients.router)
app.include_router(oracle_pages.router)

# カード画像などの公開ファイル（backend/static/ 以下）
STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
# 波動の音（スマホ向けの音のページ）。/sound/ で開く
app.mount("/sound", StaticFiles(directory=STATIC_DIR / "sound", html=True), name="sound")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def health_check():
    return {"status": "ok"}
