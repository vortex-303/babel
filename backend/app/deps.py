from __future__ import annotations

from fastapi import Depends, Header, HTTPException

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


# Sentinel owner_id used for admin callers — means "bypass the filter,
# see everything". Picked so it can't collide with a real client-generated
# UUID (UUIDs never contain '*').
OWNER_ADMIN = "*"


def get_owner_id(
    x_session_id: str | None = Header(default=None),
    admin: bool = Depends(is_admin),
) -> str:
    """Identify the caller for tenancy filtering. Admin gets the sentinel
    OWNER_ADMIN; everyone else gets their X-Session-ID header (required
    for any tenancy-scoped endpoint — frontend generates + persists it in
    localStorage). Raises 400 if a non-admin request has no session id."""
    if admin:
        return OWNER_ADMIN
    if not x_session_id:
        raise HTTPException(
            status_code=400,
            detail="missing X-Session-ID header; the frontend should set one",
        )
    return x_session_id


def require_admin(x_admin_code: str | None = Header(default=None)) -> None:
    """Dependency that 403s any request without a valid admin pass-code.

    Also 403s if BABEL_ADMIN_CODE is not configured on the server — better
    to refuse than to silently allow everyone through."""
    if not settings.admin_code:
        raise HTTPException(status_code=403, detail="admin gate not configured")
    if not x_admin_code or x_admin_code != settings.admin_code:
        raise HTTPException(status_code=403, detail="admin access required")


def require_worker(authorization: str | None = Header(default=None)) -> None:
    """Bearer-token auth for /api/worker/* endpoints. Token lives in the
    BABEL_WORKER_TOKEN env var on the backend and in the worker's config."""
    if not settings.worker_token:
        raise HTTPException(status_code=403, detail="worker gate not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    if authorization[len("Bearer ") :] != settings.worker_token:
        raise HTTPException(status_code=403, detail="invalid worker token")
