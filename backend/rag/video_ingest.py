"""
V7 第 2 轮：把 V7 第 1 轮的"业务型 MCP tool（video_to_text）产物"接进现有 ingest / 知识库链。

设计边界（最小 / 不平行造系统）：
- **复用** `rag.ingest.ingest_text` —— 不新建"视频专属知识库"，不新建第二套检索。
- **不**让业务型 MCP tool 自己吞下入库（保持 V7 第 1 轮 tool 边界：tool 只产文本）。
- 对 source_id 做最小规范化：`video:<basename>`——
  * 与 sample.md 等历史 source_id 显式分流，便于后续问答阶段从命中结果上立刻分辨"来源是视频"；
  * basename 而不是绝对路径，因为 SQLite FTS5 unicode61 分词器对反斜杠 / 长路径不友好，
    而绝对路径仍然由 `rag.ingest._fts_boost_header` 写进 `[doc_path]` 段，retrieval 端不丢。
- 失败结构化返回 `{ok, source_id, chunks, error}`，**不**抛异常给 middle runtime
  （第 1 轮 MCP 调用层已经实践过这条结构化失败收口规则）。

明确**不做**（与第 2 轮总边界一致）：
- 不做平行知识库；
- 不做向量重排扩展；
- 不做多视频源；
- 不做 chunk 策略升级；
- 不做"自动归档 / 去重 / 标签 / 热度"等任何治理特性。

支持边界（再次显式声明，防止误读为"完整视频能力"）：
- 当前唯一支持：本地 .mp4 容器内 mov_text / tx3g 字幕轨产出的纯文本；
- 非支持轨 / 无字幕轨 / 文件不存在等失败已在第 1 轮 `subtitle_extractor` 与 MCP server 收口；
- 第 1 轮失败 → 第 2 轮入库**也**失败（不伪装成功、不静默吞）。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("light_maqa")


# 与 V6 既有 source_id 风格分流：sample.md 走 "knowledge_samples/sample.md"，
# 视频走 "video:<basename>"。冒号是语义命名空间分隔符，**不**是路径分隔符——
# SQLite FTS unicode61 会把它当 token 边界，但 `_fts_boost_header` 同时写
# `[doc_path] {source_id}` + `[doc_file] {basename}`，命中权由 body 块独立承担。
SOURCE_ID_NAMESPACE = "video:"

# V11 R5 D：title slug 长度上限（按字符算）。SQLite FTS source_id 列没硬上限，
# 控长是为了 trace / 调试输出可读，且避免极端长标题做主键 lookup 性能下降。
_TITLE_SLUG_MAX_CHARS = 30
# slug 内允许保留：中日韩 + 拉丁字母数字；其他全部转 dash 后压缩
_SLUG_KEEP_RE = re.compile(
    r"[^0-9A-Za-z\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]+"
)


def _title_to_slug(title: str | None) -> str:
    """把视频标题转成"短、稳定、可读"的 slug。

    - 中日韩字符 + 拉丁字母数字保留；其他统统 dash 化 + 压缩
    - 长度上限 ``_TITLE_SLUG_MAX_CHARS``
    - 空 / 纯符号 → 返回 ""，由调用方决定是否回退
    """
    raw = (title or "").strip()
    if not raw:
        return ""
    slug = _SLUG_KEEP_RE.sub("-", raw).strip("-")
    if not slug:
        return ""
    return slug[:_TITLE_SLUG_MAX_CHARS].rstrip("-")


def build_video_source_id(
    source_basename: str | None,
    source_path: str | None,
    *,
    title: str | None = None,
    ingest_time: datetime | None = None,
) -> str:
    """
    构造稳定 source_id。

    向后兼容（V7 本地 mp4 链）：``title=None`` 且 ``ingest_time=None`` 时，
    输出与历史版本完全一致 —— ``video:<basename>``。

    V11 R5 D（V11 URL 链）：传入 ``title`` 或 ``ingest_time`` 中至少一个，
    输出格式：``video:YYYY-MM-DD_<title-slug>_<basename>``
    - 同一视频在不同时间入库 → 不同 source_id，新旧都在 KB 里
    - 从 source_id 一眼能看出"哪个视频、哪天入的"

    例：
        build_video_source_id("v7_e2e.mp4", r"C:\\videos\\v7_e2e.mp4")
            -> "video:v7_e2e.mp4"
        build_video_source_id(None, "/tmp/foo.mp4")
            -> "video:foo.mp4"
        build_video_source_id("ErBNfZEAW5c.video", None,
            title="AI Knowledge", ingest_time=datetime(2026,4,18,14,20,33))
            -> "video:2026-04-18_AI-Knowledge_ErBNfZEAW5c.video"
    """
    base = (source_basename or "").strip()
    if not base and source_path:
        base = Path(str(source_path)).name
    base = base.strip() or "unknown.mp4"
    if base.startswith(SOURCE_ID_NAMESPACE):
        base = base[len(SOURCE_ID_NAMESPACE):]

    if title is None and ingest_time is None:
        return f"{SOURCE_ID_NAMESPACE}{base}"

    date_part = (ingest_time or datetime.now()).strftime("%Y-%m-%d")
    slug = _title_to_slug(title)
    parts = [date_part]
    if slug:
        parts.append(slug)
    parts.append(base)
    return f"{SOURCE_ID_NAMESPACE}{'_'.join(parts)}"


def is_video_source_id(source_id: str | None) -> bool:
    """命中阶段判断："这条命中是不是来自 V7 视频入库链"。"""
    return bool(source_id and source_id.startswith(SOURCE_ID_NAMESPACE))


def _format_duration(sec: float | int | None) -> str:
    """V11 R5 C：时长格式化为人类可读的 X分Y秒；空 / 0 → "未知"。"""
    if not sec or sec <= 0:
        return "未知"
    total = int(sec)
    if total < 60:
        return f"{total}秒"
    m, s = divmod(total, 60)
    if m < 60:
        return f"{m}分{s}秒" if s else f"{m}分钟"
    h, m = divmod(m, 60)
    return f"{h}时{m}分" if m else f"{h}小时"


def _build_video_metadata_header(
    *,
    title: str | None,
    source_url: str | None,
    ingest_time: datetime | None,
    duration_sec: float | int | None,
    text_source: str | None,
    subtitle_lang: str | None,
    asr_provider: str | None,
) -> str:
    """V11 R5 C：构造入库前注入的视频元数据块。

    - 进 FTS body 一起入库，**LLM 答题时一定会看到**，从而清楚"这是哪条视频"
    - 字幕 / ASR 来源透明化，让 LLM 措辞更准确（不再说"根据您贴的内容"）
    - 不强求所有字段都有：缺失字段直接跳过那一行，避免 [None] 噪声
    """
    lines: list[str] = ["[视频元数据]"]
    if title:
        lines.append(f"标题: {title}")
    if source_url:
        lines.append(f"来源URL: {source_url}")
    if ingest_time:
        lines.append(f"入库时间: {ingest_time.strftime('%Y-%m-%d %H:%M:%S')}")
    dur = _format_duration(duration_sec)
    if dur != "未知":
        lines.append(f"时长: {dur}")
    if text_source == "subtitle":
        lang_part = f"({subtitle_lang})" if subtitle_lang else ""
        lines.append(f"字幕来源: 视频官方字幕{lang_part}")
    elif text_source == "asr":
        prov = asr_provider or "云端 ASR"
        lines.append(f"字幕来源: {prov} 自动语音识别")
    lines.append("==========")
    return "\n".join(lines)


def ingest_video_bundle(
    *,
    text: str | None,
    source_basename: str | None,
    source_path: str | None,
    title: str | None = None,
    ingest_time: datetime | None = None,
    source_url: str | None = None,
    duration_sec: float | int | None = None,
    text_source: str | None = None,
    subtitle_lang: str | None = None,
    asr_provider: str | None = None,
) -> dict[str, Any]:
    """
    把 V7 第 1 轮 MCP 产物（已清洗的纯文本 + 最小来源标识）写进现有知识库。

    V11 R5 D：可选 ``title`` / ``ingest_time``，传入则用 V11 URL 链格式
    ``video:YYYY-MM-DD_<slug>_<basename>``；不传则保持 V7 R2 历史格式 ``video:<basename>``。

    V11 R5 C：可选 ``source_url`` / ``duration_sec`` / ``text_source`` /
    ``subtitle_lang`` / ``asr_provider`` —— 任一非空即在入库文本头部注入
    ``[视频元数据]`` 块。无任何元数据参数时**完全保持 V7 行为**（无头注入）。

    返回（永远 dict，不抛异常）：
        {
            "ok": bool,
            "source_id": str,           # 实际写入用的稳定 source_id
            "chunks": int,              # 写入块数（含 boost header）
            "error": str,               # 失败原因，ok=True 时为 ""
            "has_metadata_header": bool, # V11 R5 C：是否注入了元数据头
        }

    最小失败边界：
    - text 为 None / 空字符串 / 仅空白 → 入库失败（与"无字幕轨"语义一致）
    - 入库底层抛异常 → 结构化失败，不伪装成功
    """
    source_id = build_video_source_id(
        source_basename, source_path, title=title, ingest_time=ingest_time
    )
    body = (text or "").strip()
    if not body:
        return {
            "ok": False,
            "source_id": source_id,
            "chunks": 0,
            "error": "video text is empty (清洗后无可入库内容)",
            "has_metadata_header": False,
        }

    has_meta = any(
        v is not None
        for v in (title, source_url, ingest_time, duration_sec, text_source)
    )
    if has_meta:
        header = _build_video_metadata_header(
            title=title,
            source_url=source_url,
            ingest_time=ingest_time,
            duration_sec=duration_sec,
            text_source=text_source,
            subtitle_lang=subtitle_lang,
            asr_provider=asr_provider,
        )
        body = f"{header}\n{body}"

    # 延迟 import：避免在不需要 RAG 的导入路径上拉起 sqlite/FTS schema
    try:
        from rag import ingest

        n = ingest.ingest_text(body, source_id=source_id)
    except Exception as e:  # noqa: BLE001
        logger.exception("V7R2 video_ingest failed source_id=%s", source_id)
        return {
            "ok": False,
            "source_id": source_id,
            "chunks": 0,
            "error": f"ingest_text failed: {e}",
            "has_metadata_header": has_meta,
        }

    if n <= 0:
        return {
            "ok": False,
            "source_id": source_id,
            "chunks": 0,
            "error": "ingest_text returned 0 chunks",
            "has_metadata_header": has_meta,
        }

    return {
        "ok": True,
        "source_id": source_id,
        "chunks": int(n),
        "error": "",
        "has_metadata_header": has_meta,
    }


__all__ = [
    "SOURCE_ID_NAMESPACE",
    "build_video_source_id",
    "ingest_video_bundle",
    "is_video_source_id",
]
