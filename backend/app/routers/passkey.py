"""Passkey / WebAuthn as a second credential on a Supabase account.

Flow:
    1. User signs up with email + password → Supabase session.
    2. Signed-in user hits /passkey/register/begin (Supabase JWT required)
       → credential bound to their Supabase user_id + email.
    3. Next visit, /passkey/login/begin (public) → browser picks discoverable
       credential → /passkey/login/complete verifies assertion → backend
       calls Supabase Admin generate_link to mint a one-time magic-link
       token → frontend exchanges the token for a real Supabase session.

No separate babel user space: passkey and email point at the same auth.users
row, so tenancy / credits / billing all Just Work.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.cose import COSEAlgorithmIdentifier
from webauthn.helpers.structs import (
    AuthenticationCredential,
    RegistrationCredential,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.auth import AuthedUser, require_authed_user
from app.config import settings
from app.db import get_session
from app.models import PasskeyChallenge, PasskeyCredential

router = APIRouter(prefix="/passkey", tags=["passkey"])


# Challenges expire quickly so a stolen in-flight ceremony can't be replayed.
CHALLENGE_TTL_SECONDS = 300


def _rp_id() -> str:
    """Relying Party id — the domain passkeys are scoped to. In prod this is
    `babeltower.lat`. For localhost dev you'd set BABEL_PASSKEY_RP_ID=localhost."""
    return os.environ.get("BABEL_PASSKEY_RP_ID") or settings.passkey_rp_id


def _rp_name() -> str:
    return os.environ.get("BABEL_PASSKEY_RP_NAME") or "babel"


def _origin() -> list[str]:
    """Allowed origins the authenticator must match. Comma-separated so we
    can authorize both apex + preview URLs at the same time."""
    raw = os.environ.get("BABEL_PASSKEY_ORIGIN") or settings.passkey_origin
    return [o.strip() for o in raw.split(",") if o.strip()]


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _purge_stale_challenges(session: Session) -> None:
    """Cheap garbage collector — runs on every ceremony so table stays tiny."""
    cutoff = datetime.utcnow() - timedelta(seconds=CHALLENGE_TTL_SECONDS)
    stale = session.exec(
        select(PasskeyChallenge).where(PasskeyChallenge.created_at < cutoff)
    ).all()
    for c in stale:
        session.delete(c)
    if stale:
        session.commit()


def _generate_supabase_magic_link(email: str) -> dict:
    """Call Supabase Admin API to mint a one-time magic-link token for the
    given email. We return the full response so the frontend can pick out
    hashed_token + verification_type and call supabase.auth.verifyOtp."""
    if not settings.supabase_url or not settings.supabase_service_key:
        raise HTTPException(status_code=503, detail="supabase admin not configured")
    r = httpx.post(
        f"{settings.supabase_url}/auth/v1/admin/generate_link",
        headers={
            "apikey": settings.supabase_service_key,
            "Authorization": f"Bearer {settings.supabase_service_key}",
            "Content-Type": "application/json",
        },
        json={"type": "magiclink", "email": email},
        timeout=10.0,
    )
    if r.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"supabase admin link failed ({r.status_code}): {r.text[:200]}",
        )
    return r.json()


# --- Registration (requires signed-in Supabase user) -------------------------


@router.post("/register/begin")
def register_begin(
    user: AuthedUser = Depends(require_authed_user),
    session: Session = Depends(get_session),
) -> dict:
    """Mint registration options for the caller's Supabase account. Credential
    will be stored against `user.user_id` so future passkey logins resolve
    back to the same auth.users row."""
    _purge_stale_challenges(session)

    # Exclude already-registered credentials so the browser doesn't let the
    # user double-enroll the same authenticator on this account.
    existing = session.exec(
        select(PasskeyCredential).where(PasskeyCredential.user_id == user.user_id)
    ).all()

    options = generate_registration_options(
        rp_id=_rp_id(),
        rp_name=_rp_name(),
        user_id=user.user_id.encode(),
        user_name=user.email or user.user_id,
        user_display_name=user.email or user.user_id,
        supported_pub_key_algs=[
            COSEAlgorithmIdentifier.ECDSA_SHA_256,
            COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,
        ],
        exclude_credentials=[
            {"id": _b64url_decode(c.credential_id), "type": "public-key"}
            for c in existing
        ],
        authenticator_selection={
            "residentKey": ResidentKeyRequirement.PREFERRED,
            "userVerification": UserVerificationRequirement.PREFERRED,
        },
    )

    challenge_id = secrets.token_urlsafe(16)
    session.add(
        PasskeyChallenge(
            id=challenge_id,
            challenge=_b64url(options.challenge),
            kind="register",
            user_id=user.user_id,
            email=user.email,
        )
    )
    session.commit()

    return {
        "challenge_id": challenge_id,
        "options": json.loads(options_to_json(options)),
    }


class RegisterCompleteBody(BaseModel):
    challenge_id: str
    credential: dict
    label: str | None = None


@router.post("/register/complete")
def register_complete(
    body: RegisterCompleteBody,
    user: AuthedUser = Depends(require_authed_user),
    session: Session = Depends(get_session),
) -> dict:
    challenge = session.get(PasskeyChallenge, body.challenge_id)
    if (
        challenge is None
        or challenge.kind != "register"
        or challenge.user_id != user.user_id
    ):
        raise HTTPException(status_code=400, detail="unknown or expired challenge")
    if (datetime.utcnow() - challenge.created_at).total_seconds() > CHALLENGE_TTL_SECONDS:
        session.delete(challenge)
        session.commit()
        raise HTTPException(status_code=400, detail="challenge expired")

    try:
        verification = verify_registration_response(
            credential=RegistrationCredential.parse_raw(json.dumps(body.credential)),
            expected_challenge=_b64url_decode(challenge.challenge),
            expected_rp_id=_rp_id(),
            expected_origin=_origin(),
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"attestation failed: {exc}")

    cred_id = _b64url(verification.credential_id)
    if session.get(PasskeyCredential, cred_id) is not None:
        raise HTTPException(status_code=409, detail="credential already registered")

    session.add(
        PasskeyCredential(
            credential_id=cred_id,
            user_id=user.user_id,
            public_key=_b64url(verification.credential_public_key),
            sign_count=verification.sign_count,
            label=body.label or user.email,
        )
    )
    session.delete(challenge)
    session.commit()

    return {"ok": True, "credential_id": cred_id, "label": body.label or user.email}


@router.get("/credentials")
def list_credentials(
    user: AuthedUser = Depends(require_authed_user),
    session: Session = Depends(get_session),
) -> dict:
    rows = session.exec(
        select(PasskeyCredential)
        .where(PasskeyCredential.user_id == user.user_id)
        .order_by(PasskeyCredential.created_at.desc())
    ).all()
    return {
        "credentials": [
            {
                "credential_id": c.credential_id,
                "label": c.label,
                "created_at": c.created_at.isoformat(),
                "last_used_at": c.last_used_at.isoformat() if c.last_used_at else None,
            }
            for c in rows
        ]
    }


@router.delete("/credentials/{credential_id}")
def delete_credential(
    credential_id: str,
    user: AuthedUser = Depends(require_authed_user),
    session: Session = Depends(get_session),
) -> dict:
    cred = session.get(PasskeyCredential, credential_id)
    if cred is None or cred.user_id != user.user_id:
        raise HTTPException(status_code=404, detail="credential not found")
    session.delete(cred)
    session.commit()
    return {"ok": True}


# --- Login (public, returns a Supabase magic-link hashed_token) ---------------


@router.post("/login/begin")
def login_begin(session: Session = Depends(get_session)) -> dict:
    """Discoverable credential flow. Any passkey scoped to our RP id is a
    candidate; the browser picks one and returns it to /login/complete."""
    _purge_stale_challenges(session)

    options = generate_authentication_options(
        rp_id=_rp_id(),
        user_verification=UserVerificationRequirement.PREFERRED,
    )

    challenge_id = secrets.token_urlsafe(16)
    session.add(
        PasskeyChallenge(
            id=challenge_id,
            challenge=_b64url(options.challenge),
            kind="login",
        )
    )
    session.commit()

    return {
        "challenge_id": challenge_id,
        "options": json.loads(options_to_json(options)),
    }


class LoginCompleteBody(BaseModel):
    challenge_id: str
    credential: dict


@router.post("/login/complete")
def login_complete(
    body: LoginCompleteBody, session: Session = Depends(get_session)
) -> dict:
    challenge = session.get(PasskeyChallenge, body.challenge_id)
    if challenge is None or challenge.kind != "login":
        raise HTTPException(status_code=400, detail="unknown or expired challenge")
    if (datetime.utcnow() - challenge.created_at).total_seconds() > CHALLENGE_TTL_SECONDS:
        session.delete(challenge)
        session.commit()
        raise HTTPException(status_code=400, detail="challenge expired")

    raw_cred_id = body.credential.get("id")
    if not raw_cred_id:
        raise HTTPException(status_code=400, detail="missing credential id")
    stored = session.get(PasskeyCredential, raw_cred_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="credential not registered")

    try:
        verification = verify_authentication_response(
            credential=AuthenticationCredential.parse_raw(json.dumps(body.credential)),
            expected_challenge=_b64url_decode(challenge.challenge),
            expected_rp_id=_rp_id(),
            expected_origin=_origin(),
            credential_public_key=_b64url_decode(stored.public_key),
            credential_current_sign_count=stored.sign_count,
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"assertion failed: {exc}")

    stored.sign_count = verification.new_sign_count
    stored.last_used_at = datetime.utcnow()
    session.add(stored)
    session.delete(challenge)
    session.commit()

    # We need the user's email to mint the magic link. Read it from the
    # profile (set at signup) or fall back to the stored credential label,
    # which we captured at registration.
    from app.models import Profile

    profile = session.get(Profile, stored.user_id)
    email = (profile.email if profile else None) or stored.label
    if not email:
        raise HTTPException(status_code=500, detail="credential has no email on file")

    link = _generate_supabase_magic_link(email)
    hashed_token = (
        link.get("properties", {}).get("hashed_token")
        or link.get("hashed_token")
    )
    if not hashed_token:
        raise HTTPException(
            status_code=502, detail="supabase did not return a hashed_token"
        )

    return {
        "email": email,
        "token_hash": hashed_token,
        "verification_type": "magiclink",
    }
