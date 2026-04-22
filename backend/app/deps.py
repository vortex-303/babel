from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Query

from app.auth import AuthedUser, get_authed_user
from app.config import settings


def is_admin(
    x_admin_code: str | None = Header(default=None),
    admin: str | None = Query(default=None),
) -> bool:
    """Returns True when the caller provided the correct admin pass-code.

    Accepts the code either as the X-Admin-Code header (normal API calls) or
    as ?admin= query param (browser downloads via <a href download> can't
    set headers). Safe to use on public endpoints that branch behavior based
    on caller identity (e.g. upload size limits). For endpoints that must
    only be reachable by admins, prefer `require_admin`."""
    code = settings.admin_code
    if not code:
        return False
    provided = x_admin_code or admin
    return bool(provided) and provided == code


# Sentinel owner_id used for admin callers — means "bypass the filter,
# see everything". Picked so it can't collide with a real client-generated
# UUID (UUIDs never contain '*').
OWNER_ADMIN = "*"


def get_owner_id(
    x_session_id: str | None = Header(default=None),
    session: str | None = Query(default=None),
    admin: bool = Depends(is_admin),
    user: AuthedUser | None = Depends(get_authed_user),
) -> str:
    """Identify the caller for tenancy filtering. Priority order:
        admin (sentinel "*") > authed user id > session id (header or ?query=).
    Browser downloads via <a href download> can't set headers so they pass
    the session/admin in the URL instead."""
    if admin:
        return OWNER_ADMIN
    if user is not None:
        return user.user_id
    owner = x_session_id or session
    if not owner:
        raise HTTPException(
            status_code=400,
            detail="missing session: sign in or send X-Session-ID / ?session=",
        )
    return owner


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
