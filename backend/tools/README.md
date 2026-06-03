# backend/tools

## Responsibilities

- 承载工具适配层，是系统的 provider wrapper / adapter 层
- 负责“拿内容”：抓网页、读文档、抽字幕、跑 ASR、调搜索、调 OCR
- 统一工具输入适配、参数校验、结果包装、provider 接缝
- 为 `services/` 和 `agents/` 提供可复用的底层工具能力

## Boundary / What not to put here

- 不要把完整业务编排重新塞进工具层
- 不要把自治决策、lane 切换、材料充分性判断放在工具层
- 不要把任务状态机、队列编排、worker runtime 细节放在工具层
- 工具层只做适配器 / provider wrapper，不得再次承载完整业务编排

## Owned files

- `backend/tools/document/`
- `backend/tools/ocr/`
- `backend/tools/asr/`
- `backend/tools/web/`
- `backend/tools/video/`
- `backend/tools/search/`

## Files that must not keep growing

- `backend/tools/video/extract_web_video_subtitle.py`
  只应保留 URL 解析、白名单判断、cookie 注入、tool result 包装，不应继续吸收切段、并发 ASR、队列调度和 provider chain 策略。
- `backend/tools/video/extract_local_video_subtitle.py`
  只应保留本地路径校验、文件大小检查、tool result 包装，不应继续吸收 duration probe、后台化策略和重处理核心。
- `backend/tools/video/` 目录
  应继续保持“输入适配 + 调服务”的瘦层定位，不应重新膨胀成视频业务主编排层。
