from __future__ import annotations

import re
import time
import uuid
from typing import Any
from urllib.parse import urlparse

import httpx

from application.chat.exit_signals import (
    EXIT_SIGNAL_PRIMARY_PATH,
    pending_kind_signal_from_extra,
    set_material_sufficiency_signal,
    set_mode_signal,
    set_pending_kind_signal,
)
from application.chat.turn_exit_gate import apply_turn_exit_to_chat_turn
from application.chat.turn_facts import TurnFacts
from config.settings import settings
from schemas import ChatTurnResult
from services.capabilities.contracts import CapabilityAdvice

from .budget_clock import SLA_BUDGET_MS, format_ms
from .pending_kind import PendingKind
from .turn_exit_extra import build_common_exit_extra

WEATHER_CITY_MAP: dict[str, tuple[str, float, float]] = {
    "广州": ("广州", 23.1291, 113.2644),
    "北京": ("北京", 39.9042, 116.4074),
    "上海": ("上海", 31.2304, 121.4737),
    "深圳": ("深圳", 22.5431, 114.0579),
    "杭州": ("杭州", 30.2741, 120.1551),
    "成都": ("成都", 30.5728, 104.0668),
    "武汉": ("武汉", 30.5928, 114.3055),
    "南京": ("南京", 32.0603, 118.7969),
    "重庆": ("重庆", 29.5630, 106.5516),
    "西安": ("西安", 34.3416, 108.9398),
    "天津": ("天津", 39.3434, 117.3616),
    "苏州": ("苏州", 31.2989, 120.5853),
}

FAST_BLOCK_TOKENS = (
    "http://", "https://", "知识库", "文档", "文件", "视频", "bilibili", "youtube",
    "查网页", "搜索", "搜一下", "上网", "联网", "总结", "分析", "对比", "保存",
)

LOCAL_TERM_EXPLAINS: dict[str, str] = {
    "cors": "CORS 是浏览器的跨域安全规则：前端想访问另一个域名/端口的后端时，后端必须明确允许。",
    "docker": "Docker 是把程序和运行环境打包到容器里，方便在不同机器上用同一套方式启动。",
    ".env": ".env 是本地环境变量文件，用来放数据库地址、模型 key、工具 key 这类不能写进代码的配置。",
    "env": ".env 是本地环境变量文件，用来放数据库地址、模型 key、工具 key 这类不能写进代码的配置。",
    "bearer": "Bearer 是一种接口鉴权方式：请求头里带上 token，后端确认 token 正确后才放行。",
    "admin key": "Admin Key 是管理接口的专用密钥，作用是避免普通用户调用危险的内部管理能力。",
    "反向代理": "反向代理是挡在后端前面的入口服务，负责把浏览器请求转发给真正的应用服务器。",
    "health check": "Health check 是健康检查接口，用来快速确认后端、数据库等关键组件是否还活着。",
    "ci": "CI 是自动检查代码的流程，通常会在提交后自动跑测试、类型检查和质量检查。",
    "cd": "CD 是自动发布流程，通常负责把通过检查的代码部署到服务器。",
}

FAST_CAPABILITY_WHITELIST: dict[str, tuple[str, ...]] = {
    "video": (
        "capability.video.subtitle_probe",
        "capability.video.short_sync_asr",
        "capability.video.duration_probe",
    ),
    "document": (
        "capability.document.probe",
        "capability.document.parse_quick",
        "capability.document.parse_pdf_quick",
        "capability.document.parse_text_or_table",
        "capability.document.summarize",
    ),
    "web": (
        "capability.web.static_fetch",
        "capability.web.probe",
    ),
    "kb": (
        "capability.kb.probe",
        "capability.kb.retrieve",
        "capability.kb.rerank",
        "capability.kb.grounding",
    ),
    "general": (
        "capability.general.direct_answer",
        "capability.general.canned_answer",
        "capability.general.weather_quick",
        "capability.general.fast_llm",
    ),
}

CROSS_LANE_GENERAL_CAPABILITIES = frozenset({
    "capability.general.fast_llm",
    "capability.general.direct_answer",
})
_KB_COMPLEX_REASON_CODES = frozenset({
    "comparison",
    "cross_material",
    "decision_tradeoff",
    "multi_dimension",
    "multi_analysis",
    "pro_con",
    "solution_design",
})
_KB_COMPLEX_MARKERS = ("对比", "比较", "异同", "优缺点", "路线图", "优先级", "取舍", "分成", "分为", "从", "角度")


def cross_lane_violation_for_capabilities(lane: str, capabilities_called: list[str]) -> bool:
    """True when fast path calls a capability outside the lane whitelist."""
    allowed = set(FAST_CAPABILITY_WHITELIST.get(lane, ()))
    for cap in capabilities_called:
        if cap in allowed or cap in CROSS_LANE_GENERAL_CAPABILITIES:
            continue
        return True
    return False


def weather_city_from_message(message: str) -> tuple[str, str] | None:
    msg = (message or "").strip()
    if "天气" not in msg:
        return None
    for zh, _query in WEATHER_CITY_MAP.items():
        if zh in msg:
            return zh, zh
    m = re.search(r"([\u4e00-\u9fa5]{2,8})(?:今天|明天|现在)?的?天气", msg)
    if m:
        zh = m.group(1)
        return zh, zh
    return None


def weather_desc(code: int | None) -> str:
    if code is None:
        return "天气"
    if code == 0:
        return "晴"
    if code in {1, 2, 3}:
        return "多云"
    if code in {45, 48}:
        return "有雾"
    if code in {51, 53, 55, 56, 57}:
        return "毛毛雨"
    if code in {61, 63, 65, 66, 67, 80, 81, 82}:
        return "有雨"
    if code in {71, 73, 75, 77, 85, 86}:
        return "有雪"
    if code in {95, 96, 99}:
        return "雷阵雨"
    return "天气"


def try_canned_fast_answer(message: str) -> tuple[str, dict[str, Any]] | None:
    msg = (message or "").strip()
    compact = re.sub(r"\s+", "", msg)
    if compact in {"你好", "您好", "hello", "hi", "嗨"}:
        return "你好，我在。你可以直接把问题、链接或资料发过来。", {"fast_path": "local_greeting"}
    if len(compact) <= 20 and any(x in compact for x in ("随便聊", "聊两句", "闲聊", "打个招呼")):
        return "好呀，我在这儿。你想轻松聊点什么，或者继续推进项目，都可以直接开口。", {"fast_path": "local_smalltalk"}
    lower = msg.lower()
    if ("解释" in msg or "什么是" in msg or "一句话" in msg) and len(msg) <= 80:
        for key, answer in LOCAL_TERM_EXPLAINS.items():
            if key in lower or key in msg:
                return answer, {"fast_path": "local_term_explain", "fast_term": key}
    return None


def _needs_structured_fast_answer(message: str) -> bool:
    text = str(message or "").strip()
    if not text:
        return False
    lowered = text.lower()
    markers = (
        "3-5个要点",
        "3~5个要点",
        "3 到 5 个要点",
        "3到5个要点",
        "按 3-5 个要点",
        "按3-5个要点",
        "按3~5个要点",
        "按 3~5 个要点",
        "详细总结",
        "分点总结",
        "按要点",
        "要点总结",
        "结构化总结",
    )
    if any(marker in text for marker in markers):
        return True
    return ("要点" in text and ("总结" in text or "展开" in text)) or ("bullet" in lowered)


def _prefers_structured_web_summary(message: str) -> bool:
    text = str(message or "").strip()
    if not text:
        return False
    return any(marker in text for marker in ("这个网页讲了什么", "这个网页在讲什么", "总结这个网页", "总结一下这个网页", "这个链接讲了什么"))


def _wants_full_web_text(message: str) -> bool:
    text = str(message or "").strip()
    if not text:
        return False
    markers = (
        "全文提取",
        "提取全文",
        "整个网页的全文",
        "网页全文",
        "完整正文",
        "原文提取",
        "把整个网页的全文提取出来",
        "把网页全文提取出来",
    )
    return any(marker in text for marker in markers)


def _extract_page_body_from_material(material: str) -> str:
    text = (material or "").strip()
    if "[网页正文]" not in text or "正文:\n" not in text:
        return ""
    body = text.split("正文:\n", 1)[1]
    if "\n\n[搜索补充]\n" in body:
        body = body.split("\n\n[搜索补充]\n", 1)[0]
    return body.strip()


def run_fast_llm_answer(
    message: str,
    *,
    context_block: str | None = None,
    system_prompt_override: str | None = None,
    max_tokens_override: int | None = None,
) -> str:
    prompt = (message or "").strip()
    if context_block:
        prompt = f"会话摘录：\n{context_block.strip()}\n\n当前用户消息：\n{prompt}"
    wants_structured = _needs_structured_fast_answer(message)
    system_prompt = "你是一个中文轻量助手。用最短可用答案回复，不展开，不寒暄过度。"
    max_tokens = 180
    if wants_structured:
        system_prompt = (
            "你是一个中文轻量助手。请按用户要求输出结构化结果，优先分点总结，"
            "每点尽量 1-2 句，避免重复和寒暄，确保最后一条完整结束。"
        )
        max_tokens = 360
    if system_prompt_override:
        system_prompt = system_prompt_override
    if max_tokens_override is not None and max_tokens_override > 0:
        max_tokens = int(max_tokens_override)
    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=min(float(settings.llm_timeout_seconds or 20.0), 20.0),
            max_retries=0,
        )
        resp = client.chat.completions.create(
            model=settings.fast_llm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=max_tokens,
        )
        content = resp.choices[0].message.content if resp.choices else ""
        text = (content or "").strip()
        if text:
            return text
    except Exception:  # noqa: BLE001 - LLM 兜底失败时回退到模板，不向上抛
        pass
    compact = (message or "").strip()
    if compact:
        return f"我可以继续帮你处理这个问题：{compact[:32]}。如果你愿意，我也可以继续展开。"
    return "我在。你可以继续把问题说得更具体一点。"


def summarize_fast_material(
    *,
    lane: str,
    message: str,
    material: str,
    context_block: str | None = None,
) -> str:
    prompt = (
        f"请基于下面材料，用中文给出最短可用首答。"
        f" lane={lane}。优先直接回答，不展开无关背景；如果材料不足，要诚实说明。\n\n"
        f"用户问题：{message.strip()}\n\n"
        f"材料：\n{(material or '').strip()[:6000]}"
    )
    system_prompt_override: str | None = None
    max_tokens_override: int | None = None
    if lane == "web" and "[网页正文]" in (material or ""):
        wants_web_points = _prefers_structured_web_summary(message) or _needs_structured_fast_answer(message)
        system_prompt_override = (
            "你是一个中文网页摘要助手。请基于网页正文直接回答用户问题，"
            + (
                "优先输出 3-5 个要点，每点 1-2 句，覆盖主题、关键事实、影响或结论；"
                if wants_web_points
                else "优先完整概括核心事实，可比默认快答稍微展开一点，但仍保持简洁；"
            )
            + "避免编造材料中没有的信息，确保最后一句完整结束。"
        )
        max_tokens_override = 520 if wants_web_points else 420
    return run_fast_llm_answer(
        prompt,
        context_block=context_block,
        system_prompt_override=system_prompt_override,
        max_tokens_override=max_tokens_override,
    )


def try_fast_weather_answer(message: str) -> tuple[str, dict[str, Any]] | None:
    city = weather_city_from_message(message)
    if city is None:
        return None
    city_zh, city_key = city
    t0 = time.perf_counter()
    city_meta = WEATHER_CITY_MAP.get(city_key)
    if city_meta is None:
        return None
    city_name, lat, lon = city_meta
    try:
        timeout = httpx.Timeout(1.2, connect=0.8, read=1.0, write=0.8, pool=0.8)
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                    "timezone": "Asia/Shanghai",
                    "forecast_days": 1,
                },
            )
        resp.raise_for_status()
        data = resp.json()
        current = data.get("current") or {}
        daily = data.get("daily") or {}
        temp = current.get("temperature_2m")
        feels = current.get("apparent_temperature")
        humidity = current.get("relative_humidity_2m")
        wind = current.get("wind_speed_10m")
        desc = weather_desc(current.get("weather_code"))
        max_list = daily.get("temperature_2m_max") or []
        min_list = daily.get("temperature_2m_min") or []
        rain_list = daily.get("precipitation_probability_max") or []
        max_c = max_list[0] if max_list else None
        min_c = min_list[0] if min_list else None
        rain = rain_list[0] if rain_list else None
        parts = [f"{city_name}当前{desc}"]
        if temp is not None:
            parts.append(f"气温 {temp}℃")
        if feels is not None:
            parts.append(f"体感 {feels}℃")
        if min_c is not None and max_c is not None:
            parts.append(f"今日约 {min_c}-{max_c}℃")
        if humidity is not None:
            parts.append(f"湿度 {humidity}%")
        if rain is not None:
            parts.append(f"最高降水概率 {rain}%")
        if wind is not None:
            parts.append(f"风速约 {wind} km/h")
        answer = "，".join(parts) + "。数据源：Open-Meteo。"
        return answer, {
            "fast_path": "weather",
            "fast_path_provider": "open-meteo",
            "fast_weather_city": city_name,
            "fast_weather_elapsed_ms": format_ms((time.perf_counter() - t0) * 1000),
        }
    except Exception as exc:  # noqa: BLE001 - 天气源异常降级为友好提示
        return (
            f"我刚才走了天气快路径，但天气源暂时没返回可用结果（{type(exc).__name__}）。你可以稍后再试，或让我走网页搜索查一次。",
            {
                "fast_path": "weather_failed",
                "fast_weather_city": city_zh,
                "fast_weather_error": type(exc).__name__,
                "fast_weather_elapsed_ms": format_ms((time.perf_counter() - t0) * 1000),
            },
        )


def can_use_direct_fast_path(
    message: str,
    *,
    use_knowledge: bool,
    v13_file_content: str | bytes | None,
    v13_text_content: str | None,
) -> bool:
    msg = (message or "").strip()
    if not msg or use_knowledge or v13_file_content is not None or (v13_text_content or "").strip():
        return False
    if len(msg) > 80:
        return False
    lower = msg.lower()
    return not any(token.lower() in lower for token in FAST_BLOCK_TOKENS)


def build_fast_trace_extra(
    *,
    lane: str,
    capabilities_called: list[str],
    elapsed_ms: int,
    exit_reason: str,
    cross_lane_violation: bool = False,
) -> dict[str, Any]:
    return {
        "fast_lane_name": lane,
        "capabilities_called": capabilities_called,
        "cross_lane_violation": cross_lane_violation,
        "fast_exit_reason": exit_reason,
        "fast_first_response_ms": elapsed_ms,
    }


def run_general_fast_path(
    *,
    message: str,
    context_block: str | None,
) -> tuple[str, dict[str, Any]]:
    answer_text = run_fast_llm_answer(message, context_block=context_block)
    return answer_text, {
        "fast_path": "general_fast",
        "lane": "general",
        "mode": "fast",
        "capabilities_called": ["capability.general.direct_answer"],
        "fast_exit_reason": "general_direct_answer",
    }


def run_kb_fast_path(
    *,
    message: str,
    context_block: str | None,
    clock,
    shared_prep: Any | None = None,
    ingress: Any | None = None,
) -> tuple[str, dict[str, Any]] | None:
    from application.chat.decision_arbitrator import arbitrate_mode
    from application.chat.pending_kind import PendingKind
    from application.chat.turn_cache import current_turn_cache
    from application.ingress.lane_decision_schema import LaneDecision
    from services.capabilities.knowledge.kb_pipeline import (
        fetch_kb_answer_material_from_probe,
        probe_kb_capability,
    )

    budget_clock = clock
    kb_cache = current_turn_cache()
    prep = shared_prep
    if prep is not None and prep.snapshot is not None and prep.material_text:
        chunks = list(prep.snapshot.chunks)
        trace_info = dict(prep.snapshot.trace_info)
        fact = prep.trace_extra.get("capability_fact")
        advice = prep.trace_extra.get("capability_advice")
        material = prep.material_text or ""
        ranked = chunks
        capabilities_called = list(prep.capabilities_called) or [
            "capability.kb.retrieve",
            "capability.kb.shared_snapshot",
        ]
    else:
        fact, advice, chunks, trace_info = probe_kb_capability(
            message,
            clock=budget_clock,
            turn_cache=kb_cache,
        )
        if advice.suggested_mode != "sync_ok" or not chunks:
            ingress = LaneDecision(
                lane="kb",
                mode="fast",
                router_source="rule",
                router_confidence=0.9,
                router_decision_ms=0,
            )
            arbitrate_mode(
                session_pending=PendingKind.NONE,
                ingress=ingress,
                main_plan=None,
                capability_advice=advice,
                clock=budget_clock,
            )
            return None
        material, ranked, capabilities_called, trace_info = fetch_kb_answer_material_from_probe(
            chunks,
            trace_info,
        )
    if _kb_should_prefer_complex(
        message=message,
        ingress=ingress,
        ranked=ranked,
        evidence_tier=(
            prep.snapshot.evidence_tier
            if prep is not None and prep.snapshot is not None
            else str((fact.metadata.get("evidence_tier") if fact else "") or "")
        ),
    ):
        return None
    if not ranked:
        return None
    answer_text = summarize_fast_material(lane="kb", message=message, material=material, context_block=context_block)
    kb_suff = getattr(prep, "kb_sufficiency", None) if prep is not None else None
    extra: dict[str, Any] = {
        "fast_path": "kb_fast",
        "lane": "kb",
        "mode": "fast",
        "executor_profile": "fast",
        "rag_context_chars": len(material),
        "v15_retrieved_chunks_count": len(ranked),
        "v14_retrieval_trace": trace_info,
        "capabilities_called": capabilities_called,
        "fast_exit_reason": "kb_retrieve_answer",
        "capability_fact": fact,
        "capability_advice": advice,
        "kb_hits": len(ranked),
        "kb_top_score": (
            prep.snapshot.top_score
            if prep is not None and prep.snapshot is not None
            else (fact.metadata.get("top_score") if fact else None)
        ),
        "kb_evidence_tier": (
            prep.snapshot.evidence_tier
            if prep is not None and prep.snapshot is not None
            else (fact.metadata.get("evidence_tier") if fact else None)
        ),
    }
    if kb_suff is not None:
        extra["kb_sufficiency_level"] = kb_suff.level
    if prep is not None:
        extra["shared_retrieval_used"] = True
    return answer_text, extra


def _kb_should_prefer_complex(
    *,
    message: str,
    ingress: Any | None,
    ranked: list[Any],
    evidence_tier: str,
) -> bool:
    if ingress is None:
        return False
    complex_candidate = bool(getattr(ingress, "complex_candidate", False))
    if not complex_candidate:
        return False
    reason_codes = {
        str(code or "").strip()
        for code in list(getattr(ingress, "complex_reason_codes", []) or [])
        if str(code or "").strip()
    }
    text = (message or "").strip()
    strong_shape = bool(reason_codes & _KB_COMPLEX_REASON_CODES) or any(marker in text for marker in _KB_COMPLEX_MARKERS)
    if not strong_shape:
        return False
    chunk_count = len(list(ranked or []))
    if chunk_count < 2:
        return False
    return str(evidence_tier or "") in {"strong", "usable"}


def run_web_fast_path(
    *,
    message: str,
    context_block: str | None,
    clock,
) -> tuple[str, dict[str, Any]] | None:
    from application.chat.decision_arbitrator import arbitrate_mode
    from application.chat.pending_kind import PendingKind
    from application.ingress.lane_decision_schema import LaneDecision
    from services.capabilities.web import web_orchestration_service as agno_web_service

    budget_clock = clock
    url_match = re.search(r"https?://[^\s]+", message or "", flags=re.IGNORECASE)
    url = url_match.group(0) if url_match else ""
    if url:
        fact, advice = agno_web_service.probe_web_capability(
            url,
            clock=budget_clock,
        )
        if advice.suggested_mode == "demote_to_async":
            ingress = LaneDecision(
                lane="web",
                mode="fast",
                router_source="rule",
                router_confidence=0.9,
                router_decision_ms=0,
            )
            decided_mode, decided_reason = arbitrate_mode(
                session_pending=PendingKind.NONE,
                ingress=ingress,
                main_plan=None,
                capability_advice=advice,
                clock=budget_clock,
            )
            host = (urlparse(url).netloc or url).strip()
            extra: dict[str, Any] = {
                "fast_path": "web_fast_background_hint",
                "lane": "web",
                "mode": "fast",
                "capabilities_called": ["capability.web.probe"],
                "fast_exit_reason": "web_dynamic_required",
                "capability_advice": advice,
                "capability_fact": fact,
                "arbitrator.decided_mode": decided_mode,
                "arbitrator.decided_reason": decided_reason,
            }
            if decided_mode == "complex":
                return None
            if decided_mode == "async":
                set_pending_kind_signal(extra, PendingKind.FAST_PENDING.value)
                extra["fast_exit_reason"] = "web_fast_pending"
            answer = (
                f"这个网页静态抓取不足，已进入后台处理建议：{host}。"
                f"原因：{advice.reason or 'dynamic_required'}。"
            )
            return answer, extra

    material = agno_web_service.fetch_web_fast_material(message, max_results=2)
    if not (material or "").strip():
        return None
    body_text = _extract_page_body_from_material(material)
    material_sources = agno_web_service.detect_web_fast_material_sources(material)
    if _wants_full_web_text(message) and body_text:
        return body_text, {
            "fast_path": "web_fast_fulltext",
            "lane": "web",
            "mode": "fast",
            "web_search_used": material_sources.get("web_supplement_source") == "search",
            "web_evidence_chars": len(material),
            "web_output_mode": "fulltext",
            **material_sources,
            "capabilities_called": ["capability.web.static_fetch"],
            "fast_exit_reason": "web_static_fetch_fulltext",
        }
    answer_text = summarize_fast_material(lane="web", message=message, material=material, context_block=context_block)
    return answer_text, {
        "fast_path": "web_fast",
        "lane": "web",
        "mode": "fast",
        "web_search_used": True,
        "web_evidence_chars": len(material),
        **material_sources,
        "capabilities_called": ["capability.web.static_fetch"],
        "fast_exit_reason": "web_static_fetch_answer",
    }


def run_document_fast_path(
    *,
    message: str,
    context_block: str | None,
    v13_text_content: str | None,
    v13_file_content: str | bytes | None,
    v13_title: str | None = None,
    clock,
) -> tuple[str, dict[str, Any]] | None:
    from application.chat.decision_arbitrator import arbitrate_mode
    from application.chat.pending_kind import PendingKind
    from application.ingress.lane_decision_schema import LaneDecision
    from services.capabilities.document import parse_service, summarize_service

    budget_clock = clock
    file_path = (v13_title or "").strip() or None
    fact, advice, parse_result = parse_service.probe_document_capability(
        inline_text=v13_text_content,
        file_content=v13_file_content,
        file_path=file_path,
        clock=budget_clock,
    )
    if advice.suggested_mode == "demote_to_async":
        ingress = LaneDecision(
            lane="document",
            mode="fast",
            router_source="rule",
            router_confidence=0.9,
            router_decision_ms=0,
        )
        decided_mode, decided_reason = arbitrate_mode(
            session_pending=PendingKind.NONE,
            ingress=ingress,
            main_plan=None,
            capability_advice=advice,
            clock=budget_clock,
        )
        name = file_path or "当前文档"
        extra: dict[str, Any] = {
            "fast_path": "document_fast_background_hint",
            "lane": "document",
            "mode": "fast",
            "capabilities_called": ["capability.document.probe"],
            "fast_exit_reason": "document_ocr_required",
            "capability_advice": advice,
            "capability_fact": fact,
            "arbitrator.decided_mode": decided_mode,
            "arbitrator.decided_reason": decided_reason,
            "document_page_count": fact.page_count,
            "document_ocr_required": fact.ocr_required,
        }
        if decided_mode == "complex":
            return None
        if decided_mode == "async":
            set_pending_kind_signal(extra, PendingKind.FAST_PENDING.value)
            extra["fast_exit_reason"] = "document_fast_pending"
        answer = (
            f"文档「{name}」需要 OCR 后台处理（约 {fact.page_count or '?'} 页），"
            f"我先返回任务状态。"
        )
        return answer, extra
    if advice.suggested_mode != "sync_ok":
        return None
    if parse_result is not None and parse_result.status == "success" and (parse_result.text or "").strip():
        material = str(parse_result.text).strip()
        parse_caps = [
            "capability.document.probe",
            "capability.document.parse_pdf_quick"
            if file_path and str(file_path).lower().endswith(".pdf")
            else "capability.document.parse_text_or_table",
        ]
    else:
        material, parse_caps, _parse_result = parse_service.extract_inline_material(
            inline_text=v13_text_content,
            file_content=v13_file_content,
            file_path=file_path,
        )
    if not material:
        return None
    capabilities_called = list(parse_caps)
    if "capability.document.summarize" not in capabilities_called:
        capabilities_called.append("capability.document.summarize")
    answer_text = summarize_service.summarize_document(
        message=message,
        material=material,
        context_block=context_block,
    )
    extra_out: dict[str, Any] = {
        "fast_path": "document_fast",
        "lane": "document",
        "mode": "fast",
        "capabilities_called": capabilities_called,
        "fast_exit_reason": "document_inline_summary",
        "capability_fact": fact,
        "capability_advice": advice,
        "document_page_count": fact.page_count,
        "document_ocr_required": fact.ocr_required,
    }
    return answer_text, extra_out


def run_video_fast_path(
    *,
    message: str,
    session_id: str | None,
    context_block: str | None,
    clock,
) -> tuple[str, dict[str, Any]] | None:
    from application.chat.decision_arbitrator import arbitrate_mode
    from application.chat.pending_kind import PendingKind
    from application.ingress.lane_decision_schema import LaneDecision
    from services.capabilities.video.early_video_support import video_tool_result_to_fetch_result
    from services.capabilities.video.video_contract_runtime import (
        advice_from_tool_result,
        is_video_background_recommended,
    )
    from tools.video.extract_web_video_subtitle import _extract_web_video_subtitle

    budget_clock = clock
    match = re.search(r"https?://[^\s]+", message or "", flags=re.IGNORECASE)
    url = match.group(0) if match else ""
    if not url:
        return None
    result = _extract_web_video_subtitle(url, session_id=session_id or "")
    fetch = video_tool_result_to_fetch_result(url=url, result=result)
    metadata = dict(getattr(result, "metadata", {}) or {})
    capabilities_called = ["capability.video.subtitle_probe"]
    if fetch.text_source == "asr":
        capabilities_called.append("capability.video.short_sync_asr")
    if fetch.success and (fetch.text or "").strip():
        answer_text = summarize_fast_material(lane="video", message=message, material=fetch.text, context_block=context_block)
        return answer_text, {
            "fast_path": "video_fast",
            "lane": "video",
            "mode": "fast",
            "v16_video_source_type": "web_video",
            "v11_middle_video_url_asr_model": str(metadata.get("model") or ""),
            "capabilities_called": capabilities_called,
            "fast_exit_reason": "video_probe_answer",
        }
    if is_video_background_recommended(result):
        host = (urlparse(url).netloc or url).strip()
        task_id = str(getattr(result, "task_id", "") or metadata.get("background_task_id") or "")
        extra: dict[str, Any] = {
            "fast_path": "video_fast_background_hint",
            "lane": "video",
            "mode": "fast",
            "v16_video_source_type": "web_video",
            "task_id": task_id,
            "capabilities_called": ["capability.video.duration_probe"],
            "fast_exit_reason": "video_background_queued",
        }
        advice = advice_from_tool_result(result)
        ingress = LaneDecision(
            lane="video",
            mode="fast",
            router_source="rule",
            router_confidence=0.9,
            router_decision_ms=0,
        )
        decided_mode, decided_reason = arbitrate_mode(
            session_pending=PendingKind.NONE,
            ingress=ingress,
            main_plan=None,
            capability_advice=advice,
            clock=budget_clock,
        )
        extra["arbitrator.decided_mode"] = decided_mode
        extra["arbitrator.decided_reason"] = decided_reason
        set_pending_kind_signal(extra, PendingKind.FAST_PENDING.value)
        if advice is not None:
            extra["capability_advice"] = advice
        if decided_mode == "async":
            extra["fast_exit_reason"] = "video_fast_pending"
        elif decided_mode == "complex":
            return None
        answer = (
            f"这个视频已进入后台处理队列，我先给你首答：当前已识别为长视频或需重处理，完成后可继续查看结果。来源：{host}。"
        )
        return answer, extra
    return None


def should_demote_fast_to_async(extra: dict[str, Any]) -> bool:
    """True when fast lane must delegate to async_entry instead of fast assembly (§6.4)."""
    advice = extra.get("capability_advice")
    if isinstance(advice, CapabilityAdvice) and advice.suggested_mode == "demote_to_async":
        return True
    suggested = str(extra.get("capability_suggested_mode") or "").strip()
    if suggested == "demote_to_async":
        return True
    return str(extra.get("arbitrator.decided_mode") or "") == "async"


def _background_task_id_from_extra(extra: dict[str, Any]) -> str:
    for key in ("task_id", "background_task_id"):
        value = str(extra.get(key) or "").strip()
        if value and not value.startswith("fast-"):
            return value
    return ""


def build_fast_result(
    *,
    answer: str,
    session_id: str | None,
    request_id: str | None,
    elapsed_ms: int,
    extra: dict[str, Any],
) -> ChatTurnResult:
    capabilities_called = list(extra.get("capabilities_called") or [])
    lane_for_audit = str(extra.get("lane") or extra.get("fast_lane_name") or extra.get("router_lane") or "")
    if lane_for_audit and capabilities_called:
        extra["cross_lane_violation"] = cross_lane_violation_for_capabilities(
            lane_for_audit, capabilities_called
        )
    fast_path = str(extra.get("fast_path") or "fast")
    lane = str(extra.get("lane") or "")
    if not lane:
        if fast_path.startswith("local_") or fast_path in {"weather", "weather_failed"}:
            lane = fast_path
        else:
            lane = str(extra.get("router_lane") or fast_path)
    capabilities_called = list(extra.get("capabilities_called") or [])
    fast_task_id = str(
        extra.get("fast_task_id")
        or f"fast-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
    )
    collab_trace = [f"v15:needs_retrieval_plan=False path={fast_path}", f"v15:fast_path={fast_path}"]
    background_task_id = _background_task_id_from_extra(extra)
    pending_kind = pending_kind_signal_from_extra(extra) or ""
    is_fast_pending = bool(background_task_id) or pending_kind == PendingKind.FAST_PENDING.value
    top_task_id: str | None = None
    answer_type = "fast_path"
    if is_fast_pending and background_task_id:
        top_task_id = background_task_id
        answer_type = "fast_pending"
        pending_kind = pending_kind or PendingKind.FAST_PENDING.value
    merged_extra: dict[str, Any] = build_common_exit_extra(
        extra_base={
            "lane": lane,
            EXIT_SIGNAL_PRIMARY_PATH: fast_path,
            "fast_path": True,
            "agno": True,
            "collaboration_trace": collab_trace,
            "v4_min_collab": True,
            "v4_path_fingerprint": fast_path,
            "v4_nodes": {},
            "v6_takeover": True,
            "v6_main_task_id": fast_task_id,
            "v6_middle_web_reason": "fast_path_skip",
            "v6_middle_material_insufficient": False,
            "v6_plan_web_mode": "fast_skip",
            "v6_plan_answer_composition": "default",
            "v6_plan_force_skip_evidence": True,
            "v6_middle_kb_tier": "none",
            "v6_middle_insufficiency_signal": "none",
            "v15_plan_id": fast_task_id,
            "v15_bundle_id": f"{fast_task_id}-bundle",
            "v15_needs_retrieval": False,
            "v15_retrieval_strategy": "fast_skip",
            "v15_needs_pending": False,
            "v15_pending_reference": "none",
            "v15_answer_mode": "direct",
            "v15_tools_allowed": [],
            "v15_material_sufficiency": "sufficient",
            "v15_execution_status": "ok",
            "v15_retrieved_chunks_count": 0,
            "fast_lane_name": lane,
            "capabilities_called": capabilities_called,
            "cross_lane_violation": bool(extra.get("cross_lane_violation", False)),
            "fast_exit_reason": str(extra.get("fast_exit_reason") or "fast_path_complete"),
            "fast_first_response_ms": elapsed_ms,
            "agent_timings": {
                "session_snapshot_ms": int(extra.get("session_snapshot_ms", 0) or 0),
                "main_ms": 0,
                "middle_ms": 0,
                "answer_ms": int(extra.get("fast_answer_ms", 0) or 0),
                "session_update_ms": 0,
                "extra_build_ms": 0,
                "total_ms": elapsed_ms,
            },
            **extra,
            "sla_deadline_ms": SLA_BUDGET_MS,
        },
        ingress=None,
        mode="fast",
        executor_profile="fast",
        progress_stage="completed",
        elapsed_ms=elapsed_ms,
    )
    set_mode_signal(merged_extra, "fast")
    set_material_sufficiency_signal(merged_extra, "sufficient")
    if top_task_id:
        merged_extra["partial_answer_text"] = answer
        merged_extra.setdefault(
            "next_action",
            "后台任务处理中，请轮询 /tasks/{task_id}/result 获取完整结果。",
        )
        merged_extra["progress_stage"] = str(extra.get("progress_stage") or "queued")
    primary_path = str(
        merged_extra.get(EXIT_SIGNAL_PRIMARY_PATH)
        or extra.get("fast_path")
        or "fast"
    )
    try:
        pk = PendingKind(pending_kind) if pending_kind else PendingKind.NONE
    except ValueError:
        pk = PendingKind.NONE
    facts = TurnFacts(
        router_lane=lane,
        effective_mode="fast",
        public_mode="fast",
        executor_profile="fast",
        pending_kind=pk,
        primary_path_candidate=primary_path,
        async_pending=answer_type == "fast_pending",
        answer_type=answer_type,
    )
    return apply_turn_exit_to_chat_turn(
        {
            "ok": True,
            "answer": answer,
            "session_id": session_id,
            "request_id": request_id,
            "task_id": top_task_id,
            "answer_type": answer_type,
            "pipeline_ok": True,
            "extra": merged_extra,
            "workflow_elapsed_ms": elapsed_ms,
        },
        facts=facts,
        effective_mode="fast",
    )
