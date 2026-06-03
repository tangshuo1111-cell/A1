"""V11 R1：视频 URL 链能力层。

唯一对外入口：`url_fetch.fetch_video_text(url)`。
对调用方（middle_agent runtime）暴露 **结构化结果**，
任何失败都不抛异常（与 V7 R2 入 KB 链路风格保持一致）。
"""
