"""
测试约定（G-023）
================
- **新测试** 不再使用 `test_vXXrY_` 版本号前缀命名。
  请按功能/层级命名：`test_<module>_<behavior>.py` 或 `test_<feature>_<scenario>.py`。
- **历史测试**（`test_v6_*` ~ `test_v17r*`）保留原名不重命名（避免 diff 噪声），
  但其 docstring 应标明"该测试属于哪个验收版本的历史用例"。
- 测试分类目标（逐步迁移，非一次性）：
  - `tests/unit/`        纯函数 / 模块级
  - `tests/integration/` 跨模块 / 需要 mock IO
  - `tests/e2e/`         端到端（需要后端启动或 LLM key）
  - `tests/acceptance/`  业务验收断言
"""

import os
import shutil
import sys
import types
from pathlib import Path

import pytest

# 让 `pg_settings` 作为全局 fixture 可被各 @pytest.mark.pg 用例直接以参数引用，
# 测试文件无需再 import（避免 F401/F811）。
from tests._support.pg_fixtures import pg_settings  # noqa: E402,F401

# Keep pytest imports from writing __pycache__ into the source tree.
sys.dont_write_bytecode = True

PROJECT_ROOT = Path(__file__).resolve().parents[1]

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
# 默认集成测 / 需 PG 的用例：本地请先启动 PostgreSQL，或与 docker-compose 中账号一致。
# CI 在 workflow 中覆盖为 services.postgres 主机名。主链以 PostgreSQL 为准。
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://light_maqa:light_maqa_dev@127.0.0.1:5432/light_maqa",
)
os.environ.setdefault("RAG_HYBRID", "0")
os.environ.setdefault("USE_LLM_ROUTER", "0")
os.environ.setdefault("ENABLE_ANSWER_CRITIC", "0")
os.environ.setdefault("EMBEDDING_ENABLED", "0")
# 默认测试基线与业务口径对齐：统一请求 auto，
# 再由 auto 在 embedding 关闭时稳定回退到 keyword。
os.environ.setdefault("RETRIEVAL_MODE", "auto")
os.environ.setdefault("ENABLE_WEB_SEARCH", "0")
os.environ.setdefault("CHECKPOINT_BACKEND", "memory")
os.environ.setdefault("RUNTIME_DB_MEMORY", "1")
os.environ.setdefault("RATE_LIMIT_CHAT", "10000/minute")

if os.environ.get("ALLOW_REAL_SENTENCE_TRANSFORMERS", "").lower() not in {"1", "true", "yes", "on"}:
    fake_sentence_transformers = types.ModuleType("sentence_transformers")

    class _SentenceTransformerUnavailable:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("SentenceTransformer is disabled in default tests")

    fake_sentence_transformers.SentenceTransformer = _SentenceTransformerUnavailable
    sys.modules.setdefault("sentence_transformers", fake_sentence_transformers)


def pytest_configure(config: pytest.Config) -> None:
    """Register suite markers."""
    for line in [
        "smoke: fast smoke coverage for default path and critical chains",
        "acceptance: business acceptance / end-to-end assertion suites",
        "real_external: tests that talk to real paid or external services when gates are enabled",
        "pg: requires PostgreSQL (DATABASE_URL) or compose stack",
    ]:
        config.addinivalue_line("markers", line)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-tag tests by filename for selective runs."""

    del config
    for item in items:
        name = Path(str(item.fspath)).name
        if "smoke" in name:
            item.add_marker(pytest.mark.smoke)
        if any(token in name for token in ("final", "acceptance", "e2e", "unified", "lifecycle")):
            item.add_marker(pytest.mark.acceptance)
        if (
            name.startswith("test_real_")
            or "real_e2e" in name
            or "tencent" in name
            or "playwright" in name
        ):
            item.add_marker(pytest.mark.real_external)


@pytest.fixture(autouse=True)
def _fake_pg_unless_marked(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Install in-memory PG stub unless the test (or module) is marked ``@pytest.mark.pg``.

    Real-DB suites must use ``tests._support.pg_fixtures.pg_settings`` and ``pg_required_marks``.
    """
    from storage.pg_pool import reset_pg_pool_for_tests

    reset_pg_pool_for_tests()
    if not request.node.get_closest_marker("pg"):
        from tests._support.fake_pg_pool import install_fake_pg_pool

        install_fake_pg_pool(monkeypatch)
    yield
    reset_pg_pool_for_tests()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Keep source directories clean after local/full regression runs."""

    del session, exitstatus
    for pycache_dir in PROJECT_ROOT.rglob("__pycache__"):
        if "_local" in pycache_dir.parts:
            continue
        shutil.rmtree(pycache_dir, ignore_errors=True)
    for pyc_file in PROJECT_ROOT.rglob("*.pyc"):
        if "_local" in pyc_file.parts:
            continue
        pyc_file.unlink(missing_ok=True)
