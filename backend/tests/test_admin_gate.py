from __future__ import annotations

import pytest

from app.config import settings
from app.deps import is_admin, require_admin


def test_is_admin_rejects_when_code_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "admin_code", "")
    assert is_admin("whatever") is False
    assert is_admin(None) is False


def test_is_admin_rejects_wrong_code(monkeypatch):
    monkeypatch.setattr(settings, "admin_code", "secret")
    assert is_admin("wrong") is False
    assert is_admin(None) is False


def test_is_admin_accepts_correct_code(monkeypatch):
    monkeypatch.setattr(settings, "admin_code", "secret")
    assert is_admin("secret") is True


def test_require_admin_blocks_when_unconfigured(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(settings, "admin_code", "")
    with pytest.raises(HTTPException) as exc:
        require_admin("anything")
    assert exc.value.status_code == 403
    assert "not configured" in exc.value.detail.lower()


def test_require_admin_allows_correct_code(monkeypatch):
    monkeypatch.setattr(settings, "admin_code", "secret")
    # Should not raise.
    require_admin("secret")


def test_require_admin_rejects_wrong_code(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(settings, "admin_code", "secret")
    with pytest.raises(HTTPException) as exc:
        require_admin("wrong")
    assert exc.value.status_code == 403
