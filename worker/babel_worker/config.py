from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


@dataclass
class Config:
    backend_url: str
    # Either the shared admin bearer token (BABEL_WORKER_TOKEN) OR a user's
    # Supabase credentials. Exactly one must be set.
    worker_token: str = ""
    supabase_url: str = ""
    supabase_anon_key: str = ""
    user_email: str = ""
    user_password: str = ""

    llama_host: str = "127.0.0.1"
    llama_port: int = 8080
    poll_interval_seconds: float = 5.0
    heartbeat_interval_seconds: float = 30.0
    worker_id: str = ""
    auto_claim: bool = True

    @property
    def uses_supabase_auth(self) -> bool:
        return bool(self.user_email and self.user_password and self.supabase_url)

    @classmethod
    def from_env(cls, config_path: Path | None = None) -> "Config":
        # Config file locations, in order of precedence:
        #   1. explicit --config path
        #   2. ~/.config/babel-worker/config.env (installer writes here)
        #   3. ./babel-worker.env (local dev)
        candidates: list[Path] = []
        if config_path:
            candidates.append(config_path)
        candidates.append(Path.home() / ".config" / "babel-worker" / "config.env")
        candidates.append(Path("babel-worker.env"))
        for c in candidates:
            _load_dotenv(c)

        backend = os.environ.get("BABEL_WORKER_BACKEND_URL", "").rstrip("/")
        token = os.environ.get("BABEL_WORKER_TOKEN", "")
        email = os.environ.get("BABEL_WORKER_EMAIL", "")
        password = os.environ.get("BABEL_WORKER_PASSWORD", "")
        sb_url = os.environ.get(
            "BABEL_SUPABASE_URL", "https://aimfjhjgzacdhxxmjlvf.supabase.co"
        )
        sb_anon = os.environ.get(
            "BABEL_SUPABASE_ANON_KEY",
            "sb_publishable_2PPS16erERoTSVJPGtZrng_MW_RRKm6",
        )

        if not backend:
            raise SystemExit(
                "error: BABEL_WORKER_BACKEND_URL not set. Configure via one of:\n"
                "  export BABEL_WORKER_BACKEND_URL=https://api.babeltower.lat\n"
                "  ~/.config/babel-worker/config.env\n"
                "  ./babel-worker.env"
            )
        if not token and not (email and password):
            raise SystemExit(
                "error: no auth configured. Set either:\n"
                "  BABEL_WORKER_EMAIL + BABEL_WORKER_PASSWORD  (self-host user)\n"
                "or\n"
                "  BABEL_WORKER_TOKEN  (shared admin token)\n"
                "Self-host users: create an account at https://babeltower.lat/app,"
                " buy the self-host license, then paste your email + password here."
            )

        return cls(
            backend_url=backend,
            worker_token=token,
            supabase_url=sb_url.rstrip("/"),
            supabase_anon_key=sb_anon,
            user_email=email,
            user_password=password,
            llama_host=os.environ.get("BABEL_WORKER_LLAMA_HOST", "127.0.0.1"),
            llama_port=int(os.environ.get("BABEL_WORKER_LLAMA_PORT", "8080")),
            poll_interval_seconds=float(
                os.environ.get("BABEL_WORKER_POLL_INTERVAL", "5.0")
            ),
            heartbeat_interval_seconds=float(
                os.environ.get("BABEL_WORKER_HEARTBEAT_INTERVAL", "30.0")
            ),
            worker_id=os.environ.get(
                "BABEL_WORKER_ID", f"worker-{uuid.getnode():012x}"
            ),
            auto_claim=os.environ.get(
                "BABEL_WORKER_AUTO_CLAIM", "true"
            ).lower() in ("1", "true", "yes", "y"),
        )
