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
