"""不正アクセスの試みなどを、管理者が後から確認するためのエンドポイント。"""

from fastapi import APIRouter, Depends

from .. import storage
from ..auth import require_admin_token

router = APIRouter(dependencies=[Depends(require_admin_token)])


@router.get("/api/security-events")
def list_security_events(limit: int = 50):
    return storage.read_jsonl(storage.SECURITY_LOG_FILE, limit=limit)
