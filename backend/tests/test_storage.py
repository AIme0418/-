from app import storage


def test_persona_save_and_load(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "PERSONA_FILE", tmp_path / "persona.json")

    saved = storage.save_persona({"name": "テスト", "system_prompt": "こんにちは"})
    assert saved["name"] == "テスト"

    loaded = storage.load_persona()
    assert loaded == {"name": "テスト", "system_prompt": "こんにちは"}


def test_load_persona_falls_back_to_default(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "PERSONA_FILE", tmp_path / "does_not_exist.json")

    loaded = storage.load_persona()
    assert loaded == storage.DEFAULT_PERSONA


def test_daily_usage_limit_blocks_after_threshold(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "USAGE_FILE", tmp_path / "usage.json")

    ok1, count1 = storage.increment_and_check_daily_usage(limit=2)
    ok2, count2 = storage.increment_and_check_daily_usage(limit=2)
    ok3, count3 = storage.increment_and_check_daily_usage(limit=2)

    assert (ok1, count1) == (True, 1)
    assert (ok2, count2) == (True, 2)
    assert (ok3, count3) == (False, 2)


def test_healy_and_external_gpt_event_roundtrip(tmp_path, monkeypatch):
    healy_log = tmp_path / "healy.jsonl"
    monkeypatch.setattr(storage, "HEALY_LOG_FILE", healy_log)

    storage.append_healy_event({"source": "healy_device", "data": {"freq": 1234}})
    events = storage.read_jsonl(healy_log)

    assert len(events) == 1
    assert events[0]["source"] == "healy_device"
    assert events[0]["data"]["freq"] == 1234


def test_active_healy_summary_save_and_load(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ACTIVE_HEALY_SUMMARY_FILE", tmp_path / "summary.json")

    assert storage.load_active_healy_summary() is None

    storage.save_active_healy_summary("M.I.", "自己犠牲というテーマに向き合っています。")
    summary = storage.load_active_healy_summary()

    assert summary == {
        "client_initials": "M.I.",
        "summary": "自己犠牲というテーマに向き合っています。",
    }


def test_build_system_prompt_without_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "PERSONA_FILE", tmp_path / "persona.json")
    monkeypatch.setattr(storage, "ACTIVE_HEALY_SUMMARY_FILE", tmp_path / "summary.json")

    prompt = storage.build_system_prompt_with_context()

    assert prompt == storage.DEFAULT_PERSONA["system_prompt"]


def test_build_system_prompt_with_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "PERSONA_FILE", tmp_path / "persona.json")
    monkeypatch.setattr(storage, "ACTIVE_HEALY_SUMMARY_FILE", tmp_path / "summary.json")
    storage.save_active_healy_summary("M.I.", "自己犠牲というテーマに向き合っています。")

    prompt = storage.build_system_prompt_with_context()

    assert storage.DEFAULT_PERSONA["system_prompt"] in prompt
    assert "M.I." in prompt
    assert "自己犠牲というテーマに向き合っています。" in prompt
