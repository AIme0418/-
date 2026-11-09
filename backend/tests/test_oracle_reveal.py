"""ワンオラクルの演出（裏面 → カードを開く → 結果）のテスト。"""

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.oracle import deck, replies, sessions
from app.routers import line_webhook

BASE = "https://example.onrender.com"


@pytest.fixture(autouse=True)
def _clean_sessions():
    sessions._sessions.clear()
    yield
    sessions._sessions.clear()


def _open_data(user="Uuser"):
    # チャットの中で引く方法（公開URLがないときや、以前に届いたボタン用に残している）
    intro = replies._back_intro("one", user, BASE)
    button = intro[1]["contents"]["footer"]["contents"][0]["action"]
    return intro, button


def test_intro_shows_guide_text_and_card_back_with_open_button():
    intro, button = _open_data()
    assert intro[0] == {"type": "text", "text": replies.ONE_INTRO_TEXT}
    hero = intro[1]["contents"]["hero"]
    assert hero["url"] == f"{BASE}/static/ui/oracle_back_wide.jpg"
    assert hero["aspectRatio"] == "4:3"  # カード全体が1画面に収まる横長
    assert button["type"] == "postback" and button["label"] == "✨ カードを開く"
    assert len(button["data"]) <= 300  # LINEのpostbackデータ上限


def test_card_is_not_decided_until_button_is_pressed():
    _open_data()
    (s,) = sessions._sessions.values()
    assert s["cards"] == []


def test_open_reveals_one_card_with_again_and_menu_buttons():
    _, button = _open_data()
    msgs = replies.build_postback_reply("Uuser", button["data"], BASE)
    assert msgs[0]["text"] == replies.REVEAL_TEXT
    bubble = msgs[1]["contents"]
    buttons = replies.footer_buttons(bubble["footer"])
    labels = [b["action"]["label"] for b in buttons]
    assert labels == ["🔮 もう一度引く", "💜 メニューに戻る", "🎵 波動の音でひと休み"]
    assert buttons[0]["action"]["text"] == "ワンオラクル"
    assert buttons[1]["action"]["inputOption"] == "openRichMenu"


def test_result_shows_card_picture_next_to_name_without_tall_hero():
    _, button = _open_data()
    assert button["inputOption"] == "closeRichMenu"  # 開くと同時にリッチメニューを閉じる
    msgs = replies.build_postback_reply("Uuser", button["data"], BASE)
    bubble = msgs[1]["contents"]
    assert "hero" not in bubble  # 横幅いっぱいの縦長画像はやめた
    head = bubble["body"]["contents"][0]
    assert head["layout"] == "horizontal"
    thumb = head["contents"][0]["contents"][0]
    (s,) = sessions._sessions.values()
    card = deck.get_card(s["cards"][0])
    assert thumb["type"] == "image" and thumb["aspectRatio"] == "2:3"
    assert thumb["url"].endswith(f"/static/cards/{card['id']:02d}.jpg")
    names = [c.get("text") for c in head["contents"][1]["contents"]]
    assert card["name"] in names and f"「{card['keyword']}」" in names


def test_mashing_the_button_gives_only_one_result():
    _, button = _open_data()
    first = replies.build_postback_reply("Uuser", button["data"], BASE)
    for _ in range(5):
        assert replies.build_postback_reply("Uuser", button["data"], BASE) is None
    (s,) = sessions._sessions.values()
    card = deck.get_card(s["cards"][0])
    assert first[1]["altText"].endswith(f"{card['name']}「{card['keyword']}」")


def test_late_second_press_gets_gentle_note_not_a_new_card(monkeypatch):
    _, button = _open_data()
    replies.build_postback_reply("Uuser", button["data"], BASE)
    (s,) = sessions._sessions.values()
    cards = list(s["cards"])
    s["opened_at"] -= 60
    msgs = replies.build_postback_reply("Uuser", button["data"], BASE)
    assert msgs[0]["text"] == replies.ALREADY_TEXT
    assert s["cards"] == cards


def test_expired_button(monkeypatch):
    _, button = _open_data()
    (s,) = sessions._sessions.values()
    s["created"] -= sessions.SESSION_TTL_SECONDS + 1
    msgs = replies.build_postback_reply("Uuser", button["data"], BASE)
    assert msgs[0]["text"] == replies.EXPIRED_TEXT
    assert s["cards"] == []


def test_button_still_works_after_server_restart_within_time_limit():
    _, button = _open_data()
    sessions._sessions.clear()  # 再起動でメモリが消えた想定
    msgs = replies.build_postback_reply("Uuser", button["data"], BASE)
    assert msgs[0]["text"] == replies.REVEAL_TEXT


def test_old_button_after_restart_is_expired():
    data = sessions.urlencode({"oracle": "open", "kind": "one", "sid": "x", "ts": int(time.time()) - 7200})
    msgs = replies.build_postback_reply("Uuser", data, BASE)
    assert msgs[0]["text"] == replies.EXPIRED_TEXT


def test_someone_elses_button_does_not_open():
    _, button = _open_data(user="Ualice")
    msgs = replies.build_postback_reply("Ubob", button["data"], BASE)
    assert msgs[0]["text"] == replies.EXPIRED_TEXT


def test_menu_button_sends_nothing():
    assert replies.build_postback_reply("Uuser", "oracle=menu", BASE) is None


def test_angel_word_is_shown_when_registered(monkeypatch):
    card = dict(deck.get_card(1), angel_word="あなたは光そのもの")
    bubble = replies._card_bubble(card, BASE, label="x", main_text="y")
    assert any(c.get("text") == "あなたは光そのもの" for c in bubble["body"]["contents"])


def test_webhook_routes_postback_and_skips_duplicates(monkeypatch):
    from main import app

    monkeypatch.setattr(line_webhook, "_verify_signature", lambda b, s: True)
    sent = []

    async def fake_reply(token, messages):
        sent.append(messages)

    monkeypatch.setattr(line_webhook, "_reply_messages", fake_reply)

    async def fail_ai(*a, **k):
        raise AssertionError("postback must not go to AI")

    monkeypatch.setattr(line_webhook, "generate_reply", fail_ai)

    _, button = _open_data()
    ev = {
        "type": "postback",
        "webhookEventId": "pb-1",
        "deliveryContext": {"isRedelivery": False},
        "timestamp": int(time.time() * 1000),
        "replyToken": "tok",
        "source": {"userId": "Uuser"},
        "postback": {"data": button["data"]},
    }
    r = TestClient(app).post("/webhook/line", json={"events": [ev, ev]}, headers={"x-line-signature": "x"})
    assert r.status_code == 200
    assert len(sent) == 1 and sent[0][0]["text"] == replies.REVEAL_TEXT


# ---- スリーオラクル ----


def _press(user, msgs):
    """返信の中の最後の「開く」ボタンを押す。"""
    contents = msgs[-1]["contents"]
    if contents["type"] == "carousel":
        contents = contents["contents"][-1]
    action = replies.footer_buttons(contents["footer"])[-1]["action"]
    assert action["type"] == "postback"
    return replies.build_postback_reply(user, action["data"], BASE), action


def test_three_oracle_opens_one_card_at_a_time_without_repeats():
    for _ in range(50):
        sessions._sessions.clear()
        intro = replies.build_reply("three", BASE, user_id="Uuser")
        assert intro[0]["text"] == replies.THREE_INTRO_TEXT
        assert intro[1]["contents"]["footer"]["contents"][0]["text"] == "✦ 1枚目：過去・背景 ✦"

        m1, _ = _press("Uuser", intro)
        assert m1[0]["text"] == "✨ 1枚目「過去・背景」のカードは……"
        assert len(m1) == 2  # 次の裏面を別に送らず、結果の中に「2枚目を開く」がある
        assert replies.footer_buttons(m1[-1]["contents"]["footer"])[-1]["action"]["label"] == "✨ 2枚目を開く"
        m2, _ = _press("Uuser", m1)
        assert m2[0]["text"] == "✨ 2枚目「現在の状況」のカードは……"
        m3, _ = _press("Uuser", m2)
        assert m3[0]["text"] == "✨ 3枚目「未来へのヒント」のカードは……"
        assert m3[-1]["altText"] == "✦ 3枚からの総合メッセージ ✦"
        third, summary = m3[-1]["contents"]["contents"]  # 3枚目 → 横スライドで総合メッセージ
        assert "hero" not in third and "hero" not in summary
        buttons = replies.footer_buttons(summary["footer"])
        labels = [b["action"]["label"] for b in buttons]
        assert labels == ["🔮 もう一度引く", "💜 メニューに戻る", "🎵 波動の音でひと休み"]
        assert buttons[0]["action"]["text"] == "スリーオラクル"

        (s,) = sessions._sessions.values()
        assert len(set(s["cards"])) == 3
        for m in (m1, m2, m3):
            assert len(m) <= 5


def test_three_oracle_old_step_button_cannot_redraw():
    intro = replies.build_reply("three", BASE, user_id="Uuser")
    m1, first_action = _press("Uuser", intro)
    _press("Uuser", m1)
    (s,) = sessions._sessions.values()
    before = list(s["cards"])
    assert replies.build_postback_reply("Uuser", first_action["data"], BASE) is None
    assert s["cards"] == before


def test_three_oracle_resumes_after_restart_without_repeats():
    intro = replies.build_reply("three", BASE, user_id="Uuser")
    m1, _ = _press("Uuser", intro)
    (s,) = sessions._sessions.values()
    first = s["cards"][0]
    sessions._sessions.clear()  # 再起動
    m2, _ = _press("Uuser", m1)
    assert m2[0]["text"] == "✨ 2枚目「現在の状況」のカードは……"
    (s,) = sessions._sessions.values()
    assert s["cards"][0] == first and len(set(s["cards"])) == 2


def test_tampered_step_is_rejected():
    data = sessions.urlencode({"oracle": "open", "kind": "three", "sid": "x", "ts": int(time.time()), "step": 3})
    msgs = replies.build_postback_reply("Uuser", data, BASE)
    assert msgs[0]["text"] == replies.EXPIRED_TEXT


# ---- 恋愛・金運・癒し ----


@pytest.mark.parametrize("kind,word,field", [("love", "恋愛", "love"), ("work", "金運", "work"), ("healing", "癒し", "healing")])
def test_theme_menus_use_card_back_and_keep_theme_message(kind, word, field):
    intro = replies.build_reply(kind, BASE, user_id="Uuser")
    assert intro[0]["text"].startswith(replies.THEMES[kind]["icon"])
    msgs, _ = _press("Uuser", intro)
    assert msgs[0]["text"] == replies.REVEAL_TEXT
    bubble = msgs[1]["contents"]
    (s,) = sessions._sessions.values()
    card = deck.get_card(s["cards"][0])
    texts = [c.get("text") for c in bubble["body"]["contents"]]
    assert card[field] in texts and card["message"] in texts
    assert replies.footer_buttons(bubble["footer"])[0]["action"]["text"] == word


def test_list_and_card_number_are_unchanged():
    assert replies.build_reply("list", BASE)[0]["type"] == "flex"
    detail = replies.build_reply("detail", BASE, card_id=7)
    assert "守護の翼" in detail[0]["altText"]


# ---- 波動の音 ----


@pytest.mark.parametrize("word", ["波動の音", "波動", "サウンド"])
def test_sound_word_opens_sound_menu(word):
    assert replies.detect_command(word) == ("sound", None)
    (msg,) = replies.build_reply("sound", BASE)
    button = msg["contents"]["footer"]["contents"][0]["action"]
    assert button == {"type": "uri", "label": "🎵 波動の音を聴く", "uri": f"{BASE}/sound/"}
    assert len(msg["quickReply"]["items"]) <= 13


def test_sound_page_is_served_with_lumiel_name():
    from main import app

    client = TestClient(app)
    r = client.get("/sound/")
    assert r.status_code == 200 and "ルミエル 波動の音" in r.text and "愛美" not in r.text
    for path in ("/sound/sw.js", "/sound/manifest.json", "/sound/icon.png"):
        assert client.get(path).status_code == 200
