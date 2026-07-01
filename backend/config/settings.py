"""集中配置层：所有启动项从环境变量读取（可辅以项目根 .env）。

协作：全项目通过 `from config.settings import settings` 访问；禁止业务模块直接 os.getenv。
拆分结构：
- _helpers.py         : .env 加载 + 工具函数
- ai_model.py         : LLM 相关字段
- tools_and_media.py  : 视频/ASR/OCR/搜索/文档工具字段
- search_and_storage.py : 检索/存储/上下文字段
- settings.py (本文件)  : 组合 + app 基础字段 + 方法 + 单例
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from ._helpers import _candidate_env_file_value, _env_bool, _env_int, _env_opt_str, _env_str, _root
from .ai_model import AiModelSettings
from .search_and_storage import SearchAndStorageSettings
from .tools_and_media import ToolsAndMediaSettings


def bundled_fallback_video_cookies_path() -> Path:
    """仓库内随代码提供的样例 cookies。"""
    return _root() / "data" / "cookies" / "video_cookies.txt"


def _bool_from_text(value: str | None) -> bool | None:
    if value is None:
        return None
    return str(value).strip().lower() not in ("0", "false", "no", "off", "")


@dataclass
class Settings(AiModelSettings, SearchAndStorageSettings, ToolsAndMediaSettings):
    """全局设置单例：通过多继承组合三个领域配置，外部访问方式不变。"""

    project_root: Path = field(default_factory=_root)
    app_env: str = field(default_factory=lambda: (_env_str("APP_ENV", "dev").lower() or "dev"))

    enable_mcp: bool = field(default_factory=lambda: _env_bool("ENABLE_MCP", True))
    mcp_use_stdio: bool = field(
        default_factory=lambda: _env_bool("USE_MCP_STDIO", False)
    )
    mcp_stdio_module: str = field(
        default_factory=lambda: _env_str("MCP_STDIO_MODULE", "mcp_servers.min_server")
        or "mcp_servers.min_server"
    )

    api_host: str = field(default_factory=lambda: _env_str("API_HOST", "127.0.0.1"))
    api_port: int = field(default_factory=lambda: _env_int("API_PORT", 8000))

    log_level: str = field(
        default_factory=lambda: _env_str("LOG_LEVEL", "INFO").upper()
    )

    admin_api_key: str | None = field(
        default_factory=lambda: _env_opt_str("ADMIN_API_KEY")
    )

    # 非空时：除 /health、/docs、/openapi.json、/redoc（及 /docs/* 静态）外须带 Bearer
    api_bearer_token: str | None = field(
        default_factory=lambda: _env_opt_str("API_BEARER_TOKEN")
    )

    rate_limit_chat: str = field(
        default_factory=lambda: _env_str("RATE_LIMIT_CHAT", "120/minute")
    )
    rate_limit_storage_uri: str | None = field(
        default_factory=lambda: _env_str("RATE_LIMIT_STORAGE_URI", "") or None
    )
    max_chat_body_bytes: int = field(
        default_factory=lambda: _env_int("MAX_CHAT_BODY_BYTES", 262144)
    )
    cors_origins: str = field(default_factory=lambda: _env_str("CORS_ORIGINS"))
    async_worker_threads: int = field(
        default_factory=lambda: _env_int("ASYNC_WORKER_THREADS", 4)
    )
    task_result_ttl_seconds: int = field(
        default_factory=lambda: _env_int("TASK_RESULT_TTL_SECONDS", 604800)
    )

    # ------------------------------------------------------------------
    # 方法
    # ------------------------------------------------------------------
    def runtime_db_path(self) -> Path:
        return self.data_dir / self.runtime_db_name

    def knowledge_db_path(self) -> Path:
        return self.data_dir / self.knowledge_db_name

    def conversation_db_path(self) -> Path:
        return self.data_dir / self.conversation_db_name

    def knowledge_samples_dir(self) -> Path:
        preferred = self.project_root / "data" / "samples" / "knowledge"
        if preferred.is_dir():
            return preferred
        return self.project_root / "knowledge_samples"

    @property
    def llm_effective_for_router(self) -> bool:
        """是否具备对主路由发起一次 chat.completions 的条件。"""
        if not self.use_llm_router:
            return False
        if not self.openai_api_key:
            return False
        prov = (self.llm_provider or "").strip().lower()
        return prov in ("", "openai", "openai_compatible")

    def video_url_domain_set(self) -> frozenset[str]:
        """把逗号分隔的 VIDEO_URL_DOMAINS 解析为小写域名集合。"""
        raw = self.video_url_domains or ""
        items = (s.strip().lower().lstrip(".") for s in raw.split(","))
        return frozenset(s for s in items if s)

    def asr_effective_base_url(self, provider: str | None = None) -> str:
        """ASR 基础 URL：显式 ASR_BASE_URL 优先；为空时按 provider 推导。

        provider 显式传入时优先于 self.asr_provider —— 供 provider 链 fallback
        （如 dashscope→siliconflow）按"实际正在尝试的 provider"取对正确域名，
        避免 fallback 仍用 .env 默认 provider 的域名而打错门。
        """
        prov = (provider or self.asr_provider or "").strip().lower()
        # 仅当未显式指定 provider 时，才让 ASR_BASE_URL 覆盖（保持旧行为）。
        if provider is None and self.asr_base_url:
            return self.asr_base_url
        if prov == "dashscope":
            # DashScope 的 OpenAI 兼容端点在 /compatible-mode/v1（不是 /api/v1）。
            return "https://dashscope.aliyuncs.com/compatible-mode/v1"
        if prov == "siliconflow":
            return "https://api.siliconflow.cn/v1"
        if prov in ("openai", "openai_whisper"):
            return "https://api.openai.com/v1"
        if self.asr_base_url:
            return self.asr_base_url
        return self.openai_base_url or "https://api.openai.com/v1"

    @property
    def asr_effective(self) -> bool:
        """是否具备调用云 ASR 的条件。"""
        if not self.asr_enabled:
            return False
        prov = (self.asr_provider or "").strip().lower()
        if prov == "dashscope":
            return bool(self.dashscope_api_key)
        if not self.openai_api_key:
            return False
        return prov in ("siliconflow", "openai", "openai_whisper", "")

    _YT_DLP_COOKIE_BROWSERS: frozenset[str] = frozenset({
        "chrome", "chromium", "brave", "opera",
        "edge", "vivaldi", "firefox", "safari", "whale",
    })

    _MANAGED_COOKIES_RELPATH: tuple[str, str] = ("cookies", "video_cookies.txt")

    def _managed_cookies_path(self) -> Path:
        return self.data_dir.joinpath(*self._MANAGED_COOKIES_RELPATH)

    def video_cookies_choice(self) -> tuple[str, str]:
        """决定本轮 yt-dlp 用哪种 cookies 源。返回 (kind, value)。"""
        from pathlib import Path as _P

        bro = (self.video_cookies_from_browser or "").strip().lower()
        if bro and bro in self._YT_DLP_COOKIE_BROWSERS:
            return ("browser", bro)

        cf = (self.video_cookies_file or "").strip()
        if cf:
            try:
                if _P(cf).is_file():
                    return ("file", str(_P(cf).resolve()))
            except (OSError, ValueError):
                pass

        try:
            managed = self._managed_cookies_path()
            if managed.is_file():
                return ("file", str(managed.resolve()))
        except (OSError, ValueError):
            pass

        return ("none", "")

    def fake_llm_env_file_value(self) -> bool | None:
        return _bool_from_text(_candidate_env_file_value("LIGHT_MAQA_FAKE_LLM"))

    def fake_llm_process_env_value(self) -> bool | None:
        import os

        raw = os.environ.get("LIGHT_MAQA_FAKE_LLM")
        return _bool_from_text(raw)

    def fake_llm_source_conflict(self) -> bool:
        file_value = self.fake_llm_env_file_value()
        process_value = self.fake_llm_process_env_value()
        return file_value is not None and process_value is not None and file_value != process_value


settings = Settings()


def _log_embedding_index_state(log: logging.Logger) -> None:
    """EMBEDDING_ENABLED=1 时探活 rag_embeddings，无行则 warn（避免 silent keyword 降级）。"""
    try:
        from storage.pg_pool import get_pool

        with get_pool().connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM rag_embeddings;")
            row = cur.fetchone()
            count = int(row[0]) if row else 0
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "EMBEDDING_ENABLED=1 but rag_embeddings check failed (%s); "
            "auto retrieval may fall back to keyword",
            exc,
        )
        return
    if count <= 0:
        log.warning(
            "EMBEDDING_ENABLED=1 but rag_embeddings has no rows; "
            "auto retrieval will use keyword until chunks are indexed on commit"
        )
    else:
        log.info("embedding index: rag_embeddings rows=%s", count)


def log_runtime_bootstrap() -> None:
    """启动时打印当前模式，便于区分 no-key 与 real-llm。"""
    import logging

    log = logging.getLogger("light_maqa")
    log.info(
        "config: APP_ENV=%s store=%s fake_llm=%s API=%s:%s retrieval=%s embedding=%s",
        settings.app_env, settings.store_backend, settings.fake_llm_enabled,
        settings.api_host, settings.api_port,
        settings.retrieval_mode, settings.embedding_enabled,
    )
    if settings.fake_llm_source_conflict():
        log.warning(
            "fake_llm source conflict: process_env=%s env_file=%s effective=%s",
            settings.fake_llm_process_env_value(),
            settings.fake_llm_env_file_value(),
            settings.fake_llm_enabled,
        )
    if settings.embedding_enabled:
        _log_embedding_index_state(log)
    if settings.llm_effective_for_router:
        log.info("LLM: router model=%s base=%s", settings.llm_router_model, settings.openai_base_url)
    elif not settings.openai_api_key:
        log.info("LLM: no key — rules only")
    elif not settings.use_llm_router:
        log.info("LLM: key present but USE_LLM_ROUTER=0")
    else:
        log.info("LLM: provider=%s unsupported, rules fallback", settings.llm_provider)
