import asyncio

from app import admin_commands, storage


async def _fake_summarize_client(client_id):
    return {
        "client_id": client_id,
        "display_name": "めぐみ",
        "message_count": 2,
        "summary": "穏やかに近況を話してくれる方のようです。",
    }


def test_unrecognized_text_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "CLIENT_LOG_FILE", tmp_path / "clients.jsonl")
    result = asyncio.run(admin_commands.handle_admin_command("こんにちは"))
    assert result is None


def test_client_list_command(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "CLIENT_LOG_FILE", tmp_path / "clients.jsonl")
    storage.append_client_message("U1", "めぐみ", "こんにちは")
    storage.append_client_message("U2", "たろう", "はじめまして")

    result = asyncio.run(admin_commands.handle_admin_command("クライアント一覧"))

    assert "めぐみ" in result
    assert "たろう" in result


def test_client_list_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "CLIENT_LOG_FILE", tmp_path / "clients.jsonl")
    result = asyncio.run(admin_commands.handle_admin_command("クライアント一覧"))
    assert "いません" in result


def test_summary_command_without_name(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "CLIENT_LOG_FILE", tmp_path / "clients.jsonl")
    result = asyncio.run(admin_commands.handle_admin_command("要約"))
    assert "名前を指定" in result


def test_summary_command_no_match(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "CLIENT_LOG_FILE", tmp_path / "clients.jsonl")
    storage.append_client_message("U1", "めぐみ", "こんにちは")

    result = asyncio.run(admin_commands.handle_admin_command("要約 存在しない人"))

    assert "見つかりませんでした" in result


def test_summary_command_match(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "CLIENT_LOG_FILE", tmp_path / "clients.jsonl")
    monkeypatch.setattr(admin_commands, "summarize_client", _fake_summarize_client)
    storage.append_client_message("U1", "めぐみ", "こんにちは")

    result = asyncio.run(admin_commands.handle_admin_command("要約 めぐみ"))

    assert "めぐみさんの要約" in result
    assert "穏やかに近況" in result


def test_security_command_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "SECURITY_LOG_FILE", tmp_path / "security.jsonl")
    result = admin_commands._security_reply()
    assert "ありません" in result


def test_security_command_lists_recent_events(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "SECURITY_LOG_FILE", tmp_path / "security.jsonl")
    storage.log_security_event("admin_auth_failed")
    storage.log_security_event("line_signature_invalid")

    result = admin_commands._security_reply()

    assert "admin_auth_failed" in result
    assert "line_signature_invalid" in result
