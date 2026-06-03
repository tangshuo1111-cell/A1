"""
V7 第 1 轮：从本地 .mp4 容器内 mov_text(tx3g) 字幕轨抽取可入库纯文本。

设计要点（最小、零外部依赖、Windows 友好）：
- 纯 Python `struct` 解析 ISO/IEC 14496-12 (ISO Base Media File Format) box 树；
- 找出所有 trak，过滤 hdlr.handler_type ∈ {'sbtl', 'subt', 'text'} 的字幕轨；
- 从 stbl 的 stsc / stsz / stco|co64 还原每个 sample 在 mdat 中的字节偏移；
- 按 mov_text 协议解码 sample：前 2 字节 BE u16 = 文本字节长度，后接 UTF-8 文本；
- 抽出的文本做最低限度清洗：strip 空白、合并连续空行、保留段间换行；
- 至少保留来源标识：`source_id = 文件名`、`source_path = 绝对路径`。

明确不做（V7 第 1 轮边界）：
- 不调 ffmpeg；不依赖任何外部二进制；
- 不直接负责入库（只产文本，由现有 ingest 链负责入库）；
- 不实现 ASR / 字幕翻译 / 多语言对齐。
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# ISO BMFF box 最小工具
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _Box:
    """ISO BMFF box 视图。所有偏移都是文件内绝对偏移（字节）。"""

    type: str
    offset: int       # box 起始位置（含 size header）
    size: int         # box 总大小
    header_size: int  # 8 或 16


def _read_box(data: bytes, off: int) -> _Box:
    if off + 8 > len(data):
        raise ValueError(f"box header out of range at offset={off}")
    size, btype = struct.unpack(">I4s", data[off : off + 8])
    header_size = 8
    if size == 1:
        if off + 16 > len(data):
            raise ValueError(f"largesize box header truncated at offset={off}")
        size = struct.unpack(">Q", data[off + 8 : off + 16])[0]
        header_size = 16
    elif size == 0:
        size = len(data) - off
    if size < header_size:
        raise ValueError(f"invalid box size={size} at offset={off}")
    return _Box(
        type=btype.decode("ascii", errors="replace"),
        offset=off,
        size=size,
        header_size=header_size,
    )


def _children(data: bytes, parent: _Box) -> list[_Box]:
    out: list[_Box] = []
    pos = parent.offset + parent.header_size
    end = parent.offset + parent.size
    while pos + 8 <= end:
        try:
            b = _read_box(data, pos)
        except ValueError:
            break
        if b.size <= 0 or pos + b.size > end:
            break
        out.append(b)
        pos += b.size
    return out


def _find(boxes: list[_Box], name: str) -> _Box | None:
    for b in boxes:
        if b.type == name:
            return b
    return None


def _walk(data: bytes, parent: _Box, path: list[str]) -> _Box | None:
    cur = parent
    for name in path:
        nxt = _find(_children(data, cur), name)
        if nxt is None:
            return None
        cur = nxt
    return cur


# ---------------------------------------------------------------------------
# stbl 子 box 解析（最小子集）
# ---------------------------------------------------------------------------
def _parse_hdlr_handler_type(data: bytes, hdlr: _Box) -> str:
    """`hdlr` body: 1B version + 3B flags + 4B pre_defined + 4B handler_type + ..."""
    body = hdlr.offset + hdlr.header_size + 4 + 4
    return data[body : body + 4].decode("ascii", errors="replace")


def _parse_stsz(data: bytes, stsz: _Box) -> list[int]:
    body = stsz.offset + stsz.header_size + 4
    sample_size, sample_count = struct.unpack(">II", data[body : body + 8])
    if sample_size != 0:
        return [sample_size] * sample_count
    sizes: list[int] = []
    cur = body + 8
    for _ in range(sample_count):
        sizes.append(struct.unpack(">I", data[cur : cur + 4])[0])
        cur += 4
    return sizes


def _parse_stco(data: bytes, stco: _Box) -> list[int]:
    body = stco.offset + stco.header_size + 4
    n = struct.unpack(">I", data[body : body + 4])[0]
    if n == 0:
        return []
    return list(struct.unpack(">" + "I" * n, data[body + 4 : body + 4 + 4 * n]))


def _parse_co64(data: bytes, co64: _Box) -> list[int]:
    body = co64.offset + co64.header_size + 4
    n = struct.unpack(">I", data[body : body + 4])[0]
    if n == 0:
        return []
    return list(struct.unpack(">" + "Q" * n, data[body + 4 : body + 4 + 8 * n]))


def _parse_stsc(data: bytes, stsc: _Box) -> list[tuple[int, int, int]]:
    body = stsc.offset + stsc.header_size + 4
    n = struct.unpack(">I", data[body : body + 4])[0]
    out: list[tuple[int, int, int]] = []
    cur = body + 4
    for _ in range(n):
        first_chunk, samples_per_chunk, sample_desc_idx = struct.unpack(
            ">III", data[cur : cur + 12]
        )
        out.append((first_chunk, samples_per_chunk, sample_desc_idx))
        cur += 12
    return out


def _expand_samples_per_chunk(stsc_entries: list[tuple[int, int, int]], total_chunks: int) -> list[int]:
    """把 stsc 的 first_chunk-runs 展开成"每个 chunk 内 sample 数"列表。"""
    if not stsc_entries or total_chunks <= 0:
        return [0] * total_chunks
    out = [0] * total_chunks
    for i, (first_chunk, spc, _desc) in enumerate(stsc_entries):
        next_first = stsc_entries[i + 1][0] if i + 1 < len(stsc_entries) else total_chunks + 1
        for c in range(first_chunk, next_first):
            if 1 <= c <= total_chunks:
                out[c - 1] = spc
    return out


def _decode_tx3g_sample(sample: bytes) -> str:
    """tx3g (mov_text) sample = 2-byte BE length + UTF-8 text body。"""
    if len(sample) < 2:
        return ""
    n = struct.unpack(">H", sample[:2])[0]
    if n <= 0:
        return ""
    return sample[2 : 2 + n].decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# 文本清洗（V7 第 1 轮："去除明显空白噪声 + 形成可入库纯文本"）
# ---------------------------------------------------------------------------
_WS_RUN = re.compile(r"[ \t]+")


def _clean_text_pieces(pieces: list[str]) -> str:
    cleaned: list[str] = []
    for raw in pieces:
        if not raw:
            continue
        # 行内多空格 → 单空格；保留行内非空可见字符
        lines = [_WS_RUN.sub(" ", ln).strip() for ln in raw.splitlines()]
        body = "\n".join(ln for ln in lines if ln)
        if body:
            cleaned.append(body)
    if not cleaned:
        return ""
    # 段间用单个空行分隔，杜绝多空行堆积
    joined = "\n\n".join(cleaned)
    # 合并 3+ 连续换行 → 2
    joined = re.sub(r"\n{3,}", "\n\n", joined).strip()
    return joined


# ---------------------------------------------------------------------------
# 顶层入口
# ---------------------------------------------------------------------------
_SUBTITLE_HANDLER_TYPES = {"sbtl", "subt", "text"}


def extract_text_from_mp4(mp4_path: str | Path) -> dict:
    """
    主出口：从本地 `.mp4` 抽 mov_text 字幕文本。

    返回（永远 dict，不抛异常给上游 MCP server）：
        {
            "ok": bool,
            "text": str,                # 可入库纯文本（仅 ok=True 时为非空）
            "source_id": str,           # 来源标识（文件名）
            "source_path": str,         # 绝对路径
            "format": "mov_text",       # 本轮唯一支持的字幕格式
            "sample_count": int,        # 抽出 sample 数（清洗后非空）
            "error": str,               # 失败原因（ok=True 时为 ""）
        }
    """
    p = Path(mp4_path)
    base_meta = {
        "source_id": p.name,
        "source_path": str(p.resolve()) if p.exists() else str(p),
        "format": "mov_text",
        "sample_count": 0,
        "text": "",
    }

    if not p.is_file():
        return {"ok": False, "error": f"mp4 file not found: {p}", **base_meta}
    if p.suffix.lower() != ".mp4":
        return {"ok": False, "error": f"not a .mp4 file: {p.suffix}", **base_meta}

    try:
        data = p.read_bytes()
    except OSError as e:
        return {"ok": False, "error": f"read failed: {e}", **base_meta}
    if not data:
        return {"ok": False, "error": "empty mp4 file", **base_meta}

    # 顶层 box 列表
    top: list[_Box] = []
    pos = 0
    try:
        while pos < len(data):
            b = _read_box(data, pos)
            top.append(b)
            if b.size <= 0:
                break
            pos += b.size
    except ValueError as e:
        return {"ok": False, "error": f"malformed mp4: {e}", **base_meta}

    moov = _find(top, "moov")
    if moov is None:
        return {"ok": False, "error": "no moov box (not a valid mp4 / fragmented mp4 unsupported)", **base_meta}

    traks = [b for b in _children(data, moov) if b.type == "trak"]
    if not traks:
        return {"ok": False, "error": "moov has no trak", **base_meta}

    pieces: list[str] = []
    for trak in traks:
        mdia = _walk(data, trak, ["mdia"])
        if mdia is None:
            continue
        hdlr = _find(_children(data, mdia), "hdlr")
        if hdlr is None:
            continue
        handler_type = _parse_hdlr_handler_type(data, hdlr)
        if handler_type not in _SUBTITLE_HANDLER_TYPES:
            continue

        stbl = _walk(data, mdia, ["minf", "stbl"])
        if stbl is None:
            continue
        kids = _children(data, stbl)
        stsz = _find(kids, "stsz")
        stsc = _find(kids, "stsc")
        stco = _find(kids, "stco")
        co64 = _find(kids, "co64")
        if stsz is None or stsc is None or (stco is None and co64 is None):
            continue

        sizes = _parse_stsz(data, stsz)
        stsc_entries = _parse_stsc(data, stsc)
        chunk_offsets = _parse_co64(data, co64) if co64 is not None else _parse_stco(data, stco)  # type: ignore[arg-type]
        spc = _expand_samples_per_chunk(stsc_entries, len(chunk_offsets))

        sample_idx = 0
        for chunk_i, ch_off in enumerate(chunk_offsets):
            n_in_chunk = spc[chunk_i] if chunk_i < len(spc) else 0
            cur = ch_off
            for _ in range(n_in_chunk):
                if sample_idx >= len(sizes):
                    break
                sz = sizes[sample_idx]
                if sz <= 0 or cur + sz > len(data):
                    sample_idx += 1
                    continue
                txt = _decode_tx3g_sample(data[cur : cur + sz])
                if txt.strip():
                    pieces.append(txt)
                cur += sz
                sample_idx += 1

    text = _clean_text_pieces(pieces)
    if not text:
        return {
            "ok": False,
            "error": "no decodable mov_text subtitle samples in any trak",
            **base_meta,
        }

    base_meta["text"] = text
    base_meta["sample_count"] = len(pieces)
    return {"ok": True, "error": "", **base_meta}
