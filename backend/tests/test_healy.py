from fastapi.testclient import TestClient

from app import storage
from app.config import settings
from app.routers import healy
from main import app


async def _fake_generate_reply(user_message, system_prompt, provider=None):
    return "この方は自己犠牲というテーマに向き合っている段階のようです。"


def _patch_healy_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "HEALY_LOG_FILE", tmp_path / "healy.jsonl")
    monkeypatch.setattr(storage, "ACTIVE_HEALY_SUMMARY_FILE", tmp_path / "summary.json")
    monkeypatch.setattr(storage, "CLIENT_LOG_FILE", tmp_path / "client_conversations.jsonl")
    monkeypatch.setattr(storage, "CLIENT_LINK_FILE", tmp_path / "client_links.json")
    monkeypatch.setattr(storage, "CLIENT_ANALYSIS_FILE", tmp_path / "client_analyses.json")


def test_coaching_report_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "test-admin-token")
    _patch_healy_storage(tmp_path, monkeypatch)
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
    _patch_healy_storage(tmp_path, monkeypatch)
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
    _patch_healy_storage(tmp_path, monkeypatch)

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


def test_coaching_report_links_by_explicit_line_client_id_and_generates_analysis(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "admin_api_token", "test-admin-token")
    _patch_healy_storage(tmp_path, monkeypatch)
    monkeypatch.setattr(healy, "generate_reply", _fake_generate_reply)
    storage.append_client_message("U123", "たろう", "最近仕事で自己犠牲ばかりしている気がします")

    client = TestClient(app)
    payload = {
        "client_initials": "M.I.",
        "report_datetime": "2026-07-06T19:19:00+09:00",
        "items": [],
        "line_client_id": "U123",
        "line_display_name": "たろう",
    }

    res = client.post(
        "/api/healy-data/coaching-report",
        json=payload,
        headers={"Authorization": "Bearer test-admin-token"},
    )

    assert res.status_code == 200
    assert res.json()["linked_client_id"] == "U123"
    assert storage.resolve_client_id_by_initials("M.I.") == "U123"

    analysis = storage.load_client_analysis("U123")
    assert analysis is not None
    assert analysis["client_initials"] == "M.I."
    assert "自己犠牲" in analysis["analysis"]


def test_coaching_report_reuses_existing_link_without_resubmitting_id(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "test-admin-token")
    _patch_healy_storage(tmp_path, monkeypatch)
    monkeypatch.setattr(healy, "generate_reply", _fake_generate_reply)
    storage.save_client_link("M.I.", "U123", "たろう")

    client = TestClient(app)
    res = client.post(
        "/api/healy-data/coaching-report",
        json={
            "client_initials": "M.I.",
            "report_datetime": "2026-07-06T19:19:00+09:00",
            "items": [],
        },
        headers={"Authorization": "Bearer test-admin-token"},
    )

    assert res.status_code == 200
    assert res.json()["linked_client_id"] == "U123"
    assert storage.load_client_analysis("U123") is not None


def test_coaching_report_resolves_link_by_display_name_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "test-admin-token")
    _patch_healy_storage(tmp_path, monkeypatch)
    monkeypatch.setattr(healy, "generate_reply", _fake_generate_reply)
    storage.append_client_message("U456", "はなこ", "こんにちは")

    client = TestClient(app)
    res = client.post(
        "/api/healy-data/coaching-report",
        json={
            "client_initials": "H.S.",
            "report_datetime": "2026-07-06T19:19:00+09:00",
            "items": [],
            "line_display_name": "はなこ",
        },
        headers={"Authorization": "Bearer test-admin-token"},
    )

    assert res.status_code == 200
    assert res.json()["linked_client_id"] == "U456"
    assert storage.resolve_client_id_by_initials("H.S.") == "U456"


def test_coaching_report_analysis_failure_does_not_break_upload(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "test-admin-token")
    _patch_healy_storage(tmp_path, monkeypatch)
    storage.save_client_link("M.I.", "U123", "たろう")

    async def _summary_ok_then_fail(user_message, system_prompt, provider=None):
        if system_prompt == healy.SUMMARY_SYSTEM_PROMPT:
            return "要約は成功しました。"
        raise RuntimeError("analysis generation failed")

    monkeypatch.setattr(healy, "generate_reply", _summary_ok_then_fail)

    client = TestClient(app)
    res = client.post(
        "/api/healy-data/coaching-report",
        json={
            "client_initials": "M.I.",
            "report_datetime": "2026-07-06T19:19:00+09:00",
            "items": [],
        },
        headers={"Authorization": "Bearer test-admin-token"},
    )

    assert res.status_code == 200
    assert storage.load_active_healy_summary()["summary"] == "要約は成功しました。"
    assert storage.load_client_analysis("U123") is None


def _aura_payload(**overrides):
    payload = {
        "client_initials": "M.I.",
        "report_datetime": "2026-07-28T22:48:49+09:00",
        "main_focus": "私のオーラは強く、安定しています。",
        "chakra_energies": [
            {"chakra": "根のチャクラ", "energy_percent": 58, "level": "低い", "chaos": 3},
        ],
        "items": [
            {
                "chakra": "みぞおちチャクラ",
                "match_percent": 97,
                "session_count": 7,
                "code": "LMXXX",
                "current_state": "自ら決断し、それに対して責任を取ることを恐れています。",
                "current_state_description": "太陽神経叢チャクラが、仙骨チャクラのカラーであるオレンジ色に輝いています。",
                "target_state": "私は、責任を持って自分自身で決断します。",
                "target_state_description": "太陽神経叢チャクラがチャクラカラーの黄色に輝いています。",
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_aura_report_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "test-admin-token")
    _patch_healy_storage(tmp_path, monkeypatch)
    monkeypatch.setattr(healy, "generate_reply", _fake_generate_reply)

    client = TestClient(app)
    res = client.post(
        "/api/healy-data/aura-report",
        json=_aura_payload(),
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert res.status_code == 200

    stored = storage.read_jsonl(tmp_path / "healy.jsonl")
    assert len(stored) == 1
    assert stored[0]["source"] == "healy_aura_report"
    assert stored[0]["data"]["client_initials"] == "M.I."
    assert stored[0]["data"]["items"][0]["current_state"] == "自ら決断し、それに対して責任を取ることを恐れています。"


def test_aura_report_caches_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "test-admin-token")
    _patch_healy_storage(tmp_path, monkeypatch)
    monkeypatch.setattr(healy, "generate_reply", _fake_generate_reply)

    client = TestClient(app)
    client.post(
        "/api/healy-data/aura-report",
        json=_aura_payload(),
        headers={"Authorization": "Bearer test-admin-token"},
    )

    summary = storage.load_active_healy_summary()
    assert summary is not None
    assert summary["client_initials"] == "M.I."


def test_aura_report_links_by_line_client_id_and_generates_analysis(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "test-admin-token")
    _patch_healy_storage(tmp_path, monkeypatch)
    monkeypatch.setattr(healy, "generate_reply", _fake_generate_reply)
    storage.append_client_message("U789", "みちこ", "決断するのが怖いと感じることがあります")

    client = TestClient(app)
    res = client.post(
        "/api/healy-data/aura-report",
        json=_aura_payload(line_client_id="U789", line_display_name="みちこ"),
        headers={"Authorization": "Bearer test-admin-token"},
    )

    assert res.status_code == 200
    assert res.json()["linked_client_id"] == "U789"
    assert storage.resolve_client_id_by_initials("M.I.") == "U789"

    analysis = storage.load_client_analysis("U789")
    assert analysis is not None
    assert analysis["client_initials"] == "M.I."


def test_aura_report_summary_failure_does_not_break_upload(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "test-admin-token")
    _patch_healy_storage(tmp_path, monkeypatch)

    async def _failing_generate_reply(*args, **kwargs):
        raise RuntimeError("no api key")

    monkeypatch.setattr(healy, "generate_reply", _failing_generate_reply)

    client = TestClient(app)
    res = client.post(
        "/api/healy-data/aura-report",
        json=_aura_payload(),
        headers={"Authorization": "Bearer test-admin-token"},
    )

    assert res.status_code == 200
    assert storage.load_active_healy_summary() is None


def test_aura_report_requires_admin_token():
    client = TestClient(app)
    res = client.post("/api/healy-data/aura-report", json={})
    assert res.status_code == 401


def _resonance_payload(**overrides):
    payload = {
        "client_initials": "M.I.",
        "report_datetime": "2026-07-27T19:08:37+09:00",
        "main_focus": "今、自分が最も共鳴できるものは何か？",
        "items": [
            {"topic": "アレルギー経路", "match_percent": 63},
            {"topic": "肌", "match_percent": 49},
        ],
    }
    payload.update(overrides)
    return payload


def test_resonance_report_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "test-admin-token")
    _patch_healy_storage(tmp_path, monkeypatch)
    monkeypatch.setattr(healy, "generate_reply", _fake_generate_reply)

    client = TestClient(app)
    res = client.post(
        "/api/healy-data/resonance-report",
        json=_resonance_payload(),
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert res.status_code == 200

    stored = storage.read_jsonl(tmp_path / "healy.jsonl")
    assert len(stored) == 1
    assert stored[0]["source"] == "healy_resonance_report"
    assert stored[0]["data"]["items"][0]["topic"] == "アレルギー経路"


def test_resonance_report_links_and_generates_analysis(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "test-admin-token")
    _patch_healy_storage(tmp_path, monkeypatch)
    monkeypatch.setattr(healy, "generate_reply", _fake_generate_reply)
    storage.append_client_message("U555", "よしこ", "最近アレルギーっぽい症状が気になります")

    client = TestClient(app)
    res = client.post(
        "/api/healy-data/resonance-report",
        json=_resonance_payload(line_client_id="U555", line_display_name="よしこ"),
        headers={"Authorization": "Bearer test-admin-token"},
    )

    assert res.status_code == 200
    assert res.json()["linked_client_id"] == "U555"
    assert storage.load_client_analysis("U555") is not None


def test_resonance_report_requires_admin_token():
    client = TestClient(app)
    res = client.post("/api/healy-data/resonance-report", json={})
    assert res.status_code == 401


def _meridian_payload(**overrides):
    payload = {
        "client_initials": "M.I.",
        "report_datetime": "2026-07-28T23:03:38+09:00",
        "main_focus": "私の体のすべての部位には、エネルギーが最良に供給されています。",
        "meridian_energies": [
            {"meridian": "少陽三焦経経絡左", "interference_percent": -51},
        ],
        "items": [
            {
                "point_name": "3H 21「耳への門」耳門 (ermen)",
                "match_percent": 98,
                "session_count": 10,
                "code": "LM 0",
                "current_state_notes": [
                    "自分の心の声や、人生を導くような心のサインに気づくことを拒否している。",
                    "自分のアイデンティティに対する怒り。",
                ],
                "target_state": "以下を介した穏やかで時宜にかなった完全調和： フェノール",
            }
        ],
        "programs": [
            {"name": "胆嚢", "match_percent": 57},
        ],
    }
    payload.update(overrides)
    return payload


def test_meridian_report_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "test-admin-token")
    _patch_healy_storage(tmp_path, monkeypatch)
    monkeypatch.setattr(healy, "generate_reply", _fake_generate_reply)

    client = TestClient(app)
    res = client.post(
        "/api/healy-data/meridian-report",
        json=_meridian_payload(),
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert res.status_code == 200

    stored = storage.read_jsonl(tmp_path / "healy.jsonl")
    assert len(stored) == 1
    assert stored[0]["source"] == "healy_meridian_report"
    assert stored[0]["data"]["items"][0]["point_name"] == "3H 21「耳への門」耳門 (ermen)"


def test_meridian_report_links_and_generates_analysis(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "test-admin-token")
    _patch_healy_storage(tmp_path, monkeypatch)
    monkeypatch.setattr(healy, "generate_reply", _fake_generate_reply)
    storage.append_client_message("U666", "けんじ", "自分の気持ちに気づかないふりをしてしまいます")

    client = TestClient(app)
    res = client.post(
        "/api/healy-data/meridian-report",
        json=_meridian_payload(line_client_id="U666", line_display_name="けんじ"),
        headers={"Authorization": "Bearer test-admin-token"},
    )

    assert res.status_code == 200
    assert res.json()["linked_client_id"] == "U666"
    assert storage.load_client_analysis("U666") is not None


def test_meridian_report_requires_admin_token():
    client = TestClient(app)
    res = client.post("/api/healy-data/meridian-report", json={})
    assert res.status_code == 401
