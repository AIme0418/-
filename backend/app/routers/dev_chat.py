"""LINEなしでローカルから愛美さんの応答を試すための開発用エンドポイント。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth import require_admin_token
from ..llm_clients import generate_reply
from ..storage import load_persona

router = APIRouter(dependencies=[Depends(require_admin_token)])


class ChatRequest(BaseModel):
    message: str
    provider: str | None = None  # gemini / claude / openai。省略時はDEFAULT_MODEL_PROVIDER


@router.post("/api/chat")
async def dev_chat(req: ChatRequest):
    persona = load_persona()
    reply = await generate_reply(req.message, persona["system_prompt"], req.provider)
    return {"reply": reply}
