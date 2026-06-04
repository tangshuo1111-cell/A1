"""台账治理第2b轮 — Answer hint / extra / V11 短路辅助（从 runtime 抽出）。"""

from __future__ import annotations

from agents.main_agent import AgnoCollaborationPlan, MainXiezuoPan
from agents.middle_agent import AgnoMaterialBundle, CailiaoPan

from .schema import HuidaPan


def huida_to_executor_hint(
    hp: HuidaPan,
    xiezuo_pan: MainXiezuoPan,
    cailiao_pan: CailiaoPan,
    plan: AgnoCollaborationPlan,
    bundle: AgnoMaterialBundle,
    *,
    compact: bool = False,
) -> str:
    """
    把 main / middle / answer 三层判断结论压成一段 LLM 执行端 hint。

    - 必须包含 `[main]` `[middle]` `[answer]` 三段，方便 service / test 定位。
    - 当 `da_fengshi=baoshou` 时必须含「保守」字（兼容 `_FakeZhixing` 与 V6 单测断言）。
    """
    parts: list[str] = [
        (
            f"[main] 协作方向 renwu={xiezuo_pan.renwu_lei} "
            f"allow_kb={xiezuo_pan.allow_kb} allow_web={xiezuo_pan.allow_web} "
            f"风险={xiezuo_pan.fengxian_yinzi:.2f} 策略={xiezuo_pan.celue_tag} "
            f"answer_composition={plan.answer_composition} force_skip={plan.force_skip_evidence}"
        ),
        (
            f"[middle] 材料 gou={cailiao_pan.gou} bukong={cailiao_pan.bukong_xinhao} "
            f"laiyuan={cailiao_pan.laiyuan_zhu} kb_qiangdu={cailiao_pan.kb_qiangdu:.2f} "
            f"que={cailiao_pan.que_shenme} 下一步={cailiao_pan.xia_yi_bu} "
            f"kb_tier={bundle.kb_evidence_tier} signal={bundle.insufficiency_signal}"
        ),
    ]

    if hp.da_fengshi == "zhijie":
        celue_text = (
            "直接、自然回答用户问题；像口头解释，不要写章节标题或 markdown 模板；"
            "如有材料只作背景依据，不堆砌；可保留轻量 emoji"
        )
    elif hp.da_fengshi == "baoshou":
        celue_text = (
            "采用保守语气：明确说明所引材料相关性偏弱、避免过度承诺；"
            "需要时给出『我不太确定』式说明（baoshou_level 高时尤其如此）"
        )
    else:
        celue_text = (
            "采用「已知 / 未知」分块：先说明能确定的部分，再列出尚缺的信息或下一步建议"
        )

    parts.append(
        f"[answer] 大风格={hp.da_fengshi} 结构={hp.jiegou_mode} "
        f"保守={hp.baoshou_level:.2f} 策略说明：{celue_text}"
    )

    if hp.da_fengshi == "baoshou" and "保守" not in " ".join(parts):
        parts.append("[answer/baoshou] 请保守作答")

    _trace_text = "\n".join(getattr(bundle, "trace", []) or [])
    if "v14:middle:" in _trace_text and "no_match=True" in _trace_text:
        parts.append(
            "[answer/v14] 本轮检索无命中（no_match）：知识库中未找到相关材料。"
            "请明确告知用户当前知识库没有相关内容，不要基于不存在的证据作答。"
        )
    elif "v14:middle:" in _trace_text and "low_confidence=True" in _trace_text:
        parts.append(
            "[answer/v14] 本轮检索置信度偏低（low_confidence）：检索结果相关性较弱。"
            "请在回答中注明检索证据不足，避免过度确信。"
        )

    _answer_mode = getattr(plan, "answer_mode", "direct") or "direct"
    _mat_suf = getattr(bundle, "material_sufficiency", "sufficient") or "sufficient"
    _bundle_id = getattr(bundle, "bundle_id", "") or ""
    _plan_id = getattr(bundle, "plan_id", "") or ""
    parts.append(
        f"[v15/bundle] plan_id={_plan_id} bundle_id={_bundle_id} "
        f"answer_mode={_answer_mode} material_sufficiency={_mat_suf} "
        f"retrieved_chunks={len(getattr(bundle, 'retrieved_chunks', []) or [])} "
        f"temporary_materials={len(getattr(bundle, 'temporary_materials', []) or [])} "
        f"commit_results={len(getattr(bundle, 'commit_results', []) or [])} "
        f"failures={len(getattr(bundle, 'failures', []) or [])}"
    )
    if _mat_suf in ("no_match", "insufficient"):
        parts.append(
            "[v15/answer] 当前材料不足，请保守作答，不要基于不存在的知识回答。"
        )

    if compact:
        compact_parts: list[str] = [
            (
                f"[main] renwu={xiezuo_pan.renwu_lei} "
                f"compose={plan.answer_composition}"
            ),
            (
                f"[middle] src={cailiao_pan.laiyuan_zhu} "
                f"tier={bundle.kb_evidence_tier} mat={_mat_suf} "
                f"chunks={len(getattr(bundle, 'retrieved_chunks', []) or [])}"
            ),
            (
                f"[answer] style={hp.da_fengshi} jiegou={hp.jiegou_mode} "
                f"safe={hp.baoshou_level:.2f}"
            ),
        ]
        if _mat_suf in ("no_match", "insufficient"):
            compact_parts.append("[answer] 用简体中文；证据不足时保守作答，不能补编。")
        elif hp.da_fengshi == "zhijie":
            compact_parts.append("[answer] 用简体中文；先结论，再展开；尽量精炼，少重复材料原句。")
        elif hp.da_fengshi == "baoshou":
            compact_parts.append("[answer] 用简体中文；结论保守，明确边界；表述尽量精炼。")
        else:
            compact_parts.append("[answer] 用简体中文；先已知，再未知，最后给建议；避免重复。")
        return "\n".join(compact_parts)

    return "\n".join(parts)


def xiezuo_extra_for_service(
    plan: AgnoCollaborationPlan,
    bundle: AgnoMaterialBundle,
) -> dict:
    """answer 自己暴露给 service 的 extra 字段集合（service 不再代写 v6_* 维度）。

    推迟导入 ``pan_huida_agno``，避免与 ``runtime`` 循环依赖。
    """
    from agents.answer_agent.runtime import pan_huida_agno

    hp = pan_huida_agno(plan, bundle)
    xp = plan.xiezuo_pan
    cp = bundle.cailiao_pan
    out: dict = {
        "v6_main_pan_renwu": xp.renwu_lei,
        "v6_main_pan_allow_kb": xp.allow_kb,
        "v6_main_pan_allow_web": xp.allow_web,
        "v6_main_pan_fengxian": round(float(xp.fengxian_yinzi), 3),
        "v6_main_pan_celue": xp.celue_tag,
        "v6_middle_pan_gou": cp.gou,
        "v6_middle_pan_bukong": cp.bukong_xinhao,
        "v6_middle_pan_laiyuan": cp.laiyuan_zhu,
        "v6_middle_pan_kb_qiangdu": round(float(cp.kb_qiangdu), 3),
        "v6_middle_pan_que": cp.que_shenme,
        "v6_middle_pan_xia": cp.xia_yi_bu,
        "v6_answer_pan_dafengshi": hp.da_fengshi,
        "v6_answer_pan_jiegou": hp.jiegou_mode,
        "v6_answer_pan_baoshou": hp.baoshou_level,
        "v6_answer_pan_lane": hp.lane,
        "v6_answer_pan_primary_path": hp.primary_path,
        "v7_middle_pan_video_decision": bundle.mcp_video_decision,
        "v7_middle_pan_video_ok": bool(bundle.mcp_video_ok),
        "v7_middle_pan_video_source": bundle.mcp_video_source,
        "v7_middle_pan_video_ingested": bool(bundle.mcp_video_ingested),
        "v7_middle_pan_video_ingest_source_id": bundle.mcp_video_ingest_source_id,
        "v7_middle_pan_video_ingest_chunks": int(bundle.mcp_video_ingest_chunks),
        "v7_middle_pan_video_pending_id": getattr(bundle, "mcp_video_pending_id", None),
        "v8_middle_history_used": bool(bundle.v8_history_used),
        "v8_middle_history_anchor_source_id": bundle.v8_history_anchor_source_id,
        "v8_middle_history_anchor_status": bundle.v8_history_anchor_status,
        "v8_middle_history_anchor_stale": bool(bundle.v8_history_anchor_stale),
        "v8_answer_followup_dafengshi": hp.da_fengshi,
        "v8_answer_followup_baoshou": hp.baoshou_level,
    }
    if bundle.mcp_video_error:
        out["v7_middle_pan_video_error"] = bundle.mcp_video_error
    if bundle.mcp_video_ingest_error:
        out["v7_middle_pan_video_ingest_error"] = bundle.mcp_video_ingest_error
    if bundle.v8_history_followup_query:
        out["v8_middle_history_followup_query"] = bundle.v8_history_followup_query
    routing_explain = (plan.decision.routing_explain or "")
    if "v8:main:history_used=true" in routing_explain:
        out["v8_main_history_used"] = True
    if bundle.v8_history_used and (
        bundle.v8_history_anchor_stale or bundle.material_still_insufficient
    ):
        out["v8_answer_followup_baoshou_lifted"] = True

    legacy_v10_map = {
        "v10:router_signal=": "v10_main_router_signal",
        "v10:llm_intent=": "v10_main_llm_intent",
        "v10:llm_error=": "v10_main_llm_error",
        "v10:fallback_reason=": "v10_main_fallback_reason",
    }
    v11_main_optional_map = {
        "v10:explicit_kind=": "v10_main_explicit_kind",
        "v11:video_url=": "v11_main_video_url",
    }

    def _grab(text: str, token: str) -> str | None:
        idx = text.find(token)
        if idx < 0:
            return None
        start = idx + len(token)
        end = len(text)
        for ch in (" ", "\n", "\r", "\t"):
            i = text.find(ch, start)
            if 0 <= i < end:
                end = i
        value = text[start:end].rstrip("；").strip()
        return value or None

    for token, ext_key in legacy_v10_map.items():
        v = _grab(routing_explain, token)
        if v is not None:
            out[ext_key] = v
    for token, ext_key in v11_main_optional_map.items():
        v = _grab(routing_explain, token)
        if v is None or v == "(none)":
            continue
        out[ext_key] = v

    bundle_trace_text = "\n".join(getattr(bundle, "trace", []) or [])
    v11_middle_map = {
        "v11_middle:video_url_yitu=": "v11_middle_video_url_yitu",
        "v11_middle:video_url_from=": "v11_middle_video_url_from",
        "v11_middle:video_url_decision=": "v11_middle_video_url_decision",
        "v11_middle:video_url_ok=": "v11_middle_video_url_ok",
        "v11_middle:video_url_text_source=": "v11_middle_video_url_text_source",
        "v11_middle:video_url_chars=": "v11_middle_video_url_chars",
        "v11_middle:video_url_stage=": "v11_middle_video_url_stage",
        "v11_middle:video_url_error=": "v11_middle_video_url_error",
        "v11_middle:video_url_ingest_ok=": "v11_middle_video_url_ingest_ok",
        "v11_middle:video_url_ingest_source_id=": "v11_middle_video_url_ingest_source_id",
        "v11_middle:video_url_ingest_chunks=": "v11_middle_video_url_ingest_chunks",
        "v11_middle:video_url_ingest_error=": "v11_middle_video_url_ingest_error",
        "v11_middle:video_url_ingest_skip=": "v11_middle_video_url_ingest_skip",
        "v11_middle:video_url_kb_block=": "v11_middle_video_url_kb_block",
        "v11_middle:video_url_asr_provider=": "v11_middle_video_url_asr_provider",
        "v11_middle:video_url_asr_model=": "v11_middle_video_url_asr_model",
        "v11_middle:video_url_cookies=": "v11_middle_video_url_cookies",
    }
    for token, ext_key in v11_middle_map.items():
        v = _grab(bundle_trace_text, token)
        if v is None or v == "(none)":
            continue
        out[ext_key] = v
    return out


def _grab_trace_value(text: str, token: str) -> str | None:
    idx = text.find(token)
    if idx < 0:
        return None
    start = idx + len(token)
    end = len(text)
    for ch in (" ", "\n", "\r", "\t"):
        i = text.find(ch, start)
        if 0 <= i < end:
            end = i
    value = text[start:end].rstrip("；").strip()
    return value or None


def _suggestion_for_video_url_error(error: str) -> str:
    err = (error or "").strip()

    if err.startswith("url_contains_non_ascii") or "reason=non_ascii_in_url" in err:
        return (
            "URL 里混进了中文字符——最常见原因是 URL 后面没空格就接了"
            "「这个视频讲了什么」之类的提问，整串被当成 URL 送给下载器，"
            "下载器把含中文的 query 写进 HTTP 头时编码失败。\n"
            "把 URL 和提问之间加一个空格，或者把 URL 单独发一行再发提问，"
            "就能正常识别；也可以把字幕 / 文字稿粘贴给我，我再回答。"
        )

    if "web_video_asr_needs_confirmation" in err:
        return (
            "这条视频长度超过「免确认自动语音识别」上限（默认 15 分钟）。\n"
            "请在界面上确认「继续转写」后再发送；不超过上限的短视频会直接处理，无需确认。\n"
            "你也可以换带标准字幕的链接，或把文字稿粘贴给我。"
        )

    if "duration_exceeds_limit" in err:
        return (
            "这条视频的音频时长超过当前 ASR 上限（默认 30 分钟）。\n"
            "你可以：\n"
            "1) 在环境变量里调高 `VIDEO_MAX_AUDIO_SECONDS`（当前默认 1800）；\n"
            "2) 选一条带字幕的视频——有字幕时不需要 ASR，不受时长限制；\n"
            "3) 也可以直接把字幕 / 文字稿粘贴给我。"
        )

    if "reason=video_unavailable" in err:
        return (
            "该视频不可访问（可能是私享 / 已删除 / 地区限制）。\n"
            "请确认视频链接在浏览器中能正常打开，或换一条公开视频。"
        )

    if "reason=http_412_anti_bot" in err or "412" in err:
        return (
            "该站点返回 HTTP 412（反爬检测），说明需要有效的 cookies 才能下载。\n"
            "请上传对应网站的 cookies.txt（Netscape 格式），或换一条可公开下载的链接。"
        )

    if "OSError" in err or "errno=" in err:
        return (
            "发生了系统错误 / 网络连接中断。\n"
            "1) 等几秒后重试；\n"
            "2) 如果持续失败，请检查后端日志看具体错误。"
        )

    return (
        "1) 该站点对自动下载有反爬限制（如 B 站常返回 HTTP 412），"
        "可换一条已知可下载的链接（如 YouTube 公开视频）；\n"
        "2) 视频本身没有可用的字幕时，系统会自动下载音频再走 ASR。"
        "如果这里失败，请区分两种情况：\n"
        "   - 未配置：请确认 `.env` 里已有 `ASR_ENABLED=1`，并配置了可用的 ASR 通道；\n"
        "   - 已配置但调用失败：请检查 SiliconFlow / 腾讯 ASR 的网络连通性、额度和 key 是否可用；\n"
        "3) 也可以直接把字幕 / 文字稿粘贴给我，我再回答。"
    )


def detect_v11_video_url_failure(
    bundle: AgnoMaterialBundle,
    plan: AgnoCollaborationPlan | None = None,
) -> str | None:
    """V11 R1 fail_explicit 短路检测（供 ``AnswerAgent.huida`` 使用）。"""
    trace_lines = list(getattr(bundle, "trace", []) or [])
    if not trace_lines:
        return None
    trace_text = "\n".join(trace_lines)

    decision = _grab_trace_value(trace_text, "v11_middle:video_url_decision=")
    ok = _grab_trace_value(trace_text, "v11_middle:video_url_ok=")
    if decision != "call_url_fetch_video":
        return None
    if ok != "false":
        return None
    if "v11_middle:video_url_kb_block=fresh" in trace_text:
        return None

    stage = _grab_trace_value(trace_text, "v11_middle:video_url_stage=") or "unknown"
    error = _grab_trace_value(trace_text, "v11_middle:video_url_error=") or "unknown"
    routing_explain = ""
    if plan is not None:
        routing_explain = (getattr(plan.decision, "routing_explain", "") or "")
    src_url = _grab_trace_value(routing_explain, "v11:video_url=") or "(unknown)"

    stage_zh = {
        "metadata": "拉取视频元数据",
        "subtitle": "下载/解析字幕",
        "audio": "提取音频",
        "asr": "云端 ASR 转写",
        "ingest": "入库",
    }.get(stage, stage)

    suggestion = _suggestion_for_video_url_error(error)
    return (
        "我没能成功处理这条视频链接，所以**不能给出关于其内容的总结**——"
        "下面是确定性故障明细，避免我凭空编造：\n\n"
        f"- 视频源：{src_url}\n"
        f"- 失败阶段：{stage_zh}（stage={stage}）\n"
        f"- 失败原因：{error}\n\n"
        f"可能的处理方式：\n{suggestion}"
    )


__all__ = [
    "_suggestion_for_video_url_error",
    "detect_v11_video_url_failure",
    "huida_to_executor_hint",
    "xiezuo_extra_for_service",
]
