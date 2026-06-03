"""
V7 第 1 轮测试 fixture：手工 pack 一个最小有效的 .mp4 文件，包含 mov_text 字幕轨。

为什么手写 packer：
- 项目本轮明确不依赖 ffmpeg / ASR 模型 / 外部 API；
- mov_text 字幕轨方案要求测试时也能"真实"拿到一个含字幕的 .mp4；
- 用纯 Python `struct` 直接 pack ISO Base Media File Format box 树即可，
  生成的 .mp4 完全自包含、跨平台、不需要任何外部工具。

生成的 mp4 结构（最小但合规）：
    ftyp(major='isom', compat=['isom','iso2'])
    moov
        mvhd
        trak
            tkhd
            mdia
                mdhd
                hdlr (handler_type='sbtl' 字幕轨)
                minf
                    nmhd
                    dinf/dref/url(self_contained)
                    stbl
                        stsd (1 entry, 占位 tx3g 头)
                        stts (1 entry, 全部 sample 共用一个 duration)
                        stsc (1 entry, 全在 1 个 chunk)
                        stsz (sample_size=0, 每 sample 长度可变)
                        stco (1 chunk_offset)
    mdat
        [tx3g sample 1: 2B BE length + UTF-8 text]
        [tx3g sample 2: 2B BE length + UTF-8 text]
        ...

本 packer 与 `tools.video.subtitle_extractor` 是配对的：
    pack 的字节序列 → extractor 解析 → 还原回最初的字幕文本。
"""

from __future__ import annotations

import struct
from pathlib import Path


def _box(btype: str, body: bytes) -> bytes:
    """普通 box：4B size + 4B type + body。"""
    size = 8 + len(body)
    return struct.pack(">I4s", size, btype.encode("ascii")) + body


def _ftyp() -> bytes:
    body = b"isom" + struct.pack(">I", 0x200) + b"isom" + b"iso2"
    return _box("ftyp", body)


_MATRIX_UNITY = struct.pack(
    ">9I",
    0x00010000, 0, 0,
    0, 0x00010000, 0,
    0, 0, 0x40000000,
)


def _mvhd(timescale: int = 1000, duration: int = 4000, next_track_id: int = 2) -> bytes:
    body = (
        struct.pack(">I", 0)            # version + flags
        + struct.pack(">II", 0, 0)      # creation, modification
        + struct.pack(">II", timescale, duration)
        + struct.pack(">i", 0x00010000) # rate=1.0
        + struct.pack(">h", 0x0100)     # volume=1.0
        + struct.pack(">H", 0)          # reserved
        + b"\x00" * 8                   # reserved
        + _MATRIX_UNITY
        + b"\x00" * 24                  # pre_defined
        + struct.pack(">I", next_track_id)
    )
    return _box("mvhd", body)


def _tkhd(track_id: int = 1, duration: int = 4000) -> bytes:
    body = (
        struct.pack(">I", 0x00000007)   # version=0, flags = enabled+inMovie+inPreview
        + struct.pack(">II", 0, 0)      # creation, modification
        + struct.pack(">II", track_id, 0)
        + struct.pack(">I", duration)
        + b"\x00" * 8                   # reserved
        + struct.pack(">hhhH", 0, 0, 0x0100, 0)  # layer, alt_group, volume, reserved
        + _MATRIX_UNITY
        + struct.pack(">II", 0, 0)      # width, height (subtitle: 0)
    )
    return _box("tkhd", body)


def _mdhd(timescale: int = 1000, duration: int = 4000) -> bytes:
    body = (
        struct.pack(">I", 0)            # version + flags
        + struct.pack(">II", 0, 0)      # creation, modification
        + struct.pack(">II", timescale, duration)
        + struct.pack(">H", 0x55C4)     # language: 'und'
        + struct.pack(">H", 0)          # pre_defined
    )
    return _box("mdhd", body)


def _hdlr(handler_type: str = "sbtl", name: str = "Subtitle") -> bytes:
    name_bytes = name.encode("utf-8") + b"\x00"
    body = (
        struct.pack(">I", 0)            # version + flags
        + struct.pack(">I", 0)          # pre_defined
        + handler_type.encode("ascii")
        + b"\x00" * 12                  # reserved
        + name_bytes
    )
    return _box("hdlr", body)


def _nmhd() -> bytes:
    return _box("nmhd", struct.pack(">I", 0))


def _dref() -> bytes:
    # entry: 'url ' with self-contained flag (0x000001)
    url_box = _box("url ", struct.pack(">I", 0x000001))
    body = struct.pack(">II", 0, 1) + url_box  # ver+flags, entry_count=1
    return _box("dref", body)


def _dinf() -> bytes:
    return _box("dinf", _dref())


def _stsd_minimal_tx3g() -> bytes:
    """最小 tx3g sample entry（仅占位，subtitle_extractor 不解析其内部细节）。"""
    # tx3g 最小 entry：8 byte SampleEntry header + 6 reserved + 2 data_ref_idx
    # + 4 displayFlags + 1 + 1 + 4 background_color + 8 default_text_box + 12 default_style
    tx3g_body = (
        b"\x00" * 6                    # reserved
        + struct.pack(">H", 1)         # data_reference_index
        + struct.pack(">I", 0)         # displayFlags
        + b"\x01\xff"                  # h_justify, v_justify
        + b"\x00\x00\x00\xff"          # background_color_rgba
        + struct.pack(">hhhh", 0, 0, 0, 0)   # default_text_box
        + struct.pack(">HHHBB", 0, 0, 0, 0, 12)  # startChar, endChar, font_id, face, font_size
        + b"\xff\xff\xff\xff"          # text_color_rgba
    )
    tx3g_entry = _box("tx3g", tx3g_body)
    body = struct.pack(">II", 0, 1) + tx3g_entry  # ver+flags, entry_count=1
    return _box("stsd", body)


def _stts(sample_count: int, per_sample_duration: int = 1000) -> bytes:
    body = (
        struct.pack(">I", 0)
        + struct.pack(">I", 1)
        + struct.pack(">II", sample_count, per_sample_duration)
    )
    return _box("stts", body)


def _stsc(samples_per_chunk: int) -> bytes:
    body = (
        struct.pack(">I", 0)
        + struct.pack(">I", 1)                       # entry_count=1
        + struct.pack(">III", 1, samples_per_chunk, 1)
    )
    return _box("stsc", body)


def _stsz(sizes: list[int]) -> bytes:
    body = (
        struct.pack(">I", 0)
        + struct.pack(">II", 0, len(sizes))          # sample_size=0, sample_count
        + b"".join(struct.pack(">I", s) for s in sizes)
    )
    return _box("stsz", body)


def _stco(chunk_offset: int) -> bytes:
    body = (
        struct.pack(">I", 0)
        + struct.pack(">I", 1)                        # entry_count=1
        + struct.pack(">I", chunk_offset)
    )
    return _box("stco", body)


def _stbl(sample_sizes: list[int], chunk_offset_placeholder: int = 0) -> bytes:
    return _box(
        "stbl",
        _stsd_minimal_tx3g()
        + _stts(len(sample_sizes))
        + _stsc(len(sample_sizes))
        + _stsz(sample_sizes)
        + _stco(chunk_offset_placeholder),
    )


def _build_mdat_payload(text_lines: list[str]) -> tuple[bytes, list[int]]:
    """每个 sample = 2B BE length + UTF-8 text。返回 (mdat_body, [sample_size, ...])。"""
    sample_sizes: list[int] = []
    parts: list[bytes] = []
    for line in text_lines:
        body = line.encode("utf-8")
        sample = struct.pack(">H", len(body)) + body
        parts.append(sample)
        sample_sizes.append(len(sample))
    return b"".join(parts), sample_sizes


def build_minimal_mp4_with_subtitles(text_lines: list[str]) -> bytes:
    """
    生成一个最小有效的 .mp4 字节序列（含 1 条 mov_text 字幕轨 + 给定字幕行）。

    实现要点：
    1. 先按 chunk_offset=0 占位计算 stbl/minf/mdia/trak/moov/ftyp 的实际尺寸；
    2. 算出 mdat 的 data 字段相对文件头的真实绝对偏移
       (= ftyp_size + moov_size + 8 mdat_header)；
    3. 用真实偏移 **重 pack** stbl 一次（其它 box 大小不变，因为 stco 始终 4B），
       重 pack moov / trak / mdia / minf / stbl 全部上层；
    4. 拼 ftyp + moov + mdat。
    """
    if not text_lines:
        raise ValueError("至少要有 1 条字幕")

    mdat_body, sample_sizes = _build_mdat_payload(text_lines)

    # —— 第一轮：用 placeholder=0 计算尺寸 ——
    def _moov_with_offset(offset: int) -> bytes:
        stbl = _stbl(sample_sizes, chunk_offset_placeholder=offset)
        minf = _box("minf", _nmhd() + _dinf() + stbl)
        mdia = _box("mdia", _mdhd() + _hdlr() + minf)
        trak = _box("trak", _tkhd() + mdia)
        return _box("moov", _mvhd() + trak)

    ftyp = _ftyp()
    moov_placeholder = _moov_with_offset(0)
    real_chunk_offset = len(ftyp) + len(moov_placeholder) + 8  # +8 = mdat header
    moov = _moov_with_offset(real_chunk_offset)
    # moov 的 size 不会因为 stco 内 4 字节值改变而变化
    assert len(moov) == len(moov_placeholder), (
        "moov size drift after stco rewrite — packer 实现错"
    )
    mdat = _box("mdat", mdat_body)
    return ftyp + moov + mdat


def write_minimal_mp4_with_subtitles(path: str | Path, text_lines: list[str]) -> Path:
    """方便函数：把生成的 .mp4 字节写入到目标路径并返回 `Path`。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(build_minimal_mp4_with_subtitles(text_lines))
    return p
