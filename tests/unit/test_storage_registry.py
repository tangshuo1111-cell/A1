"""存储 registry / 门面对象（委托 store）。"""

from __future__ import annotations

import pytest

from config.settings import settings


def test_storage_backend_kind_is_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    """运行口径：仅存 PostgreSQL；与 ``DATABASE_URL`` 内容无关，类型固定为 postgres。"""
    monkeypatch.setattr(settings, "database_url", None)
    from storage.registry import storage_backend_kind

    assert storage_backend_kind() == "postgres"


@pytest.mark.parametrize("url", ["postgresql://u:p@h:5432/db", "postgres://localhost/mydb", "", None])
def test_storage_backend_kind_constant(url: str | None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "database_url", url)
    from storage.registry import storage_backend_kind

    assert storage_backend_kind() == "postgres"


def test_get_conversation_storage_delegates_append_turn(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "data_dir", tmp_path)

    calls: list[str] = []

    def fake(**kwargs):
        calls.append(kwargs.get("task_id", ""))

    from storage.registry import get_conversation_storage

    sto = get_conversation_storage()
    monkeypatch.setattr("storage.conversation_store.append_turn", fake)
    sto.append_turn(task_id="x1", session_id=None, user_query="q", answer="a")
    assert calls == ["x1"]
