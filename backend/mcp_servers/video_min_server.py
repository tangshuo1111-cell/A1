"""
首条业务型 MCP Server（stdio + FastMCP），暴露 `video_to_text` 业务能力。

明确边界：
- 这是当前**收口唯一**的业务型 MCP server——服务于「本地 .mp4 → 字幕文本」这条链；
- 唯一业务型 tool 是 `video_to_text`（**不**是 ping / echo / hello world / demo）；
- 该 tool 只负责"产出可入库纯文本"，**不**直接负责入库（入库走现有 ingest 链）；
- 唯一最小视频来源 = 本地 `.mp4` 路径；
- 唯一最小转文本方案 = 字幕提取链（mov_text / tx3g），无 ASR、无外部 API、无 ffmpeg。

启动方式（一般由 stdio 客户端自动拉起）：
    python -m mcp_servers.video_min_server
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from tools.video import extract_text_from_mp4

app = FastMCP(
    "light_maqa_video_v7",
    instructions=(
        "LightMultiAgentQA V7 业务型 MCP Server。"
        "本 server 当前收口唯一业务能力：video_to_text —— 把本地 .mp4 容器内的 mov_text 字幕轨"
        "解码为可入库纯文本，并返回来源标识。"
        "本 server 不负责入库；入库走主链既有 ingest 链。"
    ),
)


@app.tool()
def video_to_text(mp4_path: str) -> str:
    """
    业务型 MCP tool：把本地 .mp4 容器内 mov_text(tx3g) 字幕轨解码为可入库纯文本。

    参数：
        mp4_path: 本地 .mp4 文件的绝对或相对路径。

    返回（JSON 字符串，便于 stdio MCP 透传）：
        {
            "ok": bool,
            "text": str,          # 可入库纯文本（仅 ok=True 时为非空）
            "source_id": str,     # 来源标识（文件名）
            "source_path": str,   # 绝对路径
            "format": "mov_text",
            "sample_count": int,
            "error": str,         # 失败原因（ok=True 时为 ""）
        }

    本 tool **不**是 ping / echo / demo：
    - 它真实读 .mp4 字节、真实解 ISO BMFF box、真实抽 mov_text 字幕样本；
    - 失败时返回明确错误信息，不伪装成功、不静默吞。
    """
    payload = extract_text_from_mp4(mp4_path)
    return json.dumps(payload, ensure_ascii=False)


def main() -> None:
    app.run(transport="stdio")


if __name__ == "__main__":
    main()
