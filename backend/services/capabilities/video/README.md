# Video Capability Plane

Unified orchestration for web/local video probe, extract, ASR, background queue, and complex gather.

MiddleAgent and application layers must import from this package — not `tools.video.*` or legacy `services/video_*` at orchestration layers.

| Module | Role |
|---|---|
| `processing_service.py` | probe → sync ASR → background queue 统一状态机 |
| `web_video_extract_service.py` | 网页视频字幕/ASR 提取编排 |
| `local_video_extract_service.py` | 本地视频字幕/ASR 提取编排 |
| `early_video_support.py` | fast probe、tool→FetchVideoResult 适配 |
| `web_video_gather.py` | complex gather 并发 probe + tool |
| `mcp_video_support.py` | MCP video_to_text → pending |
| `video_decision.py` | 路径/URL 意图与 fetch 决策 |
| `path_signals.py` | .mp4 路径显式信号（无 agent 依赖） |
| `parallel_asr_service.py` | 分段并行 ASR |
| `background_executor.py` | 后台 ASR worker 执行 |
| `queue_dispatch.py` | 视频任务入队 |
| `provider_chain.py` | ASR provider 链 |
| `audio_service.py` / `duration_probe.py` / `segment_service.py` | 音视频基础设施 |

## Tool adapters

`tools/video/extract_*_subtitle.py` 仅注册 MCP schema 并 delegate 至本 plane。
