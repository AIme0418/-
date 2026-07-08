from fastapi import Header, HTTPException

from .config import settings


def require_admin_token(authorization: str = Header(default="")) -> None:
    expected = f"Bearer {settings.admin_api_token}"
    if not authorization or authorization != expected:
        raise HTTPException(status_code=401, detail="unauthorized")
