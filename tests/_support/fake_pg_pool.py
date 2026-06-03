"""In-memory PostgreSQL pool stub for tests without a live DATABASE_URL."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


class _FakeCursor:
    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, *_args: object, **_kwargs: object) -> None:
        return None

    def fetchone(self) -> None:
        return None

    def fetchall(self) -> list[Any]:
        return []


class _FakeConnection:
    def cursor(self, *_args: object, **_kwargs: object) -> _FakeCursor:
        return _FakeCursor()

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


class FakePgPool:
    def close(self) -> None:
        return None

    @contextmanager
    def connection(self) -> Iterator[_FakeConnection]:
        yield _FakeConnection()


def install_fake_pg_pool(monkeypatch: Any, *, target: str = "storage.pg_pool.get_pool") -> FakePgPool:
    """Route ``get_pool()`` to an in-memory stub without replacing the function object.

    Do **not** monkeypatch ``get_pool`` itself: modules such as ``rag.pg_chunks`` bind
    ``from storage.pg_pool import get_pool`` at import time; swapping the function leaves
    stale lambdas that keep returning ``FakePgPool`` after pytest teardown and break
    subsequent ``@pytest.mark.pg`` suites (ingest reports chunks while PG stays empty).
    """
    del monkeypatch, target  # keep signature for existing callers
    import storage.pg_pool as pg_mod

    pg_mod.reset_pg_pool_for_tests()
    pool = FakePgPool()
    pg_mod._pool = pool
    return pool
