"""リッチメニューのボタンから届く言葉を判定し、LINEに送るメッセージを組み立てる。

AIは使わないので、何回引いてもAPI料金はかからない。
LINEの返信は1回につき最大5通。ここでは常に1〜2通に収めている。
"""

import re
import unicodedata

from . import deck, sessions

# リッチメニューのボタンが送る言葉（＋よくある言い換え）
COMMANDS = {
    "one": {"ワンオラクル", "1枚引き", "一枚引き"},
    "three": {"スリーオラクル", "3枚引き", "三枚引き"},
    "love": {"恋愛", "恋愛・人間関係", "人間関係"},
    "work": {"金運", "仕事・金運", "仕事運"},
    "healing": {"癒し", "心の癒し"},
    "list": {"カード一覧", "一覧"},
    "sound": {"波動の音", "波動", "サウンド", "ヒーリング音", "周波数"},
}

CARD_DETAIL_PATTERN = re.compile(r"^(?:カード|No\.?|NO\.?|no\.?)(\d{1,2})$")

THEMES = {
    "love": {"label": "恋愛・人間関係", "field": "love", "icon": "💗"},
    "work": {"label": "仕事・金運", "field": "work", "icon": "💰"},
    "healing": {"label": "心の癒し", "field": "healing", "icon": "🕊"},
}

# 色（リッチメニュー・ロゴに合わせた、紫・ラベンダー・ピンク・ゴールド）
DEEP_PURPLE = "#5A2D86"
GOLD = "#A9791C"
GOLD_LIGHT = "#E2C06A"
PINK = "#C4508F"
SOFT_TEXT = "#5E4A78"
FRAME_WHITE = "#FFFFFFD9"

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
            ("🎵 波動の音", "波動の音"),
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


def build_reply(kind: str, public_base_url: str, card_id: int | None = None, user_id: str = "") -> list[dict]:
    if kind in REVEAL_KINDS:
        # カード裏面を見せて、ボタンを押してもらう（結果はボタンを押した瞬間に決まる）
        return _intro(kind, user_id, public_base_url)
    elif kind == "list":
        messages = [_card_list(public_base_url)]
    elif kind == "sound":
        messages = [_sound_menu(public_base_url)]
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


# ---- カードを開く演出（裏面 → カードを開く → 結果） ----
# ワンオラクル・スリーオラクル・恋愛・金運・癒しで共通。
# カードはボタンを押した瞬間に決まり、同じボタンからは1回しか結果が出ない。

ONE_INTRO_TEXT = (
    "✨ 天使と女神たちが、あなたへのメッセージを準備しています。\n\n"
    "ゆっくり深呼吸して、今のあなたの心に意識を向けてみてください。🌙"
)
THREE_INTRO_TEXT = (
    "🔮 スリーオラクルは、「過去・背景」「現在」「未来」の3枚を順番に開いて、"
    "これまでの流れから、これからのヒントを読み解く占い方です。\n\n"
    "✨ 天使と女神たちが、あなたのための3枚のカードを準備しています。\n"
    "ゆっくり深呼吸して、今のあなたの心に意識を向けてみてください。🌙\n"
    "1枚ずつ、順番に開いていきましょう。"
)
THEME_INTRO_TEXT = (
    "{icon} {label}について、天使と女神たちがあなたへのメッセージを準備しています。\n\n"
    "ゆっくり深呼吸して、思い浮かぶ人や出来事に、そっと意識を向けてみてください。🌙"
    "{note}"
)
THEME_NOTES = {
    "love": "\n恋人や好きな人のことだけでなく、家族・友人・職場の人との関係について思い浮かべても大丈夫です。",
}
REVEAL_TEXT = "✨ あなたに届いた光のメッセージは……"
EXPIRED_TEXT = (
    "🌙 このカードは時間がたって、そっと閉じてしまいました。\n"
    "もう一度引くときは、下のボタンからどうぞ。"
)
ALREADY_TEXT = "✨ このカードは、もう開かれています。\n新しく引くときは「🔮 もう一度引く」を押してくださいね。"
# 開いた直後の連打には返事をしない（これより後に押されたら、やさしく案内する）
DOUBLE_TAP_SILENCE_SECONDS = 20

# スリーオラクルの3枚の位置
THREE_POSITIONS = ["過去・背景", "現在の状況", "未来へのヒント"]
THREE_STEP_NAMES = ["1枚目", "2枚目", "3枚目"]

# 「もう一度引く」で送る言葉（リッチメニューと同じ言葉）
AGAIN_WORD = {"one": "ワンオラクル", "three": "スリーオラクル", "love": "恋愛", "work": "金運", "healing": "癒し"}
REVEAL_KINDS = set(AGAIN_WORD)


GODDESS_INTRO_TEXT = (
    "🔮 ワンオラクルは、今のあなたに必要なメッセージを1枚のカードで受け取る占い方です。\n\n"
    "✨ 天使と女神たちが、あなたへのメッセージを準備しています。\n"
    "ゆっくり深呼吸して、今のあなたの心に意識を向けてみてください。🌙\n"
    "下のボタンを押すと、女神様があなたのカードを選んでくれます。"
)


def _intro(kind: str, user_id: str, base_url: str) -> list[dict]:
    if kind == "one" and base_url.startswith("https://"):
        # ワンオラクルは女神様の演出ページで引く（チャットで開く方法と2つあると迷うため1つに）
        return [{"type": "text", "text": GODDESS_INTRO_TEXT}, _goddess_message(base_url)]
    return _back_intro(kind, user_id, base_url)


GODDESS_RESULT_RE = re.compile(r"女神様が選んだカード\s*No\.?\s*(\d{1,2})")


def goddess_result_reply(text: str, base_url: str) -> list[dict] | None:
    """演出ページの「LINEで結果を受け取る」から送られたメッセージに、カードの結果を返す。"""
    m = GODDESS_RESULT_RE.search(text or "")
    if not m:
        return None
    card = deck.get_card(int(m.group(1)))
    if not card:
        return None
    bubble = _card_bubble(card, base_url, label="ワンオラクル", main_text=card["message"])
    bubble["footer"] = _again_buttons("one", base_url)
    return [
        {"type": "text", "text": "✨ 女神様があなたのために選んだカードは……"},
        _flex(f"ワンオラクル｜{card['name']}「{card['keyword']}」", bubble),
    ]


def _goddess_message(base_url: str) -> dict:
    url = f"{base_url.rstrip('/')}/oracle/"
    # 横長の画像（女神様の全身＋左右はぼかした背景）。リッチメニューが開いていても1画面に収まる高さにする
    goddess = deck.ui_asset_url("goddess_wide.jpg", base_url)
    bubble = {
        "type": "bubble",
        "size": "giga",
        "hero": {
            "type": "image",
            "url": goddess,
            "size": "full",
            "aspectRatio": "4:3",
            "aspectMode": "cover",
            "action": {"type": "uri", "label": "女神様に選んでもらう", "uri": url},
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "10px",
            "background": _gradient(),
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "color": "#8E5BC4",
                    "height": "sm",
                    "action": {"type": "uri", "label": "🌟 女神様に選んでもらう", "uri": url},
                }
            ],
        },
    }
    return _flex("✨ ワンオラクル｜女神様があなたのカードを選びます", bubble)


def _back_intro(kind: str, user_id: str, base_url: str) -> list[dict]:
    """カード裏面＋「カードを開く」で、チャットの中で引く方法。"""
    if kind == "three":
        text = THREE_INTRO_TEXT
    elif kind in THEMES:
        text = THEME_INTRO_TEXT.format(note=THEME_NOTES.get(kind, ""), **THEMES[kind])
    else:
        text = ONE_INTRO_TEXT
    data = sessions.create(user_id, kind)
    return [{"type": "text", "text": text}, _back_message(kind, data, base_url, step=1)]


def _back_message(kind: str, data: str, base_url: str, step: int) -> dict:
    """カード裏面＋「カードを開く」ボタン。"""
    if kind == "three":
        caption = f"✦ {THREE_STEP_NAMES[step - 1]}：{THREE_POSITIONS[step - 1]} ✦"
        label = f"✨ {THREE_STEP_NAMES[step - 1]}を開く"
    elif kind in THEMES:
        caption = f"{THEMES[kind]['icon']} {THEMES[kind]['label']}"
        label = "✨ カードを開く"
    else:
        caption = None
        label = "✨ カードを開く"

    # 横長の画像（カード全体＋左右はぼかした背景）。リッチメニューが開いていても1画面に収まる
    back = deck.ui_asset_url("oracle_back_wide.jpg", base_url)
    if back:
        hero = {"type": "image", "url": back, "size": "full", "aspectRatio": "4:3", "aspectMode": "cover"}
    else:
        hero = {
            "type": "box",
            "layout": "vertical",
            "height": "220px",
            "justifyContent": "center",
            "background": _gradient(),
            "contents": [_text("✧ ✦ ✧", size="xl", color=GOLD, align="center")],
        }
    footer_contents = []
    if caption:
        footer_contents.append(_text(caption, size="sm", color=GOLD, weight="bold", align="center"))
    footer_contents.append(
        {
            "type": "button",
            "style": "primary",
            "color": "#8E5BC4",
            "height": "sm",
            "action": {
                "type": "postback",
                "label": label,
                "data": data,
                "displayText": label,
                "inputOption": "closeRichMenu",
            },
        }
    )
    bubble = {
        "type": "bubble",
        "size": "giga",
        "hero": hero,
        "footer": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "paddingAll": "10px",
            "background": _gradient(),
            "contents": footer_contents,
        },
    }
    return _flex(f"✨ カードが届きました。「{label.replace('✨ ', '')}」を押してください", bubble)


def _again_buttons(kind: str, base_url: str = "") -> dict:
    row = {
        "type": "box",
        "layout": "horizontal",
        "spacing": "sm",
        "contents": [
            {
                "type": "button",
                "style": "primary",
                "color": "#8E5BC4",
                "height": "sm",
                "action": {"type": "message", "label": "🔮 もう一度引く", "text": AGAIN_WORD[kind]},
            },
            {
                "type": "button",
                "style": "secondary",
                "height": "sm",
                "action": {
                    "type": "postback",
                    "label": "💜 メニューに戻る",
                    "data": "oracle=menu",
                    "inputOption": "openRichMenu",
                },
            },
        ],
    }
    box = {
        "type": "box",
        "layout": "vertical",
        "spacing": "xs",
        "paddingAll": "10px",
        "backgroundColor": "#F9E1EF",
        "contents": [row],
    }
    sound = sound_url(base_url)
    if sound:
        box["contents"].append(
            {
                "type": "button",
                "style": "link",
                "height": "sm",
                "color": "#8E5BC4",
                "action": {"type": "uri", "label": "🎵 波動の音でひと休み", "uri": sound},
            }
        )
    return box


def footer_buttons(footer: dict) -> list[dict]:
    """フッターの中のボタンを、横並びの行も含めて順番に取り出す。"""
    out = []
    for c in footer.get("contents", []):
        if c.get("type") == "button":
            out.append(c)
        elif c.get("type") == "box":
            out += footer_buttons(c)
    return out


def sound_url(base_url: str) -> str | None:
    if not base_url.startswith("https://"):
        return None
    return f"{base_url.rstrip('/')}/sound/"


SOUND_TEXT = (
    "周波数の音や、雨音・波の音で、心と体がゆるむ時間をつくるページです。\n"
    "5つの質問に答えると、今のあなたに合う音を選びます。"
)
SOUND_NOTE = "※リラックスのための音で、病気の診断や治療を目的としたものではありません。イヤホンで、小さめの音量からどうぞ。"


def _sound_menu(base_url: str) -> dict:
    url = sound_url(base_url)
    if not url:
        return {"type": "text", "text": "🎵 波動の音は、ただいま準備中です。もう少しお待ちくださいね。"}
    bubble = {
        "type": "bubble",
        "size": "mega",
        "hero": _emblem_hero(base_url),
        "body": _body(
            [
                _text("🎵 波動の音 🎵", size="lg", color=DEEP_PURPLE, weight="bold", align="center"),
                _text("174Hz〜963Hzの周波数・自然の音", size="xs", color=GOLD, align="center", margin="sm"),
                _ornament(),
                _text(SOUND_TEXT, size="sm", color=DEEP_PURPLE, margin="md"),
                _text(SOUND_NOTE, size="xxs", color=SOFT_TEXT, margin="lg"),
            ]
        ),
        "footer": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#F9E1EF",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "color": "#8E5BC4",
                    "action": {"type": "uri", "label": "🎵 波動の音を聴く", "uri": url},
                }
            ],
        },
    }
    return _flex("🎵 波動の音｜周波数の音でリラックス", bubble)


def _one_reveal(card: dict, base_url: str) -> list[dict]:
    bubble = _card_bubble(card, base_url, label="ワンオラクル", main_text=card["message"])
    bubble["footer"] = _again_buttons("one", base_url)
    return [
        {"type": "text", "text": REVEAL_TEXT},
        _flex(f"ワンオラクル｜{card['name']}「{card['keyword']}」", bubble),
    ]


def _theme_reveal(card: dict, kind: str, base_url: str) -> list[dict]:
    msg = _theme_oracle(card, kind, base_url)
    msg["contents"]["footer"] = _again_buttons(kind, base_url)
    return [{"type": "text", "text": REVEAL_TEXT}, msg]


def _three_reveal(card_ids: list[int], sid: str, base_url: str) -> list[dict]:
    """スリーオラクルのstep枚目を開いたときの返信。結果が1画面に収まるようにする。"""
    step = len(card_ids)
    card = deck.get_card(card_ids[-1])
    pos = THREE_POSITIONS[step - 1]
    bubble = _card_bubble(card, base_url, label=f"{THREE_STEP_NAMES[step - 1]}：{pos}", main_text=three_position_text(step, card))
    text = {"type": "text", "text": f"✨ {THREE_STEP_NAMES[step - 1]}「{pos}」のカードは……"}
    if step < 3:
        data = sessions.next_step_data(sid, "three", step + 1, card_ids)
        label = f"✨ {THREE_STEP_NAMES[step]}を開く"
        bubble["footer"] = {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "10px",
            "backgroundColor": "#F9E1EF",
            "contents": [
                _text(f"次は {THREE_STEP_NAMES[step]}「{THREE_POSITIONS[step]}」", size="xs", color=GOLD, align="center"),
                {
                    "type": "button",
                    "style": "primary",
                    "color": "#8E5BC4",
                    "height": "sm",
                    "margin": "sm",
                    "action": {"type": "postback", "label": label, "data": data, "displayText": label,
                               "inputOption": "closeRichMenu"},
                },
            ],
        }
        return [text, _flex(f"{pos}｜{card['name']}「{card['keyword']}」", bubble)]

    bubble["footer"] = {
        "type": "box",
        "layout": "vertical",
        "paddingAll": "10px",
        "backgroundColor": "#F9E1EF",
        "contents": [_text("👉 右にスライドすると、3枚の総合メッセージ", size="xs", color=GOLD, align="center")],
    }
    cards = [deck.get_card(i) for i in card_ids]
    summary = _summary_bubble(cards, base_url)
    summary["size"] = "giga"
    # 横に並ぶカードと高さがそろうので、ロゴは外して1画面に収める
    summary.pop("hero", None)
    summary["body"]["paddingAll"] = "16px"
    summary["footer"] = _again_buttons("three", base_url)
    return [
        text,
        {
            "type": "flex",
            "altText": "✦ 3枚からの総合メッセージ ✦",
            "contents": {"type": "carousel", "contents": [bubble, summary]},
        },
    ]


def build_postback_reply(user_id: str, data: str, base_url: str) -> list[dict] | None:
    """ボタン（postback）が押されたときの返信。返信しないときはNone。"""
    params = sessions.parse(data)
    action = params.get("oracle")
    if action == "menu":
        return None  # リッチメニューが開くだけ。メッセージは送らない
    kind = params.get("kind", "")
    if action != "open" or kind not in REVEAL_KINDS:
        return None

    sid = params.get("sid", "")
    try:
        issued_at = int(params.get("ts", "0"))
        step = int(params.get("step", "1"))
        prior = [int(x) for x in params.get("prior", "").split(",") if x]
    except ValueError:
        return [{"type": "text", "text": EXPIRED_TEXT, "quickReply": _again_quick_reply(kind)}]
    max_step = 3 if kind == "three" else 1
    if not 1 <= step <= max_step or len(prior) != step - 1:
        return [{"type": "text", "text": EXPIRED_TEXT, "quickReply": _again_quick_reply(kind)}]

    def draw(exclude: set[int]) -> int:
        return deck.draw_excluding(exclude)["id"]

    status, card_ids = sessions.open_card(user_id, sid, kind, issued_at, draw, step=step, prior=prior)
    if status == "new":
        if kind == "three":
            return _three_reveal(card_ids, sid, base_url)
        card = deck.get_card(card_ids[-1])
        if kind in THEMES:
            return _theme_reveal(card, kind, base_url)
        return _one_reveal(card, base_url)
    if status == "already":
        ago = sessions.opened_seconds_ago(sid)
        if ago is not None and ago < DOUBLE_TAP_SILENCE_SECONDS:
            return None
        return [{"type": "text", "text": ALREADY_TEXT, "quickReply": _again_quick_reply(kind)}]
    return [{"type": "text", "text": EXPIRED_TEXT, "quickReply": _again_quick_reply(kind)}]


def _again_quick_reply(kind: str = "one") -> dict:
    word = AGAIN_WORD.get(kind, "ワンオラクル")
    return {"items": [{"type": "action", "action": {"type": "message", "label": "🔮 もう一度引く", "text": word}}]}


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
    positions = THREE_POSITIONS
    bubbles = [
        _card_bubble(card, base_url, label=f"{pos}のカード", main_text=card["message"])
        for pos, card in zip(positions, cards)
    ]
    bubbles.append(_summary_bubble(cards, base_url))
    alt = "スリーオラクル｜" + "／".join(
        f"{pos}:{c['name']}" for pos, c in zip(positions, cards)
    )
    return {"type": "flex", "altText": alt[:400], "contents": {"type": "carousel", "contents": bubbles}}


THREE_POSITION_LEADS = (
    "これまでのあなたが通ってきた道を表すカードです。\n"
    "思うようにいかない時期や、がまんを重ねてきた時期もあったかもしれません。"
    "その中で、あなたの中には「{keyword}」のテーマが育ってきました。",
    "今のあなたが向き合っているテーマを表すカードです。\n"
    "今は「{keyword}」が大切な鍵になっています。",
    "これからの流れと、未来へのヒントを表すカードです。\n"
    "この先、「{keyword}」の流れが少しずつ近づいてきています。",
)


def three_position_text(step: int, card: dict) -> str:
    """スリーオラクルのstep枚目（1〜3）の読み方。位置の意味を先に添えてから、カードのメッセージを伝える。"""
    lead = THREE_POSITION_LEADS[step - 1].format(keyword=card["keyword"])
    return f"{lead}\n\n― カードからのメッセージ ―\n{card['message']}"


def three_summary_text(cards: list[dict]) -> str:
    past, present, future = cards
    return (
        f"これまでのあなたは、「{past['keyword']}」と向き合いながら歩んできました。"
        "つらいと感じた日々も、今のあなたをつくる大切な土台になっています。\n\n"
        f"その経験があったからこそ、今は「{present['keyword']}」がテーマになっています。"
        f"{present['name']}が、今のあなたにそっと寄り添っています。\n\n"
        f"そして、その先に待っているのは「{future['keyword']}」の流れです。"
        "過去から今へとつながってきた歩みが、これからの道を照らしてくれます。\n\n"
        + deck.pick_closing(THREE_CLOSINGS)
    )


def _summary_bubble(cards: list[dict], base_url: str) -> dict:
    bubble = {
        "type": "bubble",
        "size": "mega",
        "body": _body(
            [
                _text("✦ 3枚からの総合メッセージ ✦", size="sm", color=GOLD, weight="bold", align="center"),
                _text("　→　".join(c["keyword"] for c in cards), size="sm", color=PINK, weight="bold", align="center", margin="md"),
                _ornament(),
                _text(three_summary_text(cards), size="sm", color=DEEP_PURPLE, margin="md"),
            ]
        ),
    }
    hero = _emblem_hero(base_url)
    if hero:
        bubble["hero"] = hero
    return bubble


def _emblem_hero(base_url: str) -> dict | None:
    emblem = deck.ui_asset_url("emblem.png", base_url)
    if not emblem:
        return None
    return {
        "type": "box",
        "layout": "vertical",
        "paddingAll": "16px",
        "background": _gradient(),
        "contents": [{"type": "image", "url": emblem, "size": "lg", "aspectRatio": "1:1", "aspectMode": "fit"}],
    }


def _card_list(base_url: str) -> dict:
    hint = "「カード7」のように番号を送ると、そのカードの詳しいメッセージが見られます。"
    if base_url.startswith("https://"):
        bubble = {
            "type": "bubble",
            "size": "mega",
            "hero": _emblem_hero(base_url),
            "body": _body(
                [
                    _text("✦ カード一覧 ✦", size="lg", color=DEEP_PURPLE, weight="bold", align="center"),
                    _text("光の女神と天使たち　全44枚", size="sm", color=GOLD, align="center"),
                    _ornament(),
                    _text(hint, size="xs", color=SOFT_TEXT, margin="md"),
                ]
            ),
            "footer": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#F9E1EF",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#8E5BC4",
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
    """カードの結果。絵と文章が1画面に収まるよう、絵は左に小さめ、名前は右に置く。"""
    head = {
        "type": "box",
        "layout": "horizontal",
        "spacing": "lg",
        "contents": [
            _card_thumb(card, base_url),
            {
                "type": "box",
                "layout": "vertical",
                "flex": 6,
                "justifyContent": "center",
                "spacing": "sm",
                "contents": [
                    _text(f"✦ {label} ✦", size="xs", color=GOLD, weight="bold"),
                    _text(f"No.{card['id']:02d}", size="xxs", color=GOLD),
                    _text(card["name"], size="md", color=DEEP_PURPLE, weight="bold"),
                    _text(f"「{card['keyword']}」", size="sm", color=PINK, weight="bold"),
                ],
            },
        ],
    }
    body_contents = [head, _ornament(), _text(main_text, size="sm", color=DEEP_PURPLE, margin="md")]
    if card.get("angel_word"):
        body_contents += [
            _text("― 天使からのひとこと ―", size="xxs", color=GOLD, align="center", margin="lg"),
            _text(card["angel_word"], size="sm", color=PINK, weight="bold", align="center", margin="sm"),
        ]
    if sub_text:
        body_contents += [
            _text("― カードの基本メッセージ ―", size="xxs", color=GOLD, align="center", margin="lg"),
            _text(sub_text, size="xs", color=SOFT_TEXT, margin="sm"),
        ]
    body = _body(body_contents)
    body["paddingAll"] = "16px"
    return {"type": "bubble", "size": "giga", "body": body}


def _card_thumb(card: dict, base_url: str) -> dict:
    """結果の左側に置くカードの絵（縦2:横3の比率のまま小さめに）。"""
    url = deck.card_image_url(card["id"], base_url) or deck.ui_asset_url("card_back.jpg", base_url)
    if url:
        return {
            "type": "box",
            "layout": "vertical",
            "flex": 5,
            "cornerRadius": "10px",
            "borderWidth": "2px",
            "borderColor": GOLD_LIGHT,
            "contents": [{"type": "image", "url": url, "size": "full", "aspectRatio": "2:3", "aspectMode": "cover"}],
        }
    return {
        "type": "box",
        "layout": "vertical",
        "flex": 5,
        "height": "150px",
        "justifyContent": "center",
        "cornerRadius": "10px",
        "background": _gradient(),
        "contents": [_text("✧ ✦ ✧", size="md", color=GOLD, align="center")],
    }


def _hero(card: dict, base_url: str) -> dict:
    url = deck.card_image_url(card["id"], base_url)
    if url:
        return {"type": "image", "url": url, "size": "full", "aspectRatio": "2:3", "aspectMode": "cover"}

    back = deck.ui_asset_url("card_back.jpg", base_url)
    if not back:
        return _gradient_hero(card)

    # 画像がまだないカードは、天空の背景＋金の枠＋カード名で表示する
    return {
        "type": "box",
        "layout": "vertical",
        "paddingAll": "0px",
        "contents": [
            {"type": "image", "url": back, "size": "full", "aspectRatio": "4:5", "aspectMode": "cover"},
            {
                "type": "box",
                "layout": "vertical",
                "position": "absolute",
                "offsetTop": "10px",
                "offsetBottom": "10px",
                "offsetStart": "10px",
                "offsetEnd": "10px",
                "borderWidth": "2px",
                "borderColor": GOLD_LIGHT,
                "cornerRadius": "14px",
                "contents": [{"type": "filler"}],
            },
            {
                "type": "box",
                "layout": "vertical",
                "position": "absolute",
                "offsetBottom": "26px",
                "offsetStart": "28px",
                "offsetEnd": "28px",
                "paddingAll": "10px",
                "cornerRadius": "12px",
                "backgroundColor": FRAME_WHITE,
                "borderWidth": "1px",
                "borderColor": GOLD_LIGHT,
                "contents": [
                    _text(f"✦ No.{card['id']:02d} ✦", size="xs", color=GOLD, weight="bold", align="center"),
                    _text(card["name"], size="md", color=DEEP_PURPLE, weight="bold", align="center"),
                ],
            },
        ],
    }


def _gradient_hero(card: dict) -> dict:
    """公開URL未設定のときの予備デザイン。"""
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


def _body(contents: list[dict]) -> dict:
    return {
        "type": "box",
        "layout": "vertical",
        "paddingAll": "20px",
        "background": _gradient(),
        "borderWidth": "2px",
        "borderColor": GOLD_LIGHT,
        "contents": contents,
    }


def _ornament() -> dict:
    """金の飾り罫（── ✦ ──）"""
    line = {"type": "separator", "color": GOLD_LIGHT}
    return {
        "type": "box",
        "layout": "horizontal",
        "alignItems": "center",
        "margin": "lg",
        "contents": [
            {"type": "box", "layout": "vertical", "flex": 1, "contents": [line]},
            _text("✦", size="xs", color=GOLD, align="center", flex=0, margin="sm"),
            {"type": "box", "layout": "vertical", "flex": 1, "margin": "sm", "contents": [line]},
        ],
    }


def _gradient() -> dict:
    return {
        "type": "linearGradient",
        "angle": "160deg",
        "startColor": "#EBDDFB",
        "centerColor": "#FBF3FF",
        "endColor": "#F9E1EF",
    }


def _text(text: str, size: str = "sm", color: str = DEEP_PURPLE, **extra) -> dict:
    return {"type": "text", "text": text, "size": size, "color": color, "wrap": True, **extra}


def _flex(alt_text: str, contents: dict) -> dict:
    return {"type": "flex", "altText": alt_text[:400], "contents": contents}
