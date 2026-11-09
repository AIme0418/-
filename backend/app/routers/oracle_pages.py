"""カード一覧ページ（LINEの「カード一覧」ボタンから開く、スマホ向けの1ページ）。"""

import html

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ..config import settings
from ..oracle import deck
from ..rate_limit import enforce_per_ip_limit

router = APIRouter()


def _card_html(card: dict) -> str:
    esc = html.escape
    image = deck.card_image_filename(card["id"])
    if image:
        visual = f'<img src="/static/cards/{esc(image)}" alt="{esc(card["name"])}" loading="lazy">'
    else:
        visual = (
            '<div class="ph"><img src="/static/ui/card_back.jpg" alt="" loading="lazy">'
            f'<span class="tag">No.{card["id"]:02d}</span></div>'
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
:root{--ink:#5a2d86;--soft:#5e4a78;--gold:#a9791c;--goldl:#e2c06a;--pink:#c4508f}
*{box-sizing:border-box}
body{margin:0;color:var(--ink);font-family:"Hiragino Mincho ProN","Yu Mincho",serif;line-height:1.8;
 background:#efe3fb url(/static/ui/bg.jpg) center/cover fixed}
body::before{content:"";position:fixed;inset:0;background:linear-gradient(180deg,rgba(255,255,255,.15),rgba(250,240,255,.55));z-index:-1}
header{text-align:center;padding:24px 16px 8px}
header img{width:132px;height:132px;filter:drop-shadow(0 4px 14px rgba(120,60,170,.35))}
header p{color:var(--ink);margin:6px auto 0;font-size:.9rem;letter-spacing:.15em;font-weight:bold;
 background:rgba(255,255,255,.7);display:inline-block;padding:2px 16px;border-radius:999px;border:1px solid var(--goldl)}
.hint{font-size:.8rem;color:var(--soft);text-align:center;margin:10px 16px 18px}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:14px;padding:0 16px 40px;max-width:900px;margin:0 auto}
@media(min-width:640px){.grid{grid-template-columns:repeat(4,1fr)}}
.card{background:linear-gradient(160deg,#fbf6ff,#fff 50%,#fdf0f7);border:2px solid var(--goldl);border-radius:16px;overflow:hidden;
 box-shadow:0 0 0 3px rgba(255,255,255,.6),0 6px 18px rgba(120,60,170,.25)}
.card[open]{grid-column:1/-1}
summary{list-style:none;cursor:pointer}
summary::-webkit-details-marker{display:none}
.visual{position:relative}
.visual img{display:block;width:100%;aspect-ratio:2/3;object-fit:cover}
.card[open] .visual{max-width:320px;margin:0 auto}
.ph{position:relative}
.ph::after{content:"";position:absolute;inset:6px;border:1.5px solid var(--goldl);border-radius:10px;pointer-events:none}
.tag{position:absolute;left:50%;bottom:10px;transform:translateX(-50%);background:rgba(255,255,255,.85);color:var(--gold);
 font-weight:bold;font-size:.75rem;padding:0 10px;border-radius:999px;border:1px solid var(--goldl)}
.cap{padding:8px 10px 12px;text-align:center;display:flex;flex-direction:column}
.num{color:var(--gold);font-size:.72rem}.name{font-weight:bold;font-size:.85rem}.kw{color:var(--pink);font-size:.8rem;font-weight:bold}
.detail{padding:4px 18px 18px;border-top:1px solid var(--goldl);font-size:.92rem}
.detail h3{font-size:.85rem;color:var(--gold);margin:14px 0 2px}
.detail p{margin:4px 0}
</style></head><body>
<header><img src="/static/ui/emblem.png" alt="ルミエル 天使と女神のオラクル"><br><p>✦ 全44枚のカード ✦</p></header>
<p class="hint">カードをタップすると、くわしいメッセージが開きます</p>
<main class="grid">__CARDS__</main>
</body></html>"""


@router.get("/cards", response_class=HTMLResponse)
def card_list_page() -> str:
    cards = "".join(_card_html(c) for c in deck.load_cards())
    return PAGE_TEMPLATE.replace("__CARDS__", cards)


@router.post("/api/oracle/draw")
def draw_one(request: Request) -> dict:
    """演出ページ（/oracle/）の「カードを引く」で1枚引く。

    カードはボタンを押した瞬間にサーバーで決まる（ページ側では選ばない）。
    AIは使わないので費用はかからない。連打だけIPごとの上限で防ぐ。
    """
    enforce_per_ip_limit(request.client.host if request.client else "unknown")
    card = deck.draw(1)[0]
    image = deck.card_image_filename(card["id"])
    return {
        "id": card["id"],
        "name": card["name"],
        "keyword": card["keyword"],
        "message": card["message"],
        "love": card["love"],
        "work": card["work"],
        "healing": card["healing"],
        "image": f"/static/cards/{image}" if image else None,
    }


def oracle_page_url(base_url: str = "") -> str | None:
    base = base_url or settings.public_base_url
    if not base.startswith("https://"):
        return None
    return f"{base.rstrip('/')}/oracle/"
