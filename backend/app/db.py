from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from app.config import settings

engine = create_engine(
    f"sqlite:///{settings.sqlite_path}",
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    settings.ensure_dirs()
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session


def new_session() -> Session:
    """Open a session detached from FastAPI's dependency lifecycle.

    Use for background tasks that outlive the request."""
    return Session(engine)
