"""「カードを開く」演出のための、1回の占いごとの抽選状態。

・カードはボタンを押した瞬間に決まる（裏面を出した時点では決まっていない）
・同じボタンを何度押しても、結果は最初の1回だけ
・スリーオラクルは1枚ずつ開き、同じカードは2度出ない
・時間がたったボタンは期限切れとして扱う

状態はサーバーのメモリに置く。無料プランでは再起動で消えるが、ボタンに
「いつ配ったか」と「それまでに開いたカード番号」を書いておくので、
期限の判定と続きの再開はできる。困るのは「開いた直後に再起動した」という、
ごくまれな場合だけ（そのときは同じボタンでもう一度引けてしまう）。
"""

import secrets
import time
from collections import OrderedDict
from threading import Lock
from urllib.parse import parse_qs, urlencode

SESSION_TTL_SECONDS = 30 * 60  # 裏面が届いてから30分まで開ける
_MAX_SESSIONS = 5000

_lock = Lock()
# sid -> {"user": str, "kind": str, "created": float, "cards": list[int], "opened_at": float | None}
_sessions: "OrderedDict[str, dict]" = OrderedDict()


def _now() -> float:
    return time.time()


def _prune(now: float) -> None:
    while _sessions:
        sid, s = next(iter(_sessions.items()))
        if now - s["created"] > SESSION_TTL_SECONDS * 2 or len(_sessions) > _MAX_SESSIONS:
            _sessions.pop(sid)
        else:
            break


def _data(kind: str, sid: str, created: float, step: int, prior: list[int]) -> str:
    params = {"oracle": "open", "kind": kind, "sid": sid, "ts": int(created), "step": step}
    if prior:
        params["prior"] = ",".join(str(i) for i in prior)
    return urlencode(params)


def create(user_id: str, kind: str) -> str:
    """1枚目の裏面を見せるときに呼ぶ。ボタンに埋め込むpostbackデータを返す。"""
    now = _now()
    sid = secrets.token_urlsafe(9)
    with _lock:
        _prune(now)
        _sessions[sid] = {"user": user_id, "kind": kind, "created": now, "cards": [], "opened_at": None}
    return _data(kind, sid, now, 1, [])


def next_step_data(sid: str, kind: str, step: int, prior: list[int]) -> str:
    """スリーオラクルの次の1枚のボタン用データ。"""
    with _lock:
        s = _sessions.get(sid)
        created = s["created"] if s else _now()
    return _data(kind, sid, created, step, prior)


def parse(data: str) -> dict:
    return {k: v[0] for k, v in parse_qs(data).items()}


def open_card(user_id: str, sid: str, kind: str, issued_at: int, draw, step: int = 1, prior=()) -> tuple[str, list[int]]:
    """step枚目のカードを開く。draw(除外する番号の集合) で1枚引く。

    戻り値: (状態, ここまでに開いたカード番号)
      "new"     … 今回はじめて開いた
      "already" … すでに開いたボタン
      "expired" … 期限切れ・他の人のボタンなど
    """
    now = _now()
    with _lock:
        s = _sessions.get(sid)
        created = s["created"] if s else float(issued_at)
        if now - created > SESSION_TTL_SECONDS:
            return "expired", []
        if s is None:
            # 再起動でメモリが消えたが、期限内のボタン。ボタンに書いた続きから再開する
            s = {"user": user_id, "kind": kind, "created": created, "cards": list(prior), "opened_at": None}
            _sessions[sid] = s
        if s["user"] != user_id or s["kind"] != kind:
            return "expired", []
        if len(s["cards"]) >= step:
            return "already", s["cards"][:step]
        if len(s["cards"]) != step - 1:
            return "expired", []
        s["cards"].append(draw(set(s["cards"])))
        s["opened_at"] = now
        return "new", list(s["cards"])


def opened_seconds_ago(sid: str) -> float | None:
    with _lock:
        s = _sessions.get(sid)
        if not s or s["opened_at"] is None:
            return None
        return _now() - s["opened_at"]
