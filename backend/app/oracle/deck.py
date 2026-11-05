"""オラクルカード44枚の読み込みと抽選。

カードの文章は cards.json、画像は backend/static/cards/ に置く。
画像がまだないカードは、画像なしの装飾デザインで表示される。
"""

import json
import secrets
from functools import lru_cache
from pathlib import Path

CARDS_FILE = Path(__file__).resolve().parent / "cards.json"
CARD_IMAGE_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "cards"
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")

# 偏りのない乱数（OSの暗号用乱数）で抽選する
_rng = secrets.SystemRandom()


@lru_cache(maxsize=1)
def load_cards() -> tuple[dict, ...]:
    data = json.loads(CARDS_FILE.read_text(encoding="utf-8"))
    return tuple(data["cards"])


def get_card(card_id: int) -> dict | None:
    return next((c for c in load_cards() if c["id"] == card_id), None)


def draw(count: int = 1) -> list[dict]:
    """重複なしでcount枚引く。"""
    return _rng.sample(list(load_cards()), count)


def draw_excluding(exclude: set[int]) -> dict:
    """すでに出たカードを除いて1枚引く（スリーオラクルで重複させないため）。"""
    return _rng.choice([c for c in load_cards() if c["id"] not in exclude])


def card_image_filename(card_id: int) -> str | None:
    """画像ファイルが登録されていればファイル名（例: 07.jpg）を返す。"""
    for ext in IMAGE_EXTENSIONS:
        name = f"{card_id:02d}{ext}"
        if (CARD_IMAGE_DIR / name).is_file():
            return name
    return None


def card_image_url(card_id: int, public_base_url: str) -> str | None:
    """LINEで表示できる画像URL（https必須）。画像未登録・URL未設定ならNone。"""
    if not public_base_url.startswith("https://"):
        return None
    name = card_image_filename(card_id)
    if not name:
        return None
    return f"{public_base_url.rstrip('/')}/static/cards/{name}"


def pick_closing(options: list[str]) -> str:
    return _rng.choice(options)


def ui_asset_url(filename: str, public_base_url: str) -> str | None:
    """背景・ロゴなどの装飾画像のURL（https必須）。"""
    if not public_base_url.startswith("https://"):
        return None
    return f"{public_base_url.rstrip('/')}/static/ui/{filename}"
