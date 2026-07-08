import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException

from .config import settings
from .storage import increment_and_check_daily_usage


def enforce_daily_limit() -> None:
    """1日の処理件数が上限を超えていたら429を返す（コスト暴走の防止）。"""
    ok, count = increment_and_check_daily_usage(settings.daily_message_limit)
    if not ok:
        raise HTTPException(
            status_code=429,
            detail=f"本日のメッセージ処理上限（{settings.daily_message_limit}件）に達しました。",
        )


PER_IP_WINDOW_SECONDS = 60
PER_IP_MAX_REQUESTS = 10

_ip_lock = Lock()
_ip_requests: dict[str, deque[float]] = defaultdict(deque)


def enforce_per_ip_limit(client_ip: str) -> None:
    """認証のない公開エンドポイントを、同一IPからの連続アクセスから守る。"""
    now = time.monotonic()
    with _ip_lock:
        timestamps = _ip_requests[client_ip]
        while timestamps and now - timestamps[0] > PER_IP_WINDOW_SECONDS:
            timestamps.popleft()
        if len(timestamps) >= PER_IP_MAX_REQUESTS:
            raise HTTPException(
                status_code=429,
                detail="アクセスが集中しています。少し時間をおいてお試しください。",
            )
        timestamps.append(now)
