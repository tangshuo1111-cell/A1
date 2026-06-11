"""General fast lane canned/local term helpers."""

from __future__ import annotations

import re
from typing import Any

LOCAL_TERM_EXPLAINS: dict[str, str] = {
    "cors": "CORS 是浏览器的跨域安全规则：前端想访问另一个域名/端口的后端时，后端必须明确允许。",
    "docker": "Docker 是把程序和运行环境打包到容器里，方便在不同机器上用同一套方式启动。",
    ".env": ".env 是本地环境变量文件，用来放数据库地址、模型 key、工具 key 这类不能写进代码的配置。",
    "env": ".env 是本地环境变量文件，用来放数据库地址、模型 key、工具 key 这类不能写进代码的配置。",
    "bearer": "Bearer 是一种接口鉴权方式：请求头里带上 token，后端确认 token 正确后才放行。",
    "admin key": "Admin Key 是管理接口的专用密钥，作用是避免普通用户调用危险的内部管理能力。",
    "反向代理": "反向代理是挡在后端前面的入口服务，负责把浏览器请求转发给真正的应用服务器。",
    "health check": "Health check 是健康检查接口，用来快速确认后端、数据库等关键组件是否还活着。",
    "ci": "CI 是自动检查代码的流程，通常会在提交后自动跑测试、类型检查和质量检查。",
    "cd": "CD 是自动发布流程，通常负责把通过检查的代码部署到服务器。",
}


def try_canned_fast_answer(message: str) -> tuple[str, dict[str, Any]] | None:
    msg = (message or "").strip()
    compact = re.sub(r"\s+", "", msg)
    if compact in {"你好", "您好", "hello", "hi", "嗨"}:
        return "你好，我在。你可以直接把问题、链接或资料发过来。", {"fast_path": "local_greeting"}
    if len(compact) <= 20 and any(x in compact for x in ("随便聊", "聊两句", "闲聊", "打个招呼")):
        return "好呀，我在这儿。你想轻松聊点什么，或者继续推进项目，都可以直接开口。", {"fast_path": "local_smalltalk"}
    lower = msg.lower()
    if ("解释" in msg or "什么是" in msg or "一句话" in msg) and len(msg) <= 80:
        for key, answer in LOCAL_TERM_EXPLAINS.items():
            if key in lower or key in msg:
                return answer, {"fast_path": "local_term_explain", "fast_term": key}
    return None
