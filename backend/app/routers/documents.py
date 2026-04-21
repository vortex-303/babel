from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session, select

from app.config import settings
from app.db import get_session
from app.models import Document
from app.services import ingest as ingest_service
from app.services.analyzer import count_tokens

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
    stored_name = _safe_name(original)
    stored_path = settings.uploads_dir / stored_name
    data = await file.read()
    stored_path.write_bytes(data)

    try:
        ingested = ingest_service.ingest(stored_path)
    except Exception as e:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"ingest failed: {e}") from e

    word_count = ingested.word_count
    token_count = count_tokens(ingested.full_text)

    doc = Document(
        filename=original,
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=len(data),
        page_count=ingested.page_count,
        word_count=word_count,
        token_count=token_count,
        stored_path=str(stored_path),
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
        "chapters": [
            {"title": c.title, "word_count": c.word_count}
            for c in ingested.chapters
        ],
    }


@router.get("")
def list_documents(session: Session = Depends(get_session)) -> list[dict]:
    docs = session.exec(select(Document).order_by(Document.uploaded_at.desc())).all()
    return [
        {
            "id": d.id,
            "filename": d.filename,
            "size_bytes": d.size_bytes,
            "page_count": d.page_count,
            "word_count": d.word_count,
            "token_count": d.token_count,
            "uploaded_at": d.uploaded_at.isoformat(),
        }
        for d in docs
    ]


@router.get("/{doc_id}")
def get_document(doc_id: int, session: Session = Depends(get_session)) -> dict:
    doc = session.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")
    return {
        "id": doc.id,
        "filename": doc.filename,
        "size_bytes": doc.size_bytes,
        "page_count": doc.page_count,
        "word_count": doc.word_count,
        "token_count": doc.token_count,
        "uploaded_at": doc.uploaded_at.isoformat(),
    }
