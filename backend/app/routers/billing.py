"""Stripe-backed credit top-ups.

One-time purchases only (no subscriptions). Flow:

  1. Signed-in user clicks a pack on /app/billing
  2. Frontend POSTs /billing/checkout with the pack id
  3. We create a Stripe Checkout session and return the URL
  4. User pays on Stripe-hosted page
  5. Stripe fires `checkout.session.completed` webhook
  6. /billing/webhook verifies the signature and credits the profile

Credits never expire. All top-ups land in CreditLedger for audit.
"""

from __future__ import annotations

from datetime import datetime

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import AuthedUser, require_authed_user, load_or_create_profile
from app.config import settings
from app.db import get_session
from app.models import CreditLedger, Profile


router = APIRouter(prefix="/billing", tags=["billing"])


# Immutable price table. Change prices by adding a new pack and keeping
# the old id around (Stripe receipts reference the id).
PACKS: dict[str, dict] = {
    "starter":  {"words": 50_000,  "price_usd": 5,  "label": "50,000 words"},
    "standard": {"words": 200_000, "price_usd": 15, "label": "200,000 words"},
    "pro":      {"words": 600_000, "price_usd": 40, "label": "600,000 words"},
}

# One-time licenses — distinct SKU from word packs. Buying one stamps a
# boolean on Profile (e.g. self_host_license) rather than adding words.
LICENSES: dict[str, dict] = {
    "self_host": {
        "price_usd": 9,
        "label": "Self-host license (lifetime)",
        "profile_flag": "self_host_license",
        "description": (
            "Run the babel Mac/Linux app on your own GPU. Translate unlimited"
            " documents you own, no per-word charge — you supply the compute."
        ),
    },
}


class CheckoutBody(BaseModel):
    # Accepts either a PACKS id (word top-up) or a LICENSES id (flag purchase).
    pack: str


@router.get("/packs")
def list_packs() -> dict:
    """Public price list for the billing page."""
    return {"packs": PACKS, "licenses": LICENSES}


@router.get("/me")
def me(
    user: AuthedUser = Depends(require_authed_user),
    session: Session = Depends(get_session),
) -> dict:
    profile = load_or_create_profile(session, user)
    return {
        "user_id": profile.user_id,
        "email": profile.email,
        "credits_balance": profile.credits_balance,
        "credits_used": profile.credits_used,
        "self_host_license": profile.self_host_license,
    }


@router.get("/history")
def history(
    user: AuthedUser = Depends(require_authed_user),
    session: Session = Depends(get_session),
    limit: int = 50,
) -> dict:
    """Recent ledger entries so the user can see where credits went."""
    rows = session.exec(
        select(CreditLedger)
        .where(CreditLedger.user_id == user.user_id)
        .order_by(CreditLedger.created_at.desc())
        .limit(limit)
    ).all()
    return {
        "entries": [
            {
                "id": r.id,
                "delta": r.delta,
                "reason": r.reason,
                "job_id": r.job_id,
                "stripe_session_id": r.stripe_session_id,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    }


@router.post("/checkout")
def create_checkout(
    body: CheckoutBody,
    user: AuthedUser = Depends(require_authed_user),
    session: Session = Depends(get_session),
) -> dict:
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=503, detail="billing not configured")

    pack = PACKS.get(body.pack)
    license_item = LICENSES.get(body.pack)
    if pack is None and license_item is None:
        raise HTTPException(status_code=400, detail=f"unknown sku {body.pack!r}")

    item = pack or license_item
    kind = "pack" if pack else "license"

    # Ensure a profile exists so the webhook can credit it later.
    load_or_create_profile(session, user)

    metadata = {
        "user_id": user.user_id,
        "pack": body.pack,
        "kind": kind,
    }
    if pack is not None:
        metadata["words"] = str(pack["words"])
    else:
        metadata["profile_flag"] = license_item["profile_flag"]

    stripe.api_key = settings.stripe_secret_key
    checkout = stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=["card"],
        customer_email=user.email,
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": f"babel — {item['label']}"},
                    "unit_amount": item["price_usd"] * 100,
                },
                "quantity": 1,
            }
        ],
        metadata=metadata,
        success_url=settings.stripe_success_url,
        cancel_url=settings.stripe_cancel_url,
    )
    return {"url": checkout.url, "id": checkout.id}


@router.post("/webhook")
async def webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    session: Session = Depends(get_session),
) -> dict:
    """Stripe sends every payment event here. We only act on
    `checkout.session.completed`. Idempotent via the ledger's
    stripe_session_id lookup."""
    if not settings.stripe_webhook_secret:
        raise HTTPException(status_code=503, detail="webhook not configured")
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="missing signature")

    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, settings.stripe_webhook_secret
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="bad signature")

    if event["type"] != "checkout.session.completed":
        return {"ok": True, "ignored": event["type"]}

    data = event["data"]["object"]
    checkout_id = data.get("id")
    metadata = data.get("metadata") or {}
    user_id = metadata.get("user_id")
    kind = metadata.get("kind") or "pack"
    if not user_id:
        raise HTTPException(status_code=400, detail="bad metadata: missing user_id")

    # Idempotency — if we already processed this checkout, stop.
    existing = session.exec(
        select(CreditLedger).where(CreditLedger.stripe_session_id == checkout_id)
    ).first()
    if existing is not None:
        return {"ok": True, "duplicate": True}

    profile = session.get(Profile, user_id)
    if profile is None:
        profile = Profile(
            user_id=user_id, email=data.get("customer_email"), credits_balance=0
        )

    if kind == "license":
        flag = metadata.get("profile_flag")
        if not flag or not hasattr(profile, flag):
            raise HTTPException(
                status_code=400, detail=f"bad license metadata: {flag!r}"
            )
        setattr(profile, flag, True)
        profile.updated_at = datetime.utcnow()
        session.add(profile)
        session.add(
            CreditLedger(
                user_id=user_id,
                delta=0,
                reason=f"stripe_license:{flag}",
                stripe_session_id=checkout_id,
            )
        )
        session.commit()
        return {"ok": True, "license": flag}

    # Default: word-pack top-up.
    words = int(metadata.get("words") or 0)
    if words <= 0:
        raise HTTPException(status_code=400, detail="bad metadata: words <= 0")
    profile.credits_balance += words
    profile.updated_at = datetime.utcnow()
    session.add(profile)
    session.add(
        CreditLedger(
            user_id=user_id,
            delta=words,
            reason="stripe_topup",
            stripe_session_id=checkout_id,
        )
    )
    session.commit()
    return {"ok": True, "credited": words}
