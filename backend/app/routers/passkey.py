"""Passkey / WebAuthn authentication.

Parallel auth system to Supabase. A passkey user is identified by a babel-
generated UUID stored in `passkeycredential.user_id` and carried in a
babel-minted JWT (HS256 with BABEL_JWT_SECRET). The `iss` claim is set to
`babel` so auth.py can tell our tokens apart from Supabase's.

Ceremony:
    1. Client POSTs /passkey/register/begin { email } → server returns
       options (challenge, rp, user, pubKeyCredParams) + a challenge id.
    2. Client runs navigator.credentials.create(options) → WebAuthn prompt.
    3. Client POSTs /passkey/register/complete { challenge_id, response }
       → server verifies attestation, stores credential, mints JWT.
    4. Login is symmetric: /login/begin → navigator.credentials.get →
       /login/complete.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta

import jwt
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
    PublicKeyCredentialDescriptor,
    RegistrationCredential,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.config import settings
from app.db import get_session
from app.models import PasskeyChallenge, PasskeyCredential, Profile

router = APIRouter(prefix="/passkey", tags=["passkey"])


# Challenges expire quickly so a stolen in-flight ceremony can't be replayed.
CHALLENGE_TTL_SECONDS = 300

# JWT lifetime for babel-minted passkey sessions. Short enough to limit
# exposure if a token leaks, long enough that users don't re-auth constantly.
JWT_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days


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


def _babel_jwt_secret() -> str:
    """Separate secret from Supabase's so rotating one doesn't invalidate the
    other. Falls back to the Supabase secret in dev so local .env stays slim."""
    return settings.babel_jwt_secret or settings.supabase_jwt_secret


def _mint_token(user_id: str, email: str | None) -> str:
    now = datetime.utcnow()
    payload = {
        "sub": user_id,
        "email": email,
        "iss": "babel",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=JWT_TTL_SECONDS)).timestamp()),
        "aud": "authenticated",  # match Supabase's audience so auth.py pipeline works
    }
    secret = _babel_jwt_secret()
    if not secret:
        raise HTTPException(status_code=503, detail="passkey jwt secret not configured")
    return jwt.encode(payload, secret, algorithm="HS256")


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


# --- Registration -------------------------------------------------------------


class RegisterBeginBody(BaseModel):
    email: str  # required — used as the user-visible label on the passkey prompt


@router.post("/register/begin")
def register_begin(
    body: RegisterBeginBody, session: Session = Depends(get_session)
) -> dict:
    """Generate WebAuthn registration options. We mint a brand-new user_id
    now and commit to it only after verify — cheap enough that aborted
    ceremonies just leave an orphan user_id in the challenge row."""
    _purge_stale_challenges(session)

    user_id = str(uuid.uuid4())
    options = generate_registration_options(
        rp_id=_rp_id(),
        rp_name=_rp_name(),
        user_id=user_id.encode(),
        user_name=body.email,
        user_display_name=body.email,
        supported_pub_key_algs=[
            COSEAlgorithmIdentifier.ECDSA_SHA_256,
            COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,
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
            user_id=user_id,
            email=body.email,
        )
    )
    session.commit()

    return {
        "challenge_id": challenge_id,
        "options": json.loads(options_to_json(options)),
    }


class RegisterCompleteBody(BaseModel):
    challenge_id: str
    credential: dict  # raw response from navigator.credentials.create
    label: str | None = None


@router.post("/register/complete")
def register_complete(
    body: RegisterCompleteBody, session: Session = Depends(get_session)
) -> dict:
    challenge = session.get(PasskeyChallenge, body.challenge_id)
    if challenge is None or challenge.kind != "register":
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

    # Store credential + ensure a Profile exists for the freshly-minted user.
    cred_id = _b64url(verification.credential_id)
    existing = session.get(PasskeyCredential, cred_id)
    if existing is not None:
        raise HTTPException(status_code=409, detail="credential already registered")

    session.add(
        PasskeyCredential(
            credential_id=cred_id,
            user_id=challenge.user_id,
            public_key=_b64url(verification.credential_public_key),
            sign_count=verification.sign_count,
            label=body.label or challenge.email,
        )
    )

    profile = session.get(Profile, challenge.user_id)
    if profile is None:
        profile = Profile(
            user_id=challenge.user_id,
            email=challenge.email,
            credits_balance=settings.signup_bonus_words,
        )
        session.add(profile)

    session.delete(challenge)
    session.commit()

    token = _mint_token(challenge.user_id, challenge.email)
    return {"access_token": token, "user_id": challenge.user_id, "email": challenge.email}


# --- Login --------------------------------------------------------------------


@router.post("/login/begin")
def login_begin(session: Session = Depends(get_session)) -> dict:
    """Discoverable credential flow — client doesn't need to tell us who they
    are up front. The authenticator surfaces any passkey scoped to our RP id."""
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

    profile = session.get(Profile, stored.user_id)
    email = profile.email if profile else None
    token = _mint_token(stored.user_id, email)
    return {"access_token": token, "user_id": stored.user_id, "email": email}
