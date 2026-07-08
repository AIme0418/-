import base64
import hashlib
import hmac

from app.config import settings
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
