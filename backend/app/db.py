from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from app.config import settings


def _build_engine():
    """Pick Postgres (when BABEL_DATABASE_URL is set) or SQLite (default).

    On cloud deploys point this at Supabase Postgres. Locally we stay on
    SQLite so `./dev.sh` keeps zero-config."""
    url = settings.database_url
    if url:
        # Supabase DSNs sometimes come in with the `postgres://` prefix; the
        # SQLAlchemy/psycopg3 driver wants `postgresql+psycopg://`.
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://") :]
        elif url.startswith("postgresql://") and "+psycopg" not in url:
            url = "postgresql+psycopg://" + url[len("postgresql://") :]
        return create_engine(url, pool_pre_ping=True)
    return create_engine(
        f"sqlite:///{settings.sqlite_path}",
        connect_args={"check_same_thread": False},
    )


engine = _build_engine()


def init_db() -> None:
    settings.ensure_dirs()
    # Safe on Postgres too — checkfirst=True is the default, so this won't
    # fight the Supabase migration files when those exist.
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session


def new_session() -> Session:
    """Open a session detached from FastAPI's dependency lifecycle.

    Use for background tasks that outlive the request."""
    return Session(engine)
