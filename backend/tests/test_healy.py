from fastapi.testclient import TestClient

from app import storage
from app.config import settings
from app.routers import healy
from main import app


async def _fake_generate_reply(user_message, system_prompt, provider=None):
    return "この方は自己犠牲というテーマに向き合っている段階のようです。"


def test_coaching_report_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "test-admin-token")
    monkeypatch.setattr(storage, "HEALY_LOG_FILE", tmp_path / "healy.jsonl")
    monkeypatch.setattr(storage, "ACTIVE_HEALY_SUMMARY_FILE", tmp_path / "summary.json")
    monkeypatch.setattr(healy, "generate_reply", _fake_generate_reply)

    client = TestClient(app)
    payload = {
        "client_initials": "M.I.",
        "report_datetime": "2026-07-06T19:19:00+09:00",
        "main_focus": "私は裕福であり、幸福になる価値があります。",
        "items": [
            {
                "category": "焦点を特定する",
                "match_percent": 95,
                "session_count": 7,
                "code": "D 1E12",
                "target_state": "私は自分の利益と全体の利益のために次の焦点を理解し実行する力を経験する：自己犠牲",
            }
        ],
    }

    res = client.post(
        "/api/healy-data/coaching-report",
        json=payload,
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert res.status_code == 200

    stored = storage.read_jsonl(tmp_path / "healy.jsonl")
    assert len(stored) == 1
    assert stored[0]["data"]["client_initials"] == "M.I."
    assert stored[0]["data"]["items"][0]["match_percent"] == 95


def test_coaching_report_caches_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "test-admin-token")
    monkeypatch.setattr(storage, "HEALY_LOG_FILE", tmp_path / "healy.jsonl")
    monkeypatch.setattr(storage, "ACTIVE_HEALY_SUMMARY_FILE", tmp_path / "summary.json")
    monkeypatch.setattr(healy, "generate_reply", _fake_generate_reply)

    client = TestClient(app)
    payload = {
        "client_initials": "M.I.",
        "report_datetime": "2026-07-06T19:19:00+09:00",
        "main_focus": "私は裕福であり、幸福になる価値があります。",
        "items": [],
    }

    client.post(
        "/api/healy-data/coaching-report",
        json=payload,
        headers={"Authorization": "Bearer test-admin-token"},
    )

    summary = storage.load_active_healy_summary()
    assert summary is not None
    assert summary["client_initials"] == "M.I."
    assert "自己犠牲" in summary["summary"]


def test_coaching_report_summary_failure_does_not_break_upload(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "test-admin-token")
    monkeypatch.setattr(storage, "HEALY_LOG_FILE", tmp_path / "healy.jsonl")
    monkeypatch.setattr(storage, "ACTIVE_HEALY_SUMMARY_FILE", tmp_path / "summary.json")

    async def _failing_generate_reply(*args, **kwargs):
        raise RuntimeError("no api key")

    monkeypatch.setattr(healy, "generate_reply", _failing_generate_reply)

    client = TestClient(app)
    res = client.post(
        "/api/healy-data/coaching-report",
        json={"client_initials": "M.I.", "report_datetime": "2026-07-06T19:19:00+09:00"},
        headers={"Authorization": "Bearer test-admin-token"},
    )

    assert res.status_code == 200
    assert storage.load_active_healy_summary() is None


def test_coaching_report_requires_admin_token():
    client = TestClient(app)
    res = client.post("/api/healy-data/coaching-report", json={})
    assert res.status_code == 401
