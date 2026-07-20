"""LINEで相談してきたクライアントの会話履歴を、あとから振り返るための管理者用エンドポイント。

原文は届いた時点でそのまま保存しておき、要約は見たいときにその場でAIに作らせる
（毎メッセージごとに要約を作ると呼び出し回数が倍になるため、必要なときだけ生成する）。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from ..auth import require_admin_token
from ..llm_clients import generate_reply
from ..storage import get_client_messages, list_clients

logger = logging.getLogger("clients")
router = APIRouter(dependencies=[Depends(require_admin_token)])

SUMMARY_SYSTEM_PROMPT = (
    "あなたは、ヒーラーが担当するクライアントとの会話履歴を読んで、"
    "そのクライアントがどんな人か、何を相談してきたかを、あとで振り返れるように"
    "3〜5文程度の日本語で要約するアシスタントです。個人情報や医療的な断定は避け、"
    "会話の傾向や大切にしていそうなことを中心にまとめてください。"
)


@router.get("/api/clients")
def get_clients():
    return list_clients()


@router.get("/api/clients/{client_id}")
def get_client_history(client_id: str, limit: int = 200):
    return get_client_messages(client_id, limit=limit)


@router.get("/api/clients/{client_id}/summary")
async def get_client_summary(client_id: str):
    messages = get_client_messages(client_id)
    if not messages:
        raise HTTPException(status_code=404, detail="この方の会話履歴が見つかりません。")

    display_name = messages[-1]["display_name"]
    transcript = "\n".join(f"・{m['message']}" for m in messages)

    try:
        summary = await generate_reply(transcript, SUMMARY_SYSTEM_PROMPT)
    except Exception:
        logger.exception("Client summary generation failed")
        raise HTTPException(status_code=502, detail="要約の生成に失敗しました。もう一度お試しください。")

    return {
        "client_id": client_id,
        "display_name": display_name,
        "message_count": len(messages),
        "summary": summary,
    }
