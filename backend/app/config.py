from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BABEL_", env_file=".env", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8765

    data_dir: Path = Path("./jobs")
    uploads_dir: Path = Path("./uploads")
    outputs_dir: Path = Path("./outputs")
    sqlite_path: Path = Path("./jobs/babel.sqlite")

    model_adapter: str = "llamacpp"
    llamacpp_host: str = "127.0.0.1"
    llamacpp_port: int = 8080
    llamacpp_model: str = "translategemma-4b-it.Q4_K_M.gguf"

    source_lang: str = "en"
    target_lang: str = "es"
    chunk_tokens: int = 1500
    # Default 0: chunks do not share source text, so the assembled output
    # contains no duplicated sentences. Cross-chunk coherence is instead
    # provided by feeding the previous chunk's translated tail as context
    # (see services/translate.py). Set >0 only if you want belt-and-braces.
    chunk_overlap: int = 0
    # Characters of the previous chunk's translated output to feed the
    # adapter as "previous passage" context (not re-translated).
    context_chars: int = 600

    # Watchdog — mark TRANSLATING jobs as FAILED when no chunk has progressed
    # in this many minutes. Sweep runs every watchdog_interval_seconds.
    watchdog_stuck_minutes: int = 10
    watchdog_interval_seconds: int = 60

    # Admin gate — shared pass-code required on X-Admin-Code header to call
    # any /admin/* route. Empty (default) disables admin endpoints entirely
    # so a misconfigured deploy can't leak them.
    admin_code: str = ""

    # Worker auth — bearer token required by /api/worker/* endpoints.
    # Empty disables the worker endpoints entirely (safest default).
    worker_token: str = ""

    # In-process queue worker. Convenient locally (./dev.sh runs backend +
    # llama-server on one machine) but pointless on Fly (no llama-server).
    # Default off on cloud; flip to 1 in your local .env.
    inproc_worker: bool = False

    # Queue — admin controls whether new jobs go straight to QUEUED or wait
    # for manual admin approval.
    queue_mode: str = "auto"  # "auto" | "manual"
    # Time between queue-worker sweeps (picks next QUEUED job and runs it).
    queue_interval_seconds: int = 3

    # Non-admin hard caps. Set generously so we can honestly pitch "no
    # page caps" — these beat DeepL (10 MB), BookTranslator.ai (50 MB
    # EPUB, ~100k words), and Google Translate (10 MB). Still bounded so
    # 3 × 100 MB = 300 MB fits Supabase's free tier (1 GB) with headroom
    # for translated outputs, and 3 × 500k words ≈ 12 h of M-series
    # drain-time (one overnight session).
    max_upload_mb_nonadmin: int = 100       # heavy scanned PDFs OK
    max_word_count_nonadmin: int = 500000   # handles War and Peace (587k is the rare outlier)
    max_documents_nonadmin: int = 3         # concurrency knob — queue serializes
    # How long to keep documents/chunks before purge (admin-only purge for now).
    retention_days: int = 7

    # Optional Sentry DSN. If set, initialized in main.py lifespan.
    sentry_dsn: str = ""

    # --- Cloud mode (leave empty to stay fully local) ---
    # If set, overrides the SQLite path. Typical value:
    #   postgresql://postgres:<pw>@db.<ref>.supabase.co:5432/postgres?sslmode=require
    database_url: str = ""

    # Supabase Storage — leave empty to write files to local disk instead.
    supabase_url: str = ""
    supabase_service_key: str = ""
    storage_bucket: str = "babel"

    # --- Auth (Supabase) ---
    # Supabase's project JWT secret. Used to verify Authorization: Bearer
    # <jwt> sent by the frontend. Empty = auth disabled (guest-only mode).
    supabase_jwt_secret: str = ""

    # Free-tier words each anonymous session gets before we gate on sign-in.
    guest_trial_words: int = 5000
    # Words an authed user gets the first time we see them (0 for paid-only).
    signup_bonus_words: int = 0

    # --- Billing (Stripe) ---
    # Secret key for server-side calls. Empty = billing disabled.
    stripe_secret_key: str = ""
    # Webhook signing secret from the Stripe dashboard → webhooks.
    stripe_webhook_secret: str = ""
    # Success/cancel URLs for Stripe Checkout. Set to babeltower.lat in prod.
    stripe_success_url: str = "http://127.0.0.1:3838/app/billing?status=ok"
    stripe_cancel_url: str = "http://127.0.0.1:3838/app/billing?status=cancel"

    # --- Passkey / WebAuthn ---
    # Relying Party id = the domain passkeys are scoped to. Prod: babeltower.lat.
    passkey_rp_id: str = "localhost"
    # Origins allowed on registration/assertion — comma-separated so we can
    # authorize apex + Vercel preview URLs together.
    passkey_origin: str = "http://127.0.0.1:3838,http://localhost:3838"

    # Separate secret used to sign babel-minted JWTs (passkey sessions).
    # Rotating this doesn't invalidate Supabase tokens and vice versa.
    # Falls back to supabase_jwt_secret if empty so local dev can stay slim.
    babel_jwt_secret: str = ""

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.uploads_dir, self.outputs_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
