from fastapi.testclient import TestClient

from app import storage
from app.config import settings
from app.routers import clients
from main import app


async def _fake_generate_reply(user_message, system_prompt, provider=None):
    return "穏やかに近況を話してくれる方のようです。"


def test_append_and_list_clients(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "CLIENT_LOG_FILE", tmp_path / "clients.jsonl")

    storage.append_client_message("U123", "めぐみ", "こんにちは")
    storage.append_client_message("U123", "めぐみ", "最近眠れなくて")
    storage.append_client_message("U456", "たろう", "はじめまして")

    all_clients = storage.list_clients()
    by_id = {c["client_id"]: c for c in all_clients}

    assert by_id["U123"]["message_count"] == 2
    assert by_id["U123"]["display_name"] == "めぐみ"
    assert by_id["U456"]["message_count"] == 1


def test_get_client_messages_filters_by_id(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "CLIENT_LOG_FILE", tmp_path / "clients.jsonl")

    storage.append_client_message("U123", "めぐみ", "こんにちは")
    storage.append_client_message("U456", "たろう", "はじめまして")

    messages = storage.get_client_messages("U123")
    assert len(messages) == 1
    assert messages[0]["message"] == "こんにちは"


def test_client_endpoints_require_admin_token(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "CLIENT_LOG_FILE", tmp_path / "clients.jsonl")
    client = TestClient(app)

    assert client.get("/api/clients").status_code == 401
    assert client.get("/api/clients/U123").status_code == 401
    assert client.get("/api/clients/U123/summary").status_code == 401


def test_client_summary_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "test-admin-token")
    monkeypatch.setattr(storage, "CLIENT_LOG_FILE", tmp_path / "clients.jsonl")
    monkeypatch.setattr(clients, "generate_reply", _fake_generate_reply)

    storage.append_client_message("U123", "めぐみ", "最近眠れなくて")

    client = TestClient(app)
    res = client.get(
        "/api/clients/U123/summary",
        headers={"Authorization": "Bearer test-admin-token"},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["display_name"] == "めぐみ"
    assert body["message_count"] == 1
    assert "穏やか" in body["summary"]


def test_client_summary_404_when_no_history(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "test-admin-token")
    monkeypatch.setattr(storage, "CLIENT_LOG_FILE", tmp_path / "clients.jsonl")

    client = TestClient(app)
    res = client.get(
        "/api/clients/no-such-user/summary",
        headers={"Authorization": "Bearer test-admin-token"},
    )

    assert res.status_code == 404
