"""Credit accounting.

Guests get a flat trial bucket tracked in-memory per session (good enough
for an anonymous free tier — losing it on restart is fine). Authed users
have a persistent balance in the Profile table.

Flow:
  - enqueue_translate checks `available_credits` vs job word_count and 409s
    if underfunded.
  - mark-done decrements the authed user's balance and writes a ledger row.
  - Guest consumption is not charged (their guest bucket is the cap).
"""

from __future__ import annotations

from datetime import datetime
from threading import Lock

from sqlmodel import Session

from app.config import settings
from app.models import CreditLedger, Job, Profile


# Session-id -> words already consumed this process lifetime. Refilled on
# restart which is intentionally lenient (the free tier is a lead magnet,
# not a revenue product).
_GUEST_USAGE: dict[str, int] = {}
_GUEST_LOCK = Lock()


def guest_remaining(session_id: str) -> int:
    with _GUEST_LOCK:
        used = _GUEST_USAGE.get(session_id, 0)
    return max(0, settings.guest_trial_words - used)


def guest_consume(session_id: str, words: int) -> None:
    with _GUEST_LOCK:
        _GUEST_USAGE[session_id] = _GUEST_USAGE.get(session_id, 0) + words


def available_credits(profile: Profile | None, guest_session_id: str | None) -> int:
    """Unified balance getter. Authed users see their profile balance; guests
    see the remainder of their trial bucket. Admin callers are never passed
    here (they bypass the cap upstream)."""
    if profile is not None:
        return profile.credits_balance
    if guest_session_id:
        return guest_remaining(guest_session_id)
    return 0


def charge_for_job(
    session: Session,
    job: Job,
    profile: Profile | None,
    guest_session_id: str | None,
) -> None:
    """Call after a job transitions to DONE. Decrements the authed user's
    balance + writes a ledger row, or marks the guest's trial bucket."""
    words = _job_words(session, job)
    if words <= 0:
        return

    if profile is not None:
        profile.credits_balance = max(0, profile.credits_balance - words)
        profile.credits_used += words
        profile.updated_at = datetime.utcnow()
        session.add(profile)
        session.add(
            CreditLedger(
                user_id=profile.user_id,
                delta=-words,
                reason="job_consume",
                job_id=job.id,
            )
        )
        session.commit()
        return

    if guest_session_id:
        guest_consume(guest_session_id, words)


def _job_words(session: Session, job: Job) -> int:
    """Word count we charge for. Prefer the document's stored word_count
    (set during ingest/analyze); fall back to 0 so we never over-charge on
    an unknown job."""
    from app.models import Document

    doc = session.get(Document, job.document_id)
    if doc and doc.word_count:
        return int(doc.word_count)
    return 0
