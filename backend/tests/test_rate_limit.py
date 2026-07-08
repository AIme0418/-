from collections import defaultdict, deque

import pytest
from fastapi import HTTPException

from app import rate_limit


def test_per_ip_limit_allows_up_to_max(monkeypatch):
    monkeypatch.setattr(rate_limit, "_ip_requests", defaultdict(deque))
    for _ in range(rate_limit.PER_IP_MAX_REQUESTS):
        rate_limit.enforce_per_ip_limit("1.2.3.4")


def test_per_ip_limit_blocks_after_max(monkeypatch):
    monkeypatch.setattr(rate_limit, "_ip_requests", defaultdict(deque))
    for _ in range(rate_limit.PER_IP_MAX_REQUESTS):
        rate_limit.enforce_per_ip_limit("1.2.3.4")
    with pytest.raises(HTTPException) as exc_info:
        rate_limit.enforce_per_ip_limit("1.2.3.4")
    assert exc_info.value.status_code == 429


def test_per_ip_limit_tracks_ips_independently(monkeypatch):
    monkeypatch.setattr(rate_limit, "_ip_requests", defaultdict(deque))
    for _ in range(rate_limit.PER_IP_MAX_REQUESTS):
        rate_limit.enforce_per_ip_limit("1.2.3.4")
    # 別IPは影響を受けない
    rate_limit.enforce_per_ip_limit("5.6.7.8")
