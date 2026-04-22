"""Supabase Auth integration.

The frontend sends `Authorization: Bearer <jwt>` on every api() call once a
user has signed in. We verify the JWT against the project's shared secret
(same one Supabase uses to mint tokens) and load-or-create a Profile row
for that user. Guest calls without the header fall through unauthenticated.
"""

from __future__ import annotations

from datetime import datetime

import jwt
from fastapi import Depends, Header, HTTPException
from sqlmodel import Session

from app.config import settings
from app.db import get_session
from app.models import Profile


class AuthedUser:
    __slots__ = ("user_id", "email")

    def __init__(self, user_id: str, email: str | None) -> None:
        self.user_id = user_id
        self.email = email


def decode_supabase_jwt(token: str) -> AuthedUser:
    """Verify a Supabase access token and return (user_id, email). Raises
    401 on any problem — expired, bad signature, missing sub, etc."""
    if not settings.supabase_jwt_secret:
        raise HTTPException(status_code=503, detail="auth not configured")
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="token expired")
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=f"invalid token: {exc}")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="token missing sub")
    email = payload.get("email")
    return AuthedUser(user_id=user_id, email=email)


def get_authed_user(
    authorization: str | None = Header(default=None),
) -> AuthedUser | None:
    """Optional auth: returns the authed user if a valid bearer token is
    present, None otherwise. Routes that need to branch on auth state use
    this; routes that require auth should use `require_authed_user`."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    # Skip admin bearer (worker token) — those go through require_worker.
    token = authorization.split(" ", 1)[1].strip()
    if not token or token == settings.worker_token:
        return None
    try:
        return decode_supabase_jwt(token)
    except HTTPException:
        return None


def require_authed_user(
    user: AuthedUser | None = Depends(get_authed_user),
) -> AuthedUser:
    if user is None:
        raise HTTPException(status_code=401, detail="sign in required")
    return user


def load_or_create_profile(
    session: Session, user: AuthedUser, signup_bonus: int | None = None
) -> Profile:
    """Return the Profile row for this user, creating it with the signup
    bonus on first sight. `signup_bonus` overrides the config default (used
    by tests)."""
    profile = session.get(Profile, user.user_id)
    if profile is not None:
        # Keep email fresh in case the user changes it in Supabase.
        if user.email and profile.email != user.email:
            profile.email = user.email
            profile.updated_at = datetime.utcnow()
            session.add(profile)
            session.commit()
            session.refresh(profile)
        return profile

    bonus = settings.signup_bonus_words if signup_bonus is None else signup_bonus
    profile = Profile(
        user_id=user.user_id,
        email=user.email,
        credits_balance=bonus,
        credits_used=0,
    )
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


def get_profile_optional(
    user: AuthedUser | None = Depends(get_authed_user),
    session: Session = Depends(get_session),
) -> Profile | None:
    """Resolves to the caller's Profile when authed, None for guests."""
    if user is None:
        return None
    return load_or_create_profile(session, user)
