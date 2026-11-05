"""「カードを開く」演出のための、1回ごとの抽選状態。

・カードはボタンを押した瞬間に決まる（裏面を出した時点では決まっていない）
・同じボタンを何度押しても、結果は最初の1回だけ
・時間がたったボタンは期限切れとして扱う

状態はサーバーのメモリに置く（無料プランでは再起動で消えるが、
そのときもボタンに書いた時刻で期限を判定するので、困るのは
「開いた直後に再起動した」という、ごくまれな場合だけ）。
"""

import secrets
import time
from collections import OrderedDict
from threading import Lock
from urllib.parse import parse_qs, urlencode

SESSION_TTL_SECONDS = 30 * 60  # カードを開けるのは、裏面が届いてから30分まで
_MAX_SESSIONS = 5000

_lock = Lock()
# sid -> {"user": str, "kind": str, "created": float, "card_id": int | None, "opened_at": float | None}
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


def create(user_id: str, kind: str) -> str:
    """裏面を見せるときに呼ぶ。ボタンに埋め込むpostbackデータを返す。"""
    now = _now()
    sid = secrets.token_urlsafe(9)
    with _lock:
        _prune(now)
        _sessions[sid] = {"user": user_id, "kind": kind, "created": now, "card_id": None, "opened_at": None}
    return urlencode({"oracle": "open", "kind": kind, "sid": sid, "ts": int(now)})


def parse(data: str) -> dict:
    return {k: v[0] for k, v in parse_qs(data).items()}


def open_card(user_id: str, sid: str, kind: str, issued_at: int, draw) -> tuple[str, int | None]:
    """カードを開く。

    戻り値: (状態, カード番号)
      "new"     … 今回はじめて開いた（カード番号あり）
      "already" … すでに開いたボタン（カード番号は最初の結果）
      "expired" … 期限切れ
    """
    now = _now()
    with _lock:
        s = _sessions.get(sid)
        created = s["created"] if s else float(issued_at)
        if now - created > SESSION_TTL_SECONDS:
            return "expired", None
        if s is None:
            # 再起動でメモリが消えたが、期限内のボタン。ここで新しく引く
            s = {"user": user_id, "kind": kind, "created": created, "card_id": None, "opened_at": None}
            _sessions[sid] = s
        if s["user"] != user_id:
            return "expired", None
        if s["card_id"] is not None:
            return "already", s["card_id"]
        s["card_id"] = draw()
        s["opened_at"] = now
        return "new", s["card_id"]


def opened_seconds_ago(sid: str) -> float | None:
    with _lock:
        s = _sessions.get(sid)
        if not s or s["opened_at"] is None:
            return None
        return _now() - s["opened_at"]
