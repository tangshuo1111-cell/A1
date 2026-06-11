from __future__ import annotations

import pytest

import video.url_fetch_ytdlp as ytdlp_mod


def test_default_test_harness_blocks_real_ytdlp_network() -> None:
    with pytest.raises(AssertionError, match="real yt-dlp network path is blocked"):
        ytdlp_mod._yt_dlp_extract_info("https://www.bilibili.com/video/BV1guard0001", ydl_opts={})
