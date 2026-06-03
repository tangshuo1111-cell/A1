"""外部工具：失败时返回可恢复结构。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_httpx_client(monkeypatch) -> None:
    """让 httpx.Client 在 post 时失败。"""
    mock_cm = MagicMock()
    mock_inst = MagicMock()
    mock_inst.post.side_effect = ConnectionError("offline")
    mock_cm.__enter__.return_value = mock_inst
    mock_cm.__exit__.return_value = None
    monkeypatch.setattr("httpx.Client", lambda **kw: mock_cm)


def test_web_search_graceful_error(mock_httpx_client) -> None:
    from tools.search.web_search import run_web_search

    recs, code = run_web_search("python tutorial")
    assert code == "http_error"
    assert recs[0].status == "error"
