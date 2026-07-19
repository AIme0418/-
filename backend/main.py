import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import dev_chat, healy, line_webhook, persona, public_chat, security

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


@app.get("/")
def health_check():
    return {"status": "ok"}
