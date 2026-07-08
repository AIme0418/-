import pytest
from fastapi import HTTPException

from app.auth import require_admin_token
from app.config import settings


def test_correct_token_passes(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "secret-token")
    require_admin_token(authorization="Bearer secret-token")


def test_wrong_token_raises_401(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "secret-token")
    with pytest.raises(HTTPException) as exc_info:
        require_admin_token(authorization="Bearer wrong-token")
    assert exc_info.value.status_code == 401


def test_missing_header_raises_401(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "secret-token")
    with pytest.raises(HTTPException) as exc_info:
        require_admin_token(authorization="")
    assert exc_info.value.status_code == 401
