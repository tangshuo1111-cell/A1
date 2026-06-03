from __future__ import annotations

from rag import retriever


class _FakeCursor:
    def __init__(self, rows_by_expr: dict[str, list[dict]], record: list[str]) -> None:
        self._rows_by_expr = rows_by_expr
        self._record = record
        self._rows: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql: str, params: tuple) -> None:
        expr = params[0]
        self._record.append(expr)
        self._rows = list(self._rows_by_expr.get(expr, []))

    def fetchall(self):
        return list(self._rows)


class _FakeConn:
    def __init__(self, rows_by_expr: dict[str, list[dict]], record: list[str]) -> None:
        self._rows_by_expr = rows_by_expr
        self._record = record

    def cursor(self, **kwargs):
        return _FakeCursor(self._rows_by_expr, self._record)


def test_try_ts_pg_merges_hits_from_multiple_candidates(monkeypatch) -> None:
    monkeypatch.setattr(retriever, "_query_tokens", lambda q: ["复杂题", "Agent", "主链"])
    calls: list[str] = []
    rows_by_expr = {
        "原始整句": [{"rowid": 1, "source_id": "s1", "content": "c1", "bm": 0.91}],
        "复杂题": [{"rowid": 2, "source_id": "s2", "content": "c2", "bm": 0.87}],
        "Agent": [{"rowid": 1, "source_id": "s1", "content": "c1", "bm": 0.91}],
        "主链": [{"rowid": 3, "source_id": "s3", "content": "c3", "bm": 0.82}],
    }
    conn = _FakeConn(rows_by_expr, calls)

    rows = retriever._try_ts_pg(conn, "原始整句", top_k=5)

    assert [r["rowid"] for r in rows] == [1, 2, 3]
    assert calls == ["原始整句", "复杂题", "Agent", "主链"]
