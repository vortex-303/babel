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


class WorkerIdentity:
    """What kind of caller reached a /worker/* endpoint.

    `user_id` is None for the shared admin-token path (legacy / admin fleet),
    and a Supabase UUID for self-hosted user workers. Downstream code uses
    user_id to scope claim-next + decide whether to charge credits."""

    __slots__ = ("user_id", "email")

    def __init__(self, user_id: str | None, email: str | None) -> None:
        self.user_id = user_id
        self.email = email

    @property
    def is_admin_worker(self) -> bool:
        return self.user_id is None


def require_worker(authorization: str | None = Header(default=None)) -> WorkerIdentity:
    """Accept either the shared admin worker token OR a Supabase JWT from a
    user who purchased the self-host license. Admin-token callers are
    unscoped; user callers are scoped to their own jobs by the router."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()

    # Fast path: shared admin token. Empty setting disables this branch.
    if settings.worker_token and token == settings.worker_token:
        return WorkerIdentity(user_id=None, email=None)

    # User worker path: decode Supabase JWT and enforce license flag.
    # Imports are local to avoid a circular dependency (auth.py imports deps).
    from app.auth import decode_supabase_jwt
    from app.db import new_session
    from app.models import Profile

    try:
        user = decode_supabase_jwt(token)
    except HTTPException as exc:
        # Keep the original message so the worker can surface it clearly.
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    with new_session() as s:
        profile = s.get(Profile, user.user_id)
        if profile is None or not profile.self_host_license:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "license_required",
                    "message": "Self-host license required to run a worker.",
                },
            )
    return WorkerIdentity(user_id=user.user_id, email=user.email)
