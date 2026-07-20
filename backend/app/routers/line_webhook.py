import base64
import hashlib
import hmac
import logging

import httpx
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from ..config import settings
from ..llm_clients import generate_reply
from ..rate_limit import enforce_daily_limit
from ..storage import append_client_message, build_system_prompt_with_context, log_security_event

logger = logging.getLogger("line_webhook")
router = APIRouter()

LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"
LINE_PROFILE_URL = "https://api.line.me/v2/bot/profile/{user_id}"


def _verify_signature(body: bytes, signature: str) -> bool:
    if not settings.line_channel_secret:
        return False
    mac = hmac.new(
        settings.line_channel_secret.encode("utf-8"), body, hashlib.sha256
    ).digest()
    expected = base64.b64encode(mac).decode("utf-8")
    return hmac.compare_digest(expected, signature)


async def _reply_to_line(reply_token: str, text: str) -> None:
    if not settings.line_channel_access_token:
        logger.error("LINE_CHANNEL_ACCESS_TOKEN is not set; cannot send reply")
        return

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.line_channel_access_token}",
    }
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text}],
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(LINE_REPLY_URL, headers=headers, json=payload)
            if resp.status_code >= 400:
                logger.error("LINE reply failed: %s %s", resp.status_code, resp.text)
    except httpx.HTTPError:
        logger.exception("LINE reply request failed")


async def _fetch_display_name(user_id: str) -> str:
    if not settings.line_channel_access_token:
        return user_id
    headers = {"Authorization": f"Bearer {settings.line_channel_access_token}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(LINE_PROFILE_URL.format(user_id=user_id), headers=headers)
            if resp.status_code == 200:
                return resp.json().get("displayName", user_id)
    except httpx.HTTPError:
        logger.exception("Failed to fetch LINE display name")
    return user_id


async def _handle_text_message(reply_token: str, user_id: str, user_text: str) -> None:
    try:
        enforce_daily_limit()
    except HTTPException:
        await _reply_to_line(
            reply_token, "本日の対応件数の上限に達しました。また明日お話しましょうね。"
        )
        return

    display_name = await _fetch_display_name(user_id)
    append_client_message(user_id, display_name, user_text)

    system_prompt = (
        f"{build_system_prompt_with_context()}\n\n【相手の表示名】{display_name}"
    )
    try:
        reply_text = await generate_reply(user_text, system_prompt)
    except Exception:
        logger.exception("LLM generation failed")
        reply_text = "ごめんなさい、少し調子が悪いみたいです。もう一度話しかけてもらえますか？"

    await _reply_to_line(reply_token, reply_text)


@router.post("/webhook/line")
async def line_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_line_signature: str = Header(default=""),
):
    body = await request.body()
    if not _verify_signature(body, x_line_signature):
        log_security_event("line_signature_invalid")
        raise HTTPException(status_code=403, detail="invalid signature")

    payload = await request.json()
    for event in payload.get("events", []):
        if event.get("type") == "message" and event["message"].get("type") == "text":
            reply_token = event["replyToken"]
            user_id = event.get("source", {}).get("userId", "unknown")
            user_text = event["message"]["text"]
            background_tasks.add_task(_handle_text_message, reply_token, user_id, user_text)

    # LINEにはすぐ200を返し、実処理はバックグラウンドで行う
    return {"status": "ok"}
