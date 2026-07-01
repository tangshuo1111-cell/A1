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

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

PYTEST_TEMP_ROOT = PROJECT_ROOT / "_local" / "temp" / "pytest"
PYTEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)

# 必须在 import config.settings 之前写入（pg_fixtures 会触发 settings 单例）。
sys.dont_write_bytecode = True
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
os.environ["TMP"] = str(PYTEST_TEMP_ROOT)
os.environ["TEMP"] = str(PYTEST_TEMP_ROOT)
os.environ["TMPDIR"] = str(PYTEST_TEMP_ROOT)
# 不在此处 default 真实业务库 URL；@pytest.mark.pg 用例由 CI/workflow 或
# PYTEST_DATABASE_URL / DATABASE_URL 注入。默认走 fake_pg（见 _fake_pg_unless_marked）。
os.environ.setdefault("RAG_HYBRID", "0")
os.environ["USE_LLM_ROUTER"] = "0"
os.environ.setdefault("ENABLE_ANSWER_CRITIC", "0")
os.environ.setdefault("EMBEDDING_ENABLED", "0")
os.environ.setdefault("RETRIEVAL_MODE", "auto")
os.environ.setdefault("ENABLE_WEB_SEARCH", "0")
os.environ.setdefault("CHECKPOINT_BACKEND", "memory")
os.environ.setdefault("RUNTIME_DB_MEMORY", "1")
os.environ.setdefault("RATE_LIMIT_CHAT", "10000/minute")

import pytest

# 让 `pg_settings` 作为全局 fixture 可被各 @pytest.mark.pg 用例直接以参数引用，
# 测试文件无需再 import（避免 F401/F811）。
from tests._support.pg_fixtures import pg_settings  # noqa: E402,F401

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
    from workers.entry.worker_bootstrap import reset_all_workers_for_tests

    reset_all_workers_for_tests()
    reset_pg_pool_for_tests()
    if not request.node.get_closest_marker("pg"):
        from tests._support.fake_pg_pool import install_fake_pg_pool

        install_fake_pg_pool(monkeypatch)
    yield
    reset_all_workers_for_tests()
    reset_pg_pool_for_tests()


@pytest.fixture(autouse=True)
def _block_real_ytdlp_network_in_default_tests(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail fast if a default test leaks into the real yt-dlp network path.

    Tests that intentionally exercise real external services must opt in via
    ``@pytest.mark.real_external`` and are exempt from this guard.
    """
    if request.node.get_closest_marker("real_external"):
        return

    def _blocked_extract_info(url: str, *, ydl_opts: dict[str, object]):
        del ydl_opts
        raise AssertionError(
            f"real yt-dlp network path is blocked in default tests: {url}. "
            "Patch the canonical video boundary instead."
        )

    monkeypatch.setattr(
        "video.url_fetch_ytdlp._yt_dlp_extract_info",
        _blocked_extract_info,
    )


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
