from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth import require_admin_token
from ..storage import (
    EXTERNAL_GPT_LOG_FILE,
    HEALY_LOG_FILE,
    append_external_gpt_event,
    append_healy_event,
    read_jsonl,
)

router = APIRouter(dependencies=[Depends(require_admin_token)])


class HealyEvent(BaseModel):
    source: str  # 例: "healy_device", "healy_app"
    data: dict[str, Any]


class HealyCoachingItem(BaseModel):
    category: str  # 例: "焦点を特定する", "職業", "個人的責任"
    match_percent: float
    session_count: int | None = None
    code: str | None = None  # Healyアプリ内の内部コード（例: "D 1E12"）
    target_state: str  # 「目標とする状態」のアファメーション文


class HealyCoachingReport(BaseModel):
    # 個人情報保護のため、フルネームではなくイニシャルで保存する運用とする
    client_initials: str
    report_datetime: str
    main_focus: str | None = None  # 「主患部」のアファメーション文
    items: list[HealyCoachingItem] = []


class ExternalGptEvent(BaseModel):
    source: str  # 例: 相手のGPT/サービス名
    message: str
    context: dict[str, Any] | None = None


@router.post("/api/healy-data")
def receive_healy_data(event: HealyEvent):
    record = {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "source": event.source,
        "data": event.data,
    }
    append_healy_event(record)
    return {"status": "stored"}


@router.post("/api/healy-data/coaching-report")
def receive_coaching_report(report: HealyCoachingReport):
    record = {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "source": "healy_coaching_report",
        "data": report.model_dump(),
    }
    append_healy_event(record)
    return {"status": "stored"}


@router.get("/api/healy-data")
def list_healy_data(limit: int = 50):
    return read_jsonl(HEALY_LOG_FILE, limit=limit)


@router.post("/api/external-gpt")
def receive_external_gpt(event: ExternalGptEvent):
    record = {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "source": event.source,
        "message": event.message,
        "context": event.context,
    }
    append_external_gpt_event(record)
    return {"status": "stored"}


@router.get("/api/external-gpt")
def list_external_gpt(limit: int = 50):
    return read_jsonl(EXTERNAL_GPT_LOG_FILE, limit=limit)
