from __future__ import annotations

from fastapi import Header, HTTPException

from app.config import settings


def is_admin(x_admin_code: str | None = Header(default=None)) -> bool:
    """Returns True when the caller provided the correct admin pass-code.

    Safe to use on public endpoints that branch behavior based on caller
    identity (e.g. upload size limits). For endpoints that must only be
    reachable by admins, prefer `require_admin`."""
    code = settings.admin_code
    if not code:
        return False
    return bool(x_admin_code) and x_admin_code == code


def require_admin(x_admin_code: str | None = Header(default=None)) -> None:
    """Dependency that 403s any request without a valid admin pass-code.

    Also 403s if BABEL_ADMIN_CODE is not configured on the server — better
    to refuse than to silently allow everyone through."""
    if not settings.admin_code:
        raise HTTPException(status_code=403, detail="admin gate not configured")
    if not x_admin_code or x_admin_code != settings.admin_code:
        raise HTTPException(status_code=403, detail="admin access required")
