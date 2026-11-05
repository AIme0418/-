import base64
import hashlib
import hmac
import logging
import time
from collections import OrderedDict
from threading import Lock

import httpx
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from ..admin_commands import handle_admin_command
from ..config import settings
from ..llm_clients import generate_reply
from ..oracle import replies as oracle
from ..rate_limit import enforce_daily_limit
from ..storage import append_client_message, build_system_prompt_with_context, log_security_event

logger = logging.getLogger("line_webhook")
router = APIRouter()

LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"
LINE_PROFILE_URL = "https://api.line.me/v2/bot/profile/{user_id}"


# 同じイベントを二度処理しないための記録（直近のwebhookEventIdをしばらく覚えておく）
_SEEN_TTL_SECONDS = 15 * 60
_SEEN_MAX = 5000
_seen_events: "OrderedDict[str, float]" = OrderedDict()
_seen_lock = Lock()

# これより古いメッセージには返信しない（サーバーが寝ていて遅れて届いたものへの的外れな返信を防ぐ）
STALE_EVENT_SECONDS = 3 * 60


def _is_duplicate(event_id: str) -> bool:
    """初めて見るイベントならFalse（そして記録）、すでに処理済みならTrue。"""
    if not event_id:
        return False
    now = time.monotonic()
    with _seen_lock:
        while _seen_events:
            oldest_id, seen_at = next(iter(_seen_events.items()))
            if now - seen_at > _SEEN_TTL_SECONDS or len(_seen_events) > _SEEN_MAX:
                _seen_events.pop(oldest_id)
            else:
                break
        if event_id in _seen_events:
            return True
        _seen_events[event_id] = now
        return False


def _should_skip(event: dict) -> str | None:
    """返信すべきでないイベントなら理由を返す。"""
    if event.get("deliveryContext", {}).get("isRedelivery"):
        return "redelivery"
    if _is_duplicate(event.get("webhookEventId", "")):
        return "duplicate"
    timestamp_ms = event.get("timestamp")
    if isinstance(timestamp_ms, (int, float)) and time.time() - timestamp_ms / 1000 > STALE_EVENT_SECONDS:
        return "stale"
    return None


def _verify_signature(body: bytes, signature: str) -> bool:
    if not settings.line_channel_secret:
        return False
    mac = hmac.new(
        settings.line_channel_secret.encode("utf-8"), body, hashlib.sha256
    ).digest()
    expected = base64.b64encode(mac).decode("utf-8")
    return hmac.compare_digest(expected, signature)


async def _reply_to_line(reply_token: str, text: str) -> None:
    await _reply_messages(reply_token, [{"type": "text", "text": text}])


async def _reply_messages(reply_token: str, messages: list[dict]) -> None:
    if not settings.line_channel_access_token:
        logger.error("LINE_CHANNEL_ACCESS_TOKEN is not set; cannot send reply")
        return

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.line_channel_access_token}",
    }
    payload = {
        "replyToken": reply_token,
        "messages": messages[:5],  # LINEの返信は1回5通まで
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
    # リッチメニューのオラクルの言葉は、AIより先に処理する（AIを使わないので無料・回数制限なし）
    command = oracle.detect_command(user_text)
    if command is not None:
        kind, card_id = command
        try:
            messages = oracle.build_reply(kind, settings.public_base_url, card_id=card_id, user_id=user_id)
        except Exception:
            logger.exception("Oracle reply failed")
            messages = [{"type": "text", "text": "ごめんなさい、カードをうまく引けませんでした。もう一度ボタンを押してみてくださいね。"}]
        await _reply_messages(reply_token, messages)
        return

    if settings.admin_line_user_id and user_id == settings.admin_line_user_id:
        try:
            admin_reply = await handle_admin_command(user_text)
        except Exception:
            logger.exception("Admin command handling failed")
            admin_reply = None
        if admin_reply is not None:
            await _reply_to_line(reply_token, admin_reply)
            return

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
        f"{build_system_prompt_with_context(user_id)}\n\n【相手の表示名】{display_name}"
    )
    try:
        reply_text = await generate_reply(user_text, system_prompt)
    except Exception:
        logger.exception("LLM generation failed")
        reply_text = "ごめんなさい、少し調子が悪いみたいです。もう一度話しかけてもらえますか？"

    await _reply_to_line(reply_token, reply_text)


async def _handle_postback(reply_token: str, user_id: str, data: str) -> None:
    """カードの「開く」「メニューに戻る」ボタン。AIは使わない。"""
    try:
        messages = oracle.build_postback_reply(user_id, data, settings.public_base_url)
    except Exception:
        logger.exception("Oracle postback failed")
        messages = [{"type": "text", "text": "ごめんなさい、カードをうまく開けませんでした。もう一度メニューから引いてみてくださいね。"}]
    if messages:
        await _reply_messages(reply_token, messages)


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
            skip_reason = _should_skip(event)
            if skip_reason:
                logger.info("Skipping LINE event (%s): %s", skip_reason, event.get("webhookEventId"))
                continue
            reply_token = event["replyToken"]
            user_id = event.get("source", {}).get("userId", "unknown")
            user_text = event["message"]["text"]
            background_tasks.add_task(_handle_text_message, reply_token, user_id, user_text)
        elif event.get("type") == "postback":
            skip_reason = _should_skip(event)
            if skip_reason:
                logger.info("Skipping LINE event (%s): %s", skip_reason, event.get("webhookEventId"))
                continue
            background_tasks.add_task(
                _handle_postback,
                event["replyToken"],
                event.get("source", {}).get("userId", "unknown"),
                event.get("postback", {}).get("data", ""),
            )

    # LINEにはすぐ200を返し、実処理はバックグラウンドで行う
    return {"status": "ok"}
