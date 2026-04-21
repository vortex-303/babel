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

    # Queue — admin controls whether new jobs go straight to QUEUED or wait
    # for manual admin approval.
    queue_mode: str = "auto"  # "auto" | "manual"
    # Time between queue-worker sweeps (picks next QUEUED job and runs it).
    queue_interval_seconds: int = 3

    # Non-admin limits.
    max_upload_mb_nonadmin: int = 10
    max_word_count_nonadmin: int = 80000  # ~ one 300-page book
    # How long to keep documents/chunks before purge (admin-only purge for now).
    retention_days: int = 7

    # Optional Sentry DSN. If set, initialized in main.py lifespan.
    sentry_dsn: str = ""

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.uploads_dir, self.outputs_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
