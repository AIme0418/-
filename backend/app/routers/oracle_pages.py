"""カード一覧ページ（LINEの「カード一覧」ボタンから開く、スマホ向けの1ページ）。"""

import html

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from ..oracle import deck

router = APIRouter()


def _card_html(card: dict) -> str:
    esc = html.escape
    image = deck.card_image_filename(card["id"])
    if image:
        visual = f'<img src="/static/cards/{esc(image)}" alt="{esc(card["name"])}" loading="lazy">'
    else:
        visual = (
            '<div class="ph"><span class="st">✧ ✦ ✧</span>'
            '<span class="nm">画像準備中</span></div>'
        )
    return f"""
<details class="card">
  <summary>
    <div class="visual">{visual}</div>
    <div class="cap"><span class="num">No.{card['id']:02d}</span>
      <span class="name">{esc(card['name'])}</span>
      <span class="kw">「{esc(card['keyword'])}」</span></div>
  </summary>
  <div class="detail">
    <p>{esc(card['message'])}</p>
    <h3>💗 恋愛・人間関係</h3><p>{esc(card['love'])}</p>
    <h3>💰 仕事・金運</h3><p>{esc(card['work'])}</p>
    <h3>🕊 心の癒し</h3><p>{esc(card['healing'])}</p>
  </div>
</details>"""


PAGE_TEMPLATE = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>カード一覧｜ルミエル 天使と女神のオラクル</title>
<style>
:root{--bg:#fbf7ff;--ink:#4b3a63;--soft:#6c6080;--gold:#b08a2e;--pink:#d9739b;--line:#eadff5}
*{box-sizing:border-box}
body{margin:0;background:linear-gradient(160deg,#efe3fb,#fff8ea 50%,#fde4ee);background-attachment:fixed;
 color:var(--ink);font-family:"Hiragino Mincho ProN","Yu Mincho",serif;line-height:1.8}
header{text-align:center;padding:32px 16px 12px}
header h1{font-size:1.35rem;margin:0}
header p{color:var(--gold);margin:4px 0 0;font-size:.9rem;letter-spacing:.1em}
.hint{font-size:.8rem;color:var(--soft);text-align:center;margin:8px 16px 20px}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:14px;padding:0 16px 40px;max-width:900px;margin:0 auto}
@media(min-width:640px){.grid{grid-template-columns:repeat(4,1fr)}}
.card{background:rgba(255,255,255,.75);border:1px solid #e3cf9a;border-radius:14px;overflow:hidden;
 box-shadow:0 4px 14px rgba(150,110,180,.15)}
.card[open]{grid-column:1/-1}
summary{list-style:none;cursor:pointer}
summary::-webkit-details-marker{display:none}
.visual img,.ph{display:block;width:100%;aspect-ratio:2/3;object-fit:cover}
.card[open] .visual{max-width:320px;margin:0 auto}
.ph{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;padding:10px;text-align:center;
 background:linear-gradient(135deg,#e8d9f7,#fff6e0 50%,#fadce8)}
.ph .st{color:var(--gold)}.ph .no{color:var(--gold);font-weight:bold;font-size:.8rem}.ph .nm{font-weight:bold;font-size:.85rem}
.cap{padding:8px 10px 12px;text-align:center;display:flex;flex-direction:column}
.num{color:var(--gold);font-size:.72rem}.name{font-weight:bold;font-size:.85rem}.kw{color:var(--pink);font-size:.8rem}
.detail{padding:4px 18px 18px;border-top:1px solid var(--line);font-size:.92rem}
.detail h3{font-size:.85rem;color:var(--gold);margin:14px 0 2px}
.detail p{margin:4px 0}
</style></head><body>
<header><h1>✦ ルミエル ✦</h1><p>天使と女神のオラクル　全44枚</p></header>
<p class="hint">カードをタップすると、くわしいメッセージが開きます</p>
<main class="grid">__CARDS__</main>
</body></html>"""


@router.get("/cards", response_class=HTMLResponse)
def card_list_page() -> str:
    cards = "".join(_card_html(c) for c in deck.load_cards())
    return PAGE_TEMPLATE.replace("__CARDS__", cards)
