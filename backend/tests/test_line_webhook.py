import asyncio
import base64
import hashlib
import hmac

from app import storage
from app.config import settings
from app.routers import line_webhook
from app.routers.line_webhook import _verify_signature


def _sign(secret: str, body: bytes) -> str:
    mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(mac).decode("utf-8")


def test_valid_signature_is_accepted(monkeypatch):
    monkeypatch.setattr(settings, "line_channel_secret", "test-secret")
    body = b'{"events": []}'
    signature = _sign("test-secret", body)

    assert _verify_signature(body, signature) is True


def test_invalid_signature_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "line_channel_secret", "test-secret")
    body = b'{"events": []}'

    assert _verify_signature(body, "not-the-real-signature") is False


def test_missing_secret_rejects_everything(monkeypatch):
    monkeypatch.setattr(settings, "line_channel_secret", "")
    body = b'{"events": []}'
    signature = _sign("anything", body)

    assert _verify_signature(body, signature) is False


def test_admin_command_bypasses_normal_chat_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "admin_line_user_id", "Uadmin")
    monkeypatch.setattr(storage, "CLIENT_LOG_FILE", tmp_path / "clients.jsonl")

    replies = []

    async def _fake_reply_to_line(reply_token, text):
        replies.append(text)

    async def _fake_handle_admin_command(user_text):
        return "管理コマンドの応答です"

    async def _fail_generate_reply(*args, **kwargs):
        raise AssertionError("admin command should not fall through to normal chat")

    monkeypatch.setattr(line_webhook, "_reply_to_line", _fake_reply_to_line)
    monkeypatch.setattr(line_webhook, "handle_admin_command", _fake_handle_admin_command)
    monkeypatch.setattr(line_webhook, "generate_reply", _fail_generate_reply)

    asyncio.run(line_webhook._handle_text_message("token", "Uadmin", "クライアント一覧"))

    assert replies == ["管理コマンドの応答です"]
    # 管理コマンドは通常のクライアント会話ログには残らない
    assert storage.list_clients() == []


def test_non_admin_falls_through_to_normal_chat(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "admin_line_user_id", "Uadmin")
    monkeypatch.setattr(storage, "CLIENT_LOG_FILE", tmp_path / "clients.jsonl")
    monkeypatch.setattr(storage, "USAGE_FILE", tmp_path / "usage.json")

    replies = []

    async def _fake_reply_to_line(reply_token, text):
        replies.append(text)

    async def _fake_fetch_display_name(user_id):
        return "たろう"

    async def _fake_generate_reply(user_text, system_prompt):
        return "こんにちは、たろうさん"

    monkeypatch.setattr(line_webhook, "_reply_to_line", _fake_reply_to_line)
    monkeypatch.setattr(line_webhook, "_fetch_display_name", _fake_fetch_display_name)
    monkeypatch.setattr(line_webhook, "generate_reply", _fake_generate_reply)

    asyncio.run(line_webhook._handle_text_message("token", "Ustranger", "こんにちは"))

    assert replies == ["こんにちは、たろうさん"]
    clients = storage.list_clients()
    assert len(clients) == 1
    assert clients[0]["display_name"] == "たろう"
