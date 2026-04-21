from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture
def memory_engine() -> Iterator:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def session_factory(memory_engine):
    def _factory() -> Session:
        return Session(memory_engine)

    return _factory
