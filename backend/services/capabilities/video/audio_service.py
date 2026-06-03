"""统一视频音频提取能力。

网页视频 / 本地视频后续都应通过服务层提供的音频文件进入切段与 ASR，
避免工具层把可复用的音频处理细节各自维护一套。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def extract_audio_wav_for_asr(path: Path) -> tuple[Path | None, str, str, str]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return (
            None,
            "ffmpeg_dependency_missing",
            "未找到 ffmpeg 可执行文件，无法把本地视频转换为 ASR 可用音频",
            "安装 FFmpeg 并把 ffmpeg 加入 PATH",
        )
    fd, tmp_name = tempfile.mkstemp(prefix="v16_local_video_asr_", suffix=".wav")
    os.close(fd)
    out_path = Path(tmp_name)
    cmd = [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "wav",
        str(out_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=180)
    except (subprocess.SubprocessError, OSError) as e:
        out_path.unlink(missing_ok=True)
        return None, "audio_extract_failed", f"本地视频音轨提取失败: {e}", "检查 FFmpeg 是否可用，或确认视频容器/编码格式"
    if proc.returncode != 0 or not out_path.exists() or out_path.stat().st_size <= 0:
        stderr = (proc.stderr or b"").decode("utf-8", errors="replace")[:500]
        out_path.unlink(missing_ok=True)
        return None, "audio_extract_failed", stderr or "ffmpeg 提取音轨失败", "检查视频文件是否损坏，或确认 ffmpeg 可以读取该 MP4"
    return out_path, "", "", ""
