from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import delete
from sqlmodel import Session, func, select

from app.auth import AuthedUser, require_authed_user
from app.config import settings
from app.db import get_session
from app.deps import OWNER_ADMIN, get_owner_id, is_admin
from app.models import Chunk, Document, GlossaryTerm, Job
from app.services import ingest as ingest_service
from pydantic import BaseModel
from app.services.analyzer import count_tokens
from app.services.langdetect_util import detect_language
from app.services.storage import get_storage

router = APIRouter(prefix="/documents", tags=["documents"])


def _safe_name(original: str) -> str:
    suffix = Path(original).suffix.lower()
    stem = Path(original).stem.replace("/", "_").replace("\\", "_")[:80]
    token = secrets.token_hex(4)
    return f"{stem}-{token}{suffix}"


@router.post("")
async def upload_document(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    admin: bool = Depends(is_admin),
    owner: str = Depends(get_owner_id),
) -> dict:
    original = file.filename or "upload"
    suffix = Path(original).suffix.lower()
    if suffix not in ingest_service.supported_extensions():
        raise HTTPException(
            status_code=400,
            detail=f"unsupported file type {suffix!r}; supported: "
            + ", ".join(ingest_service.supported_extensions()),
        )

    settings.ensure_dirs()
    storage = get_storage()
    stored_name = _safe_name(original)
    storage_key = f"source/{stored_name}"
    data = await file.read()

    # Non-admin total-documents cap, scoped per-owner. Each session gets
    # their own slot allocation so heavy users can't starve out newcomers.
    if not admin:
        doc_count = session.exec(
            select(func.count())
            .select_from(Document)
            .where(Document.owner_id == owner)
        ).one()
        if int(doc_count) >= settings.max_documents_nonadmin:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"upload cap reached for this session: "
                    f"{settings.max_documents_nonadmin} documents. "
                    f"Delete one to free a slot, or wait for the retention "
                    f"window to expire."
                ),
            )

    # Non-admin upload size cap. Admins bypass (they're running the GPU).
    if not admin:
        limit_bytes = settings.max_upload_mb_nonadmin * 1024 * 1024
        if len(data) > limit_bytes:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"file too large ({len(data) // (1024 * 1024)} MB); "
                    f"non-admin limit is {settings.max_upload_mb_nonadmin} MB"
                ),
            )

    storage.put(storage_key, data, content_type=file.content_type)

    try:
        with storage.as_local_path(storage_key) as local_path:
            ingested = ingest_service.ingest(local_path)
    except Exception as e:
        storage.delete(storage_key)
        raise HTTPException(status_code=400, detail=f"ingest failed: {e}") from e

    word_count = ingested.word_count
    token_count = count_tokens(ingested.full_text)
    detected_lang, detected_conf = detect_language(ingested.full_text)

    # Non-admin word-count cap — prevents users from queueing a 500k-word tome.
    if not admin and word_count > settings.max_word_count_nonadmin:
        storage.delete(storage_key)
        raise HTTPException(
            status_code=413,
            detail=(
                f"document too long ({word_count:,} words); non-admin "
                f"limit is {settings.max_word_count_nonadmin:,} words"
            ),
        )

    doc = Document(
        filename=original,
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=len(data),
        page_count=ingested.page_count,
        word_count=word_count,
        token_count=token_count,
        stored_path=storage_key,
        owner_id=owner if owner != OWNER_ADMIN else None,
        detected_lang=detected_lang,
        detected_lang_confidence=detected_conf,
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)

    return {
        "id": doc.id,
        "filename": doc.filename,
        "size_bytes": doc.size_bytes,
        "page_count": doc.page_count,
        "word_count": doc.word_count,
        "token_count": doc.token_count,
        "detected_lang": doc.detected_lang,
        "detected_lang_confidence": doc.detected_lang_confidence,
        "chapters": [
            {"title": c.title, "word_count": c.word_count}
            for c in ingested.chapters
        ],
    }


@router.get("")
def list_documents(
    session: Session = Depends(get_session),
    owner: str = Depends(get_owner_id),
) -> list[dict]:
    stmt = select(Document).order_by(Document.uploaded_at.desc())
    if owner != OWNER_ADMIN:
        stmt = stmt.where(Document.owner_id == owner)
    docs = session.exec(stmt).all()
    return [_serialize(d) for d in docs]


@router.get("/{doc_id}")
def get_document(
    doc_id: int,
    session: Session = Depends(get_session),
    owner: str = Depends(get_owner_id),
) -> dict:
    doc = session.get(Document, doc_id)
    if not doc or not _owned_by(doc, owner):
        # Deliberately 404 rather than 403 so cross-session snooping can't
        # enumerate other people's document ids.
        raise HTTPException(status_code=404, detail="document not found")
    return _serialize(doc)


@router.delete("/{doc_id}")
def delete_document(
    doc_id: int,
    session: Session = Depends(get_session),
    owner: str = Depends(get_owner_id),
) -> dict:
    """Remove a document, its storage blob, and every job + chunk + glossary
    term associated with it. Cascading delete — use with care."""
    doc = session.get(Document, doc_id)
    if not doc or not _owned_by(doc, owner):
        raise HTTPException(status_code=404, detail="document not found")

    # Purge cascading rows first (no DB-level cascade on SQLite).
    job_ids = [
        j.id
        for j in session.exec(select(Job).where(Job.document_id == doc_id)).all()
    ]
    if job_ids:
        session.exec(delete(Chunk).where(Chunk.job_id.in_(job_ids)))
        session.exec(delete(GlossaryTerm).where(GlossaryTerm.job_id.in_(job_ids)))
        session.exec(delete(Job).where(Job.id.in_(job_ids)))

    # Best-effort remove the stored file.
    try:
        get_storage().delete(doc.stored_path)
    except Exception:
        pass  # file already gone / storage transient — keep purging the row

    session.delete(doc)
    session.commit()
    return {"ok": True, "deleted_document_id": doc_id, "deleted_jobs": len(job_ids)}


def _serialize(d: Document) -> dict:
    return {
        "id": d.id,
        "filename": d.filename,
        "size_bytes": d.size_bytes,
        "page_count": d.page_count,
        "word_count": d.word_count,
        "token_count": d.token_count,
        "detected_lang": d.detected_lang,
        "detected_lang_confidence": d.detected_lang_confidence,
        "owner_id": d.owner_id,
        "uploaded_at": d.uploaded_at.isoformat(),
    }


def _owned_by(doc: Document, owner: str) -> bool:
    """True if the caller is admin or owns this document. Legacy NULL-owner
    docs are admin-only."""
    if owner == OWNER_ADMIN:
        return True
    return doc.owner_id is not None and doc.owner_id == owner


class ClaimBody(BaseModel):
    session_id: str


@router.post("/claim")
def claim_guest_documents(
    body: ClaimBody,
    user: AuthedUser = Depends(require_authed_user),
    session: Session = Depends(get_session),
) -> dict:
    """Transfer every document + its jobs from a guest session id to the
    signed-in user. Called by the frontend right after login so the user
    keeps whatever they uploaded before signing up."""
    if not body.session_id or body.session_id == user.user_id:
        return {"ok": True, "claimed": 0}

    docs = session.exec(
        select(Document).where(Document.owner_id == body.session_id)
    ).all()
    for d in docs:
        d.owner_id = user.user_id
        session.add(d)
    session.commit()
    return {"ok": True, "claimed": len(docs)}
