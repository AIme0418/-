from collections import defaultdict, deque

from fastapi.testclient import TestClient

from app import rate_limit, storage
from app.config import settings
from main import app


def test_failed_admin_auth_is_logged(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "correct-token")
    monkeypatch.setattr(storage, "SECURITY_LOG_FILE", tmp_path / "security.jsonl")

    client = TestClient(app)
    client.get("/api/persona", headers={"Authorization": "Bearer wrong-token"})

    events = storage.read_jsonl(tmp_path / "security.jsonl")
    assert len(events) == 1
    assert events[0]["type"] == "admin_auth_failed"


def test_per_ip_limit_exceeded_is_logged(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "SECURITY_LOG_FILE", tmp_path / "security.jsonl")
    monkeypatch.setattr(rate_limit, "_ip_requests", defaultdict(deque))

    for _ in range(rate_limit.PER_IP_MAX_REQUESTS):
        rate_limit.enforce_per_ip_limit("9.9.9.9")
    try:
        rate_limit.enforce_per_ip_limit("9.9.9.9")
    except Exception:
        pass

    events = storage.read_jsonl(tmp_path / "security.jsonl")
    assert len(events) == 1
    assert events[0]["type"] == "per_ip_limit_exceeded"
    assert events[0]["detail"] == "9.9.9.9"


def test_security_events_endpoint_requires_admin_token(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "SECURITY_LOG_FILE", tmp_path / "security.jsonl")
    client = TestClient(app)
    res = client.get("/api/security-events")
    assert res.status_code == 401


def test_security_events_endpoint_lists_events(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "correct-token")
    monkeypatch.setattr(storage, "SECURITY_LOG_FILE", tmp_path / "security.jsonl")
    storage.log_security_event("line_signature_invalid")

    client = TestClient(app)
    res = client.get(
        "/api/security-events", headers={"Authorization": "Bearer correct-token"}
    )

    assert res.status_code == 200
    events = res.json()
    assert len(events) == 1
    assert events[0]["type"] == "line_signature_invalid"
