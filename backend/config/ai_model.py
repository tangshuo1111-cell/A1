"""AI 模型相关配置（LLM provider / key / model / timeout）。"""

from __future__ import annotations

from dataclasses import dataclass, field

from ._helpers import (
    _env_bool,
    _env_float,
    _env_int,
    _env_opt_str,
    _env_str,
    _resolve_default_llm_model,
    _resolve_fast_llm_model,
    _resolve_llm_api_key,
    _resolve_openai_base_url,
    _resolve_router_model,
)


@dataclass
class AiModelSettings:
    """LLM / Agent 模型字段。"""

    llm_provider: str = field(
        default_factory=lambda: _env_str("LLM_PROVIDER", "openai_compatible").lower()
    )
    openai_api_key: str | None = field(default_factory=_resolve_llm_api_key)
    openai_base_url: str = field(default_factory=_resolve_openai_base_url)
    default_llm_model: str = field(default_factory=_resolve_default_llm_model)
    fast_llm_model: str = field(default_factory=_resolve_fast_llm_model)
    llm_router_model: str = field(default_factory=_resolve_router_model)
    llm_timeout_seconds: float = field(
        default_factory=lambda: _env_float("LLM_TIMEOUT", 60.0)
    )
    llm_max_retries: int = field(default_factory=lambda: _env_int("LLM_MAX_RETRIES", 2))
    use_llm_router: bool = field(
        default_factory=lambda: _env_bool("USE_LLM_ROUTER", True)
    )
    fake_llm_enabled: bool = field(
        default_factory=lambda: _env_bool("LIGHT_MAQA_FAKE_LLM", False)
    )

    middle_llm_model: str | None = field(
        default_factory=lambda: _env_opt_str("MIDDLE_MODEL")
    )
    answer_llm_model: str | None = field(
        default_factory=lambda: _env_opt_str("ANSWER_MODEL")
    )
    critic_llm_model: str | None = field(
        default_factory=lambda: _env_opt_str("CRITIC_MODEL")
    )
