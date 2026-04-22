"""Credit gate + decrement + ledger integrity."""
from __future__ import annotations

import pytest
from sqlmodel import Session

from app.config import settings
from app.models import CreditLedger, Document, Job, JobStatus, Profile
from app.services import credits as credits_svc


@pytest.fixture
def base_doc(session_factory) -> int:
    with session_factory() as s:
        doc = Document(
            filename="a.pdf",
            mime_type="application/pdf",
            size_bytes=1,
            word_count=1000,
            token_count=1300,
            stored_path="x",
            owner_id="u-1",
        )
        s.add(doc)
        s.commit()
        s.refresh(doc)
        return doc.id


def test_authed_user_charged_on_done(session_factory, base_doc):
    with session_factory() as s:
        s.add(Profile(user_id="u-1", credits_balance=5000))
        s.commit()
        job = Job(
            document_id=base_doc,
            status=JobStatus.DONE,
            source_lang="en",
            target_lang="es",
            model_adapter="llamacpp",
            model_name="x",
        )
        s.add(job)
        s.commit()
        s.refresh(job)
        doc = s.get(Document, base_doc)
        profile = s.get(Profile, "u-1")
        credits_svc.charge_for_job(s, job, profile, guest_session_id=None)

        profile = s.get(Profile, "u-1")
        assert profile.credits_balance == 4000
        assert profile.credits_used == 1000
        ledger = s.query(CreditLedger).filter_by(user_id="u-1").all() if False else None  # noqa
        from sqlmodel import select

        entries = s.exec(select(CreditLedger).where(CreditLedger.user_id == "u-1")).all()
        assert len(entries) == 1
        assert entries[0].delta == -1000
        assert entries[0].reason == "job_consume"


def test_guest_trial_bucket(monkeypatch):
    monkeypatch.setattr(settings, "guest_trial_words", 3000)
    credits_svc._GUEST_USAGE.clear()
    assert credits_svc.guest_remaining("sess-A") == 3000
    credits_svc.guest_consume("sess-A", 500)
    assert credits_svc.guest_remaining("sess-A") == 2500
    # Other sessions are isolated.
    assert credits_svc.guest_remaining("sess-B") == 3000


def test_available_credits_dispatches(monkeypatch, session_factory):
    monkeypatch.setattr(settings, "guest_trial_words", 1000)
    credits_svc._GUEST_USAGE.clear()
    with session_factory() as s:
        p = Profile(user_id="u-9", credits_balance=4200)
        s.add(p)
        s.commit()
        s.refresh(p)
        assert credits_svc.available_credits(p, guest_session_id=None) == 4200
    assert credits_svc.available_credits(None, guest_session_id="sess-X") == 1000
    assert credits_svc.available_credits(None, guest_session_id=None) == 0
