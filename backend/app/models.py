from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class JobStatus(str, Enum):
    UPLOADED = "uploaded"
    ANALYZING = "analyzing"
    AWAITING_GLOSSARY_REVIEW = "awaiting_glossary_review"
    PENDING_APPROVAL = "pending_approval"
    QUEUED = "queued"
    TRANSLATING = "translating"
    REVIEWING = "reviewing"
    ASSEMBLING = "assembling"
    DONE = "done"
    FAILED = "failed"
    REJECTED = "rejected"


class Document(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    filename: str
    mime_type: str
    size_bytes: int
    page_count: int = 0
    word_count: int = 0
    token_count: int = 0
    stored_path: str
    detected_lang: Optional[str] = None
    detected_lang_confidence: Optional[float] = None
    # Phase D0 tenancy: session UUID (from X-Session-ID header) for
    # anonymous users, admin email/identifier for admin uploads, or NULL
    # for legacy pre-D0 rows (visible only to admin).
    owner_id: Optional[str] = Field(default=None, index=True)
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)


class Job(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    document_id: int = Field(foreign_key="document.id")
    status: JobStatus = Field(default=JobStatus.UPLOADED)
    source_lang: str
    target_lang: str
    model_adapter: str
    model_name: str
    chunk_count: int = 0
    translated_chunks: int = 0
    estimated_seconds: Optional[int] = None
    estimated_cost_usd: Optional[float] = None
    error: Optional[str] = None
    # Queue metadata — used to order pending/queued jobs.
    queued_at: Optional[datetime] = None
    priority: int = 0  # higher priority runs first; 0 default
    # Whether this job was submitted by an admin (bypasses approval gate).
    submitted_by_admin: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class Chunk(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="job.id", index=True)
    idx: int
    source_text: str
    translated_text: Optional[str] = None
    reviewed_text: Optional[str] = None
    token_count: int = 0
    translated_at: Optional[datetime] = None


class Profile(SQLModel, table=True):
    """One row per authenticated user. `user_id` is the Supabase
    `auth.users.id` UUID (stored as text). Balance + usage are in words,
    not tokens — the unit we quote to users."""

    user_id: str = Field(primary_key=True)
    email: Optional[str] = None
    credits_balance: int = 0  # remaining words the user can translate
    credits_used: int = 0     # lifetime words translated (for receipts + analytics)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class PasskeyCredential(SQLModel, table=True):
    """One row per registered passkey. A user may register multiple devices;
    each appears here as its own credential.

    `user_id` is the same opaque id carried in Profile.user_id — for
    passkey-only accounts we mint a new UUID at signup; it never collides
    with Supabase Auth UUIDs because we scope them behind an "iss" claim
    in the babel JWT."""

    credential_id: str = Field(primary_key=True)  # base64url of raw credential id
    user_id: str = Field(index=True)
    public_key: str                                # base64url cose key bytes
    sign_count: int = 0
    transports: Optional[str] = None               # csv: "usb,nfc,ble,internal"
    label: Optional[str] = None                    # user-visible name
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_used_at: Optional[datetime] = None


class PasskeyChallenge(SQLModel, table=True):
    """Short-lived nonce issued during register/login ceremonies. Keyed by a
    random id the client echoes back on completion."""

    id: str = Field(primary_key=True)
    challenge: str                                 # base64url bytes
    kind: str                                      # "register" | "login"
    user_id: Optional[str] = None                  # set during register, null during login
    email: Optional[str] = None                    # friendly label captured on register
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CreditLedger(SQLModel, table=True):
    """Immutable audit trail for every credit movement: top-ups from
    Stripe, consumption per completed job, admin grants, refunds. Lets
    support debug any "where did my credits go" question."""

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)
    delta: int                       # +top-up / -consumption
    reason: str                      # "stripe_topup" | "job_consume" | "admin_grant" | ...
    job_id: Optional[int] = Field(default=None, foreign_key="job.id")
    stripe_session_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class GlossaryTerm(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="job.id", index=True)
    source_term: str
    # target_term is None right after extraction, filled in by user (or
    # eventually by an auto-translate pass) before the glossary is injected
    # into translation prompts.
    target_term: Optional[str] = None
    notes: Optional[str] = None
    locked: bool = Field(default=True)
    occurrences: int = 0
