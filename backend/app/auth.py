from fastapi import Header, HTTPException

from .config import settings
from .storage import log_security_event


def require_admin_token(authorization: str = Header(default="")) -> None:
    expected = f"Bearer {settings.admin_api_token}"
    if not authorization or authorization != expected:
        log_security_event("admin_auth_failed")
        raise HTTPException(status_code=401, detail="unauthorized")
