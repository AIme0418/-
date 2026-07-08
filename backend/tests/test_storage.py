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
