"""配置层公共工具：.env 加载 + 环境变量读取函数。

所有 config/ 下的子配置文件都从这里导入 _env_str/_env_bool/_env_int/_env_float 等工具。
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# 项目根目录与 .env 加载
# ---------------------------------------------------------------------------
_project_root = Path(__file__).resolve().parent.parent.parent


def _candidate_env_files() -> list[Path]:
    """按优先级返回可加载的 .env 路径。"""
    candidates: list[Path] = [_project_root / ".env"]
    for parent in _project_root.parents[:3]:
        candidates.append(parent / ".env")
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        if path not in seen:
            unique.append(path)
            seen.add(path)
    return unique


try:
    from dotenv import load_dotenv

    for _env_file in _candidate_env_files():
        if _env_file.exists():
            load_dotenv(_env_file, override=False)
except ImportError:
    pass


def _root() -> Path:
    return _project_root


# ---------------------------------------------------------------------------
# 环境变量读取工具
# ---------------------------------------------------------------------------
def _env_str(name: str, default: str = "") -> str:
    v = os.environ.get(name)
    return (v.strip() if isinstance(v, str) else "") or default


def _env_opt_str(name: str) -> str | None:
    v = os.environ.get(name)
    if v is None:
        return None
    s = v.strip()
    return s or None


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() not in ("0", "false", "no", "off")


def _env_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    if v is None or not str(v).strip():
        return default
    try:
        return int(str(v).strip(), 10)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    v = os.environ.get(name)
    if v is None or not str(v).strip():
        return default
    try:
        return float(str(v).strip())
    except ValueError:
        return default


def _env_profile() -> str:
    return _env_str("APP_ENV", "dev").lower() or "dev"


# ---------------------------------------------------------------------------
# LLM key/url 解析器（供 ai_model.py 使用）
# ---------------------------------------------------------------------------
def _resolve_llm_api_key() -> str | None:
    """共用一把 key：LLM_API_KEY 优先，兼容旧名 OPENAI_API_KEY。"""
    for key in ("LLM_API_KEY", "OPENAI_API_KEY"):
        v = _env_opt_str(key)
        if v:
            return v
    return None


def _resolve_openai_base_url() -> str:
    return (
        _env_str("LLM_BASE_URL")
        or _env_str("OPENAI_BASE_URL")
        or "https://api.openai.com/v1"
    )


def _resolve_default_llm_model() -> str:
    return _env_str("LLM_MODEL", "gpt-4o-mini") or "gpt-4o-mini"


def _resolve_fast_llm_model() -> str:
    return (
        _env_str("LLM_FAST_MODEL")
        or _env_str("FAST_LLM_MODEL")
        or _resolve_default_llm_model()
    )


def _resolve_router_model() -> str:
    return (
        _env_str("ROUTER_MODEL")
        or _env_str("LLM_ROUTER_MODEL")
        or _resolve_default_llm_model()
    )
