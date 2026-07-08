"""フロントエンド（index.html）から直接叩く、認証不要のチャット窓口。

管理用トークンは持たせず、1日あたりのメッセージ上限（DAILY_MESSAGE_LIMIT）だけで
コストの暴走を防ぐ。persona編集などの管理操作はここには含めない。
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..llm_clients import generate_reply
from ..rate_limit import enforce_daily_limit
from ..storage import load_persona

logger = logging.getLogger("public_chat")
router = APIRouter()


class PublicChatRequest(BaseModel):
    message: str


@router.post("/api/public-chat")
async def public_chat(req: PublicChatRequest):
    enforce_daily_limit()
    persona = load_persona()
    try:
        reply = await generate_reply(req.message, persona["system_prompt"])
    except Exception:
        logger.exception("generate_reply failed")
        raise HTTPException(status_code=502, detail="応答の生成に失敗しました。もう一度お試しください。")
    return {"reply": reply}
