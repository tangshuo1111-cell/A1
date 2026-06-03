"""Shared bootstrap helpers for historical acceptance tests.

Goal:
- avoid repeating repo-root / sys.path boilerplate in large historical suites
- keep environment defaults explicit and consistent
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path


def find_repo_root(file: str) -> Path:
    """Find the repository root by walking upward to ``pyproject.toml``.

    This lets tests move into nested folders like ``tests/smoke`` without
    rewriting every historical ``parents[N]`` assumption.
    """

    current = Path(file).resolve()
    for parent in (current.parent, *current.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    raise RuntimeError(f"Could not locate repo root from {file}")


def bootstrap_historical_test(
    file: str,
    *,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Return repo root and apply shared sys.path / env defaults.

    Historical tests often live at ``tests/test_vXX...`` and previously repeated
    their own root detection and environment setup. This helper keeps that
    bootstrap consistent without changing test semantics.
    """

    repo_root = find_repo_root(file)
    backend_root = repo_root / "backend"
    text = str(backend_root)
    if text not in sys.path:
        sys.path.insert(0, text)

    defaults = {
        "ENABLE_RAG": "1",
        "EMBEDDING_ENABLED": "0",
        # 与运行时统一：测试默认请求 auto，再由 auto 回退到 keyword。
        "RETRIEVAL_MODE": "auto",
        "USE_LLM_ROUTER": "0",
    }
    if env:
        defaults.update({k: str(v) for k, v in env.items()})
    for key, value in defaults.items():
        os.environ.setdefault(key, value)
    return repo_root
