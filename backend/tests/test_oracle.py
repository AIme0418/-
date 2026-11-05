import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.oracle import deck, replies
from app.routers import line_webhook

BASE = "https://example.onrender.com"


def test_deck_has_44_unique_complete_cards():
    cards = deck.load_cards()
    assert len(cards) == 44
    assert sorted(c["id"] for c in cards) == list(range(1, 45))
    assert len({c["name"] for c in cards}) == 44
    for c in cards:
        for field in ("name", "keyword", "message", "love", "work", "healing"):
            assert c[field].strip(), (c["id"], field)


def test_three_cards_never_repeat():
    for _ in range(300):
        ids = [c["id"] for c in deck.draw(3)]
        assert len(set(ids)) == 3


@pytest.mark.parametrize(
    "text,kind",
    [
        ("ワンオラクル", "one"),
        (" スリーオラクル ", "three"),
        ("恋愛", "love"),
        ("金運", "work"),
        ("癒し", "healing"),
        ("カード一覧", "list"),
        ("ｶｰﾄﾞ一覧", "list"),
    ],
)
def test_rich_menu_words_are_detected(text, kind):
    assert replies.detect_command(text) == (kind, None)


def test_card_number_and_normal_chat():
    assert replies.detect_command("カード７") == ("detail", 7)
    assert replies.detect_command("カード 12") == ("detail", 12)
    assert replies.detect_command("恋愛の悩みを聞いてほしい") is None
    assert replies.detect_command("こんにちは") is None


@pytest.mark.parametrize("kind", ["one", "three", "love", "work", "healing", "list"])
@pytest.mark.parametrize("base", [BASE, ""])
def test_replies_follow_line_limits(kind, base):
    messages = replies.build_reply(kind, base)
    assert 1 <= len(messages) <= 5
    for m in messages:
        if m["type"] == "flex":
            assert len(m["altText"]) <= 400
            assert len(json.dumps(m["contents"], ensure_ascii=False).encode()) < 30_000
    if kind != "one":  # ワンオラクルは裏面のボタンで進むので、クイックリプライなし
        qr = messages[-1]["quickReply"]["items"]
        assert len(qr) <= 13
        assert all(len(i["action"]["label"]) <= 20 for i in qr)


def test_three_oracle_has_past_present_future_and_summary():
    msg = replies.build_reply("three", BASE)[0]
    bubbles = msg["contents"]["contents"]
    assert len(bubbles) == 4
    labels = [b["body"]["contents"][0]["text"] for b in bubbles[:3]]
    assert labels == ["✦ 過去のカード ✦", "✦ 現在のカード ✦", "✦ 未来のカード ✦"]


def test_image_used_only_when_registered(tmp_path, monkeypatch):
    monkeypatch.setattr(deck, "CARD_IMAGE_DIR", tmp_path)
    assert deck.card_image_url(3, BASE) is None
    (tmp_path / "03.jpg").write_bytes(b"x")
    assert deck.card_image_url(3, BASE) == f"{BASE}/static/cards/03.jpg"
    assert deck.card_image_url(3, "http://insecure") is None  # LINEはhttpsのみ


def _patch_line(monkeypatch):
    sent = []

    async def fake_reply_messages(token, messages):
        sent.append(messages)

    async def fail_ai(*a, **k):
        raise AssertionError("oracle words must not go to the AI")

    def fail_limit():
        raise AssertionError("oracle words must not count toward the AI daily limit")

    monkeypatch.setattr(line_webhook, "_reply_messages", fake_reply_messages)
    monkeypatch.setattr(line_webhook, "generate_reply", fail_ai)
    monkeypatch.setattr(line_webhook, "enforce_daily_limit", fail_limit)
    return sent


def test_menu_word_goes_to_oracle_not_ai(monkeypatch):
    sent = _patch_line(monkeypatch)
    asyncio.run(line_webhook._handle_text_message("tok", "Uuser", "ワンオラクル"))
    assert len(sent) == 1
    assert [m["type"] for m in sent[0]] == ["text", "flex"]


def _event(event_id, text="ワンオラクル", redelivery=False, age_seconds=0):
    return {
        "type": "message",
        "webhookEventId": event_id,
        "deliveryContext": {"isRedelivery": redelivery},
        "timestamp": int((time.time() - age_seconds) * 1000),
        "replyToken": "tok",
        "source": {"userId": "Uuser"},
        "message": {"type": "text", "text": text},
    }


def test_webhook_skips_duplicates_redeliveries_and_old_events(monkeypatch):
    from main import app

    monkeypatch.setattr(settings, "line_channel_secret", "s")
    monkeypatch.setattr(line_webhook, "_verify_signature", lambda body, sig: True)
    handled = []

    async def fake_handle(token, user, text):
        handled.append(text)

    monkeypatch.setattr(line_webhook, "_handle_text_message", fake_handle)
    client = TestClient(app)

    events = [
        _event("evt-1", "1回目"),
        _event("evt-1", "同じイベントの重複"),
        _event("evt-2", "再送", redelivery=True),
        _event("evt-3", "10分前の古いメッセージ", age_seconds=600),
        _event("evt-4", "2回目"),
    ]
    r = client.post("/webhook/line", json={"events": events}, headers={"x-line-signature": "x"})
    assert r.status_code == 200
    assert handled == ["1回目", "2回目"]


def test_card_list_page_shows_all_cards():
    from main import app

    r = TestClient(app).get("/cards")
    assert r.status_code == 200
    assert r.text.count('class="card"') == 44
