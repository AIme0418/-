"""ワンオラクルの演出ページ（/oracle/）と、そのボタンのテスト。"""

from fastapi.testclient import TestClient

from app import rate_limit
from app.oracle import deck, replies
from main import app

BASE = "https://example.onrender.com"
client = TestClient(app)


def setup_function():
    rate_limit._ip_requests.clear()


def test_page_is_served():
    r = client.get("/oracle/")
    assert r.status_code == 200
    assert "ワンオラクル" in r.text and "/api/oracle/draw" in r.text


def test_page_assets_exist():
    assert client.get("/static/ui/goddess.jpg").status_code == 200
    assert client.get("/static/ui/oracle_back.jpg").status_code == 200


def test_draw_returns_a_real_card_with_image():
    r = client.post("/api/oracle/draw")
    assert r.status_code == 200
    c = r.json()
    card = deck.get_card(c["id"])
    assert card and c["name"] == card["name"] and c["message"] == card["message"]
    assert set(c) >= {"keyword", "love", "work", "healing", "image"}
    if c["image"]:
        assert client.get(c["image"]).status_code == 200


def test_draw_is_random_across_calls():
    ids = {client.post("/api/oracle/draw").json()["id"] for _ in range(8)}
    assert len(ids) > 1


def test_draw_is_rate_limited_per_ip():
    codes = [client.post("/api/oracle/draw").status_code for _ in range(rate_limit.PER_IP_MAX_REQUESTS + 1)]
    assert codes[-1] == 429


def test_draw_rejects_get():
    assert client.get("/api/oracle/draw").status_code == 405


def test_one_oracle_has_goddess_button_after_open_button():
    intro = replies.build_reply("one", BASE, user_id="U1")
    buttons = intro[1]["contents"]["footer"]["contents"]
    assert buttons[0]["action"]["type"] == "postback"  # 今までの「カードを開く」が先頭のまま
    assert buttons[1]["action"] == {"type": "uri", "label": "🌟 女神様に選んでもらう", "uri": f"{BASE}/oracle/"}
    assert len(buttons[1]["action"]["label"]) <= 20  # LINEのボタン文字数上限


def test_other_menus_do_not_get_goddess_button():
    for kind in ["three", "love", "work", "healing"]:
        intro = replies.build_reply(kind, BASE, user_id="U1")
        actions = [b.get("action", {}).get("type") for b in intro[1]["contents"]["footer"]["contents"] if b.get("type") == "button"]
        assert "uri" not in actions


def test_no_goddess_button_without_https_url():
    intro = replies.build_reply("one", "", user_id="U1")
    actions = [b["action"]["type"] for b in intro[1]["contents"]["footer"]["contents"] if b.get("type") == "button"]
    assert actions == ["postback"]
