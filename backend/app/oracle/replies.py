"""リッチメニューのボタンから届く言葉を判定し、LINEに送るメッセージを組み立てる。

AIは使わないので、何回引いてもAPI料金はかからない。
LINEの返信は1回につき最大5通。ここでは常に1〜2通に収めている。
"""

import re
import unicodedata

from . import deck

# リッチメニューのボタンが送る言葉（＋よくある言い換え）
COMMANDS = {
    "one": {"ワンオラクル", "1枚引き", "一枚引き"},
    "three": {"スリーオラクル", "3枚引き", "三枚引き"},
    "love": {"恋愛", "恋愛・人間関係", "人間関係"},
    "work": {"金運", "仕事・金運", "仕事運"},
    "healing": {"癒し", "心の癒し"},
    "list": {"カード一覧", "一覧"},
}

CARD_DETAIL_PATTERN = re.compile(r"^(?:カード|No\.?|NO\.?|no\.?)(\d{1,2})$")

THEMES = {
    "love": {"label": "恋愛・人間関係", "field": "love", "icon": "💗"},
    "work": {"label": "仕事・金運", "field": "work", "icon": "💰"},
    "healing": {"label": "心の癒し", "field": "healing", "icon": "🕊"},
}

# 色（ラベンダー・ピンク・ゴールド）
LAVENDER_BG = "#F7F1FC"
DEEP_PURPLE = "#4B3A63"
GOLD = "#B08A2E"
PINK = "#D9739B"
SOFT_TEXT = "#5E5470"

QUICK_REPLY = {
    "items": [
        {"type": "action", "action": {"type": "message", "label": label, "text": text}}
        for label, text in [
            ("✦ ワンオラクル", "ワンオラクル"),
            ("✦ スリーオラクル", "スリーオラクル"),
            ("💗 恋愛", "恋愛"),
            ("💰 金運", "金運"),
            ("🕊 癒し", "癒し"),
            ("📖 カード一覧", "カード一覧"),
        ]
    ]
}

THREE_CLOSINGS = [
    "どの1枚も、今のあなたに必要だから現れたカードです。心に残った言葉を、今日のお守りにしてくださいね。",
    "過去から未来へ、光はひとつの道としてつながっています。あなたのペースで、安心して進んでください。",
    "天使と女神たちは、いつもあなたのそばで見守っています。気になったカードの言葉を、ゆっくり味わってみてください。",
]


def normalize(text: str) -> str:
    """全角・半角やスペースの違いをならして比較しやすくする。"""
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", "", text)


def detect_command(user_text: str) -> tuple[str, int | None] | None:
    """オラクルの言葉なら (種類, カード番号) を返す。それ以外はNone（AIとの会話に回す）。"""
    text = normalize(user_text)
    for kind, words in COMMANDS.items():
        if text in {normalize(w) for w in words}:
            return kind, None
    m = CARD_DETAIL_PATTERN.match(text)
    if m:
        return "detail", int(m.group(1))
    return None


def build_reply(kind: str, public_base_url: str, card_id: int | None = None) -> list[dict]:
    if kind == "one":
        messages = [_one_oracle(deck.draw(1)[0], public_base_url)]
    elif kind == "three":
        messages = [_three_oracle(deck.draw(3), public_base_url)]
    elif kind in THEMES:
        messages = [_theme_oracle(deck.draw(1)[0], kind, public_base_url)]
    elif kind == "list":
        messages = [_card_list(public_base_url)]
    elif kind == "detail":
        card = deck.get_card(card_id) if card_id else None
        if card:
            messages = [_one_oracle(card, public_base_url, label=f"No.{card['id']:02d} のカード")]
        else:
            messages = [{"type": "text", "text": "カードは1〜44番まであります。「カード7」のように送ってくださいね。"}]
    else:
        raise ValueError(f"unknown oracle command: {kind}")

    messages[-1]["quickReply"] = QUICK_REPLY
    return messages


# ---- 各メニューの返信 ----


def _one_oracle(card: dict, base_url: str, label: str = "ワンオラクル") -> dict:
    bubble = _card_bubble(card, base_url, label=label, main_text=card["message"])
    return _flex(f"{label}｜{card['name']}「{card['keyword']}」", bubble)


def _theme_oracle(card: dict, kind: str, base_url: str) -> dict:
    theme = THEMES[kind]
    bubble = _card_bubble(
        card,
        base_url,
        label=f"{theme['icon']} {theme['label']}",
        main_text=card[theme["field"]],
        sub_text=card["message"],
    )
    return _flex(f"{theme['label']}｜{card['name']}「{card['keyword']}」", bubble)


def _three_oracle(cards: list[dict], base_url: str) -> dict:
    positions = ["過去", "現在", "未来"]
    bubbles = [
        _card_bubble(card, base_url, label=f"{pos}のカード", main_text=card["message"])
        for pos, card in zip(positions, cards)
    ]
    bubbles.append(_summary_bubble(cards))
    alt = "スリーオラクル｜" + "／".join(
        f"{pos}:{c['name']}" for pos, c in zip(positions, cards)
    )
    return {"type": "flex", "altText": alt[:400], "contents": {"type": "carousel", "contents": bubbles}}


def three_summary_text(cards: list[dict]) -> str:
    past, present, future = cards
    return (
        f"過去の「{past['keyword']}」は、今のあなたをつくってきた大切な土台です。\n\n"
        f"現在は「{present['keyword']}」がテーマ。{present['name']}が、今のあなたにそっと寄り添っています。\n\n"
        f"そして未来には「{future['keyword']}」の光が待っています。\n\n"
        + deck.pick_closing(THREE_CLOSINGS)
    )


def _summary_bubble(cards: list[dict]) -> dict:
    return {
        "type": "bubble",
        "size": "mega",
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "paddingAll": "20px",
            "background": _gradient(),
            "contents": [
                _text("✦ 3枚からの総合メッセージ ✦", size="sm", color=GOLD, weight="bold", align="center"),
                _text(
                    "　→　".join(c["keyword"] for c in cards),
                    size="sm",
                    color=PINK,
                    weight="bold",
                    align="center",
                ),
                {"type": "separator", "color": GOLD, "margin": "md"},
                _text(three_summary_text(cards), size="sm", color=DEEP_PURPLE, margin="md"),
            ],
        },
    }


def _card_list(base_url: str) -> dict:
    hint = "「カード7」のように番号を送ると、そのカードの詳しいメッセージが見られます。"
    if base_url.startswith("https://"):
        bubble = {
            "type": "bubble",
            "size": "mega",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "paddingAll": "20px",
                "background": _gradient(),
                "contents": [
                    _text("✦ カード一覧 ✦", size="lg", color=DEEP_PURPLE, weight="bold", align="center"),
                    _text("光の女神と天使たち 全44枚", size="sm", color=GOLD, align="center"),
                    _text(hint, size="xs", color=SOFT_TEXT, margin="lg"),
                ],
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#A98BC9",
                        "action": {
                            "type": "uri",
                            "label": "44枚のカードを見る",
                            "uri": f"{base_url.rstrip('/')}/cards",
                        },
                    }
                ],
            },
        }
        return _flex("カード一覧（全44枚）", bubble)

    # 公開URLが未設定の間は文字の一覧で代用
    lines = [f"{c['id']:02d}. {c['name']}" for c in deck.load_cards()]
    return {"type": "text", "text": "✦ カード一覧（全44枚）✦\n\n" + "\n".join(lines) + "\n\n" + hint}


# ---- 部品 ----


def _card_bubble(card: dict, base_url: str, label: str, main_text: str, sub_text: str | None = None) -> dict:
    body_contents = [
        _text(f"✦ {label} ✦", size="xs", color=GOLD, weight="bold", align="center"),
        _text(card["name"], size="lg", color=DEEP_PURPLE, weight="bold", align="center", margin="sm"),
        _text(f"「{card['keyword']}」", size="md", color=PINK, weight="bold", align="center"),
        {"type": "separator", "color": GOLD, "margin": "lg"},
        _text(main_text, size="sm", color=DEEP_PURPLE, margin="lg"),
    ]
    if sub_text:
        body_contents += [
            _text("― カードの基本メッセージ ―", size="xxs", color=GOLD, align="center", margin="xl"),
            _text(sub_text, size="xs", color=SOFT_TEXT, margin="sm"),
        ]

    bubble = {
        "type": "bubble",
        "size": "mega",
        "hero": _hero(card, base_url),
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "20px",
            "backgroundColor": LAVENDER_BG,
            "contents": body_contents,
        },
    }
    return bubble


def _hero(card: dict, base_url: str) -> dict:
    url = deck.card_image_url(card["id"], base_url)
    if url:
        return {"type": "image", "url": url, "size": "full", "aspectRatio": "2:3", "aspectMode": "cover"}
    # 画像がまだないカード用の装飾デザイン
    return {
        "type": "box",
        "layout": "vertical",
        "height": "220px",
        "justifyContent": "center",
        "background": _gradient(),
        "contents": [
            _text("✧ ✦ ✧", size="lg", color=GOLD, align="center"),
            _text(f"No.{card['id']:02d}", size="sm", color=GOLD, weight="bold", align="center", margin="md"),
            _text(card["name"], size="md", color=DEEP_PURPLE, weight="bold", align="center", margin="sm"),
            _text("✧ ✦ ✧", size="lg", color=GOLD, align="center", margin="md"),
        ],
    }


def _gradient() -> dict:
    return {
        "type": "linearGradient",
        "angle": "135deg",
        "startColor": "#E8D9F7",
        "centerColor": "#FFF6E0",
        "endColor": "#FADCE8",
    }


def _text(text: str, size: str = "sm", color: str = DEEP_PURPLE, **extra) -> dict:
    return {"type": "text", "text": text, "size": size, "color": color, "wrap": True, **extra}


def _flex(alt_text: str, contents: dict) -> dict:
    return {"type": "flex", "altText": alt_text[:400], "contents": contents}
