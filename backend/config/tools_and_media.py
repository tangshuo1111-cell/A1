"""工具和媒体处理配置（视频 / ASR / OCR / 搜索 / 文档解析 / V16 开关）。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from ._helpers import (
    _env_bool,
    _env_float,
    _env_int,
    _env_str,
    _resolve_v16_web_search_api_key,
    _resolve_v16_web_search_provider,
)


@dataclass
class ToolsAndMediaSettings:
    """视频链、ASR、OCR、搜索、文档处理的所有配置字段。"""

    # --- 通用工具开关 ---
    enable_tools: bool = field(default_factory=lambda: _env_bool("ENABLE_TOOLS", True))
    enable_web_search: bool = field(
        default_factory=lambda: _env_bool("ENABLE_WEB_SEARCH", True)
    )
    web_search_when_no_link: bool = field(
        default_factory=lambda: _env_bool("WEB_SEARCH_NO_LINK", False)
    )
    http_fetch_timeout_sec: float = field(
        default_factory=lambda: _env_float("HTTP_FETCH_TIMEOUT_SEC", 8.0)
    )

    # --- 视频 URL 链 + 云 ASR ---
    video_url_enabled: bool = field(
        default_factory=lambda: _env_bool("VIDEO_URL_ENABLED", True)
    )
    video_url_domains: str = field(
        default_factory=lambda: _env_str(
            "VIDEO_URL_DOMAINS",
            "bilibili.com,b23.tv,youtube.com,youtu.be,youtube-nocookie.com,"
            "tiktok.com,douyin.com,vm.tiktok.com,twitter.com,x.com,vimeo.com",
        )
    )
    video_tmp_dir: Path = field(
        default_factory=lambda: Path(
            _env_str("VIDEO_TMP_DIR")
            or str(Path(os.environ.get("TEMP") or os.environ.get("TMP") or "/tmp")
                   / "light_maqa_video")
        )
    )
    video_url_fetch_timeout_sec: float = field(
        default_factory=lambda: _env_float("VIDEO_URL_FETCH_TIMEOUT_SEC", 90.0)
    )
    video_max_audio_seconds: int = field(
        default_factory=lambda: _env_int("VIDEO_MAX_AUDIO_SECONDS", 1800)
    )

    # ASR
    asr_enabled: bool = field(
        default_factory=lambda: _env_bool("ASR_ENABLED", True)
    )
    asr_provider: str = field(
        default_factory=lambda: _env_str("ASR_PROVIDER", "dashscope").lower()
        or "dashscope"
    )
    asr_model: str = field(
        default_factory=lambda: _env_str("ASR_MODEL", "paraformer-v2")
        or "paraformer-v2"
    )
    asr_base_url: str = field(
        default_factory=lambda: _env_str("ASR_BASE_URL", "")
    )
    dashscope_api_key: str = field(
        default_factory=lambda: _env_str("DASHSCOPE_API_KEY", "")
    )
    asr_timeout_seconds: float = field(
        default_factory=lambda: _env_float("ASR_TIMEOUT", 120.0)
    )
    asr_max_file_mb: int = field(
        default_factory=lambda: _env_int("ASR_MAX_FILE_MB", 50)
    )

    # --- Cookies ---
    video_cookies_from_browser: str = field(
        default_factory=lambda: _env_str("VIDEO_COOKIES_FROM_BROWSER", "").strip().lower()
    )
    video_cookies_file: str = field(
        default_factory=lambda: _env_str("VIDEO_COOKIES_FILE", "").strip()
    )

    # --- 字幕梳理 ---
    video_tidy_enabled: bool = field(
        default_factory=lambda: _env_bool("VIDEO_TIDY_ENABLED", False)
    )
    video_tidy_model: str = field(
        default_factory=lambda: _env_str("VIDEO_TIDY_MODEL", "")
    )
    video_tidy_max_input_chars: int = field(
        default_factory=lambda: _env_int("VIDEO_TIDY_MAX_INPUT_CHARS", 12000)
    )
    video_tidy_timeout_seconds: float = field(
        default_factory=lambda: _env_float("VIDEO_TIDY_TIMEOUT", 30.0)
    )
    video_tidy_max_retries: int = field(
        default_factory=lambda: _env_int("VIDEO_TIDY_MAX_RETRIES", 0)
    )

    # --- 文档处理上限与工具开关 ---
    v16_max_file_mb: int = field(
        default_factory=lambda: _env_int("V16_MAX_FILE_MB", 20)
    )
    v16_max_pdf_pages: int = field(
        default_factory=lambda: _env_int("V16_MAX_PDF_PAGES", 100)
    )
    v16_max_excel_sheets: int = field(
        default_factory=lambda: _env_int("V16_MAX_EXCEL_SHEETS", 10)
    )
    v16_max_excel_cells: int = field(
        default_factory=lambda: _env_int("V16_MAX_EXCEL_CELLS", 50000)
    )
    v16_max_docx_paragraphs: int = field(
        default_factory=lambda: _env_int("V16_MAX_DOCX_PARAGRAPHS", 2000)
    )
    v16_max_text_chars: int = field(
        default_factory=lambda: _env_int("V16_MAX_TEXT_CHARS", 200000)
    )
    v16_enable_docx: bool = field(
        default_factory=lambda: _env_bool("V16_ENABLE_DOCX", True)
    )
    v16_enable_xlsx: bool = field(
        default_factory=lambda: _env_bool("V16_ENABLE_XLSX", True)
    )
    v16_enable_pdf: bool = field(
        default_factory=lambda: _env_bool("V16_ENABLE_PDF", True)
    )
    v16_enable_local_video: bool = field(
        default_factory=lambda: _env_bool("V16_ENABLE_LOCAL_VIDEO", True)
    )
    v16_enable_web_video: bool = field(
        default_factory=lambda: _env_bool("V16_ENABLE_WEB_VIDEO", True)
    )
    v16_web_video_subtitle_provider: str = field(
        default_factory=lambda: _env_str("V16_WEB_VIDEO_SUBTITLE_PROVIDER", "yt_dlp").strip().lower()
    )
    v16_enable_web_video_automatic_caption: bool = field(
        default_factory=lambda: _env_bool("V16_ENABLE_WEB_VIDEO_AUTOMATIC_CAPTION", True)
    )
    v16_web_video_asr_fallback_max_sec: int = field(
        default_factory=lambda: _env_int("V16_WEB_VIDEO_ASR_FALLBACK_MAX_SEC", 900)
    )
    v16_web_video_asr_abs_max_sec: int = field(
        default_factory=lambda: _env_int("V16_WEB_VIDEO_ASR_ABS_MAX_SEC", 7200)
    )
    v16_enable_web_search: bool = field(
        default_factory=lambda: _env_bool("V16_ENABLE_WEB_SEARCH", True)
    )
    v16_enable_ocr: bool = field(
        default_factory=lambda: _env_bool("V16_ENABLE_OCR", True)
    )
    v16_enable_asr: bool = field(
        default_factory=lambda: _env_bool("V16_ENABLE_ASR", True)
    )
    v16_enable_external_processing: bool = field(
        default_factory=lambda: (
            _env_bool("V16_ENABLE_EXTERNAL_PROCESSING", False)
            if os.environ.get("V16_ENABLE_EXTERNAL_PROCESSING") is not None
            else _env_bool("ENABLE_EXTERNAL_PROCESSING", False)
        )
    )
    v16_enable_paid_ocr: bool = field(
        default_factory=lambda: (
            _env_bool("V16_ENABLE_PAID_OCR", False)
            if os.environ.get("V16_ENABLE_PAID_OCR") is not None
            else _env_bool("ENABLE_PAID_OCR", False)
        )
    )
    v16_enable_paid_asr: bool = field(
        default_factory=lambda: (
            _env_bool("V16_ENABLE_PAID_ASR", False)
            if os.environ.get("V16_ENABLE_PAID_ASR") is not None
            else _env_bool("ENABLE_PAID_ASR", False)
        )
    )
    v16_video_sync_deadline_ms: int = field(
        default_factory=lambda: _env_int("V16_VIDEO_SYNC_DEADLINE_MS", 20000)
    )
    v16_video_probe_budget_ms: int = field(
        default_factory=lambda: _env_int("V16_VIDEO_PROBE_BUDGET_MS", 6000)
    )
    v16_video_probe_timeout_sec: float = field(
        default_factory=lambda: _env_float("V16_VIDEO_PROBE_TIMEOUT_SEC", 12.0)
    )
    v16_video_sync_asr_budget_ms: int = field(
        default_factory=lambda: _env_int("V16_VIDEO_SYNC_ASR_BUDGET_MS", 9000)
    )
    v16_video_target_segment_sec: int = field(
        default_factory=lambda: _env_int("V16_VIDEO_TARGET_SEGMENT_SEC", 120)
    )
    v16_video_max_segment_sec: int = field(
        default_factory=lambda: _env_int("V16_VIDEO_MAX_SEGMENT_SEC", 300)
    )
    v16_video_silence_min_sec: float = field(
        default_factory=lambda: _env_float("V16_VIDEO_SILENCE_MIN_SEC", 0.6)
    )
    v16_video_silence_noise_db: str = field(
        default_factory=lambda: _env_str("V16_VIDEO_SILENCE_NOISE_DB", "-35dB").strip() or "-35dB"
    )
    v16_video_parallel_asr_workers: int = field(
        default_factory=lambda: _env_int("V16_VIDEO_PARALLEL_ASR_WORKERS", 6)
    )
    v16_video_background_workers: int = field(
        default_factory=lambda: _env_int("V16_VIDEO_BACKGROUND_WORKERS", 2)
    )
    v16_video_task_queue_backend: str = field(
        default_factory=lambda: _env_str("V16_VIDEO_TASK_QUEUE_BACKEND", "memory").strip().lower() or "memory"
    )
    v16_video_task_queue_redis_url: str = field(
        default_factory=lambda: _env_str("V16_VIDEO_TASK_QUEUE_REDIS_URL", "").strip()
    )
    v16_video_task_queue_key: str = field(
        default_factory=lambda: _env_str("V16_VIDEO_TASK_QUEUE_KEY", "light_maqa:video_tasks").strip()
    )
    v16_web_video_asr_provider_chain: str = field(
        default_factory=lambda: _env_str("V16_WEB_VIDEO_ASR_PROVIDER_CHAIN", "dashscope,siliconflow").strip()
    )
    v16_local_video_asr_provider_chain: str = field(
        default_factory=lambda: _env_str("V16_LOCAL_VIDEO_ASR_PROVIDER_CHAIN", "dashscope,siliconflow").strip()
    )
    v16_ocr_provider: str = field(
        default_factory=lambda: _env_str("V16_OCR_PROVIDER", "").strip().lower()
    )
    v16_ocr_endpoint: str = field(
        default_factory=lambda: _env_str("V16_OCR_ENDPOINT", "")
    )
    v16_ocr_api_key: str = field(
        default_factory=lambda: _env_str("V16_OCR_API_KEY", "")
    )
    v16_ocr_timeout_sec: float = field(
        default_factory=lambda: _env_float("V16_OCR_TIMEOUT_SEC", 60.0)
    )
    v16_tencent_secret_id: str = field(
        default_factory=lambda: _env_str("V16_TENCENT_SECRET_ID", "")
    )
    v16_tencent_secret_key: str = field(
        default_factory=lambda: _env_str("V16_TENCENT_SECRET_KEY", "")
    )
    v16_tencent_region: str = field(
        default_factory=lambda: _env_str("V16_TENCENT_REGION", "ap-guangzhou")
    )
    v16_tencent_appid: str = field(
        default_factory=lambda: _env_str("V16_TENCENT_APPID", "")
    )
    v16_search_provider: str = field(
        default_factory=lambda: _env_str("V16_SEARCH_PROVIDER", "").strip().lower()
    )
    v16_web_search_provider: str = field(
        default_factory=_resolve_v16_web_search_provider
    )
    v16_web_search_api_key: str = field(
        default_factory=_resolve_v16_web_search_api_key
    )
    v16_web_search_endpoint: str = field(
        default_factory=lambda: _env_str("V16_WEB_SEARCH_ENDPOINT", "")
    )
    v16_web_search_timeout_sec: float = field(
        default_factory=lambda: _env_float("V16_WEB_SEARCH_TIMEOUT_SEC", 15.0)
    )
    v16_max_ocr_cost_per_task: float = field(
        default_factory=lambda: _env_float(
            "V16_OCR_MAX_COST_PER_TASK",
            _env_float("MAX_OCR_COST_PER_TASK", 5.0),
        )
    )
    v16_max_asr_cost_per_task: float = field(
        default_factory=lambda: _env_float(
            "V16_ASR_MAX_COST_PER_TASK",
            _env_float("MAX_ASR_COST_PER_TASK", 5.0),
        )
    )
    v16_asr_provider: str = field(
        default_factory=lambda: _env_str("V16_ASR_PROVIDER", "").strip().lower()
    )
    v16_asr_endpoint: str = field(
        default_factory=lambda: _env_str("V16_ASR_ENDPOINT", "")
    )
    v16_asr_api_key: str = field(
        default_factory=lambda: _env_str("V16_ASR_API_KEY", "")
    )
    v16_asr_timeout_sec: float = field(
        default_factory=lambda: _env_float("V16_ASR_TIMEOUT_SEC", 120.0)
    )
    v16_asr_max_duration_sec: int = field(
        default_factory=lambda: _env_int("V16_ASR_MAX_DURATION_SEC", 0)
    )
    v16_asr_short_threshold_sec: int = field(
        default_factory=lambda: _env_int("V16_ASR_SHORT_THRESHOLD_SEC", 900)
    )
    v16_asr_long_threshold_sec: int = field(
        default_factory=lambda: _env_int("V16_ASR_LONG_THRESHOLD_SEC", 7200)
    )
    v16_asr_max_file_mb: int = field(
        default_factory=lambda: _env_int("V16_ASR_MAX_FILE_MB", 0)
    )
    v16_tencent_asr_engine_model_type: str = field(
        default_factory=lambda: _env_str("V16_TENCENT_ASR_ENGINE_MODEL_TYPE", "16k_zh")
    )
    v16_max_video_duration_sec: int = field(
        default_factory=lambda: _env_int("V16_MAX_VIDEO_DURATION_SEC", 1800)
    )
    v16_max_search_results: int = field(
        default_factory=lambda: _env_int("V16_MAX_SEARCH_RESULTS", 5)
    )
    v16_max_search_query_chars: int = field(
        default_factory=lambda: _env_int("V16_MAX_SEARCH_QUERY_CHARS", 200)
    )
    v16_task_timeout_sec: int = field(
        default_factory=lambda: _env_int("V16_TASK_TIMEOUT_SEC", 120)
    )
