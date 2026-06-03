# Light MAQA — 前端（Next.js 15 + React 19）

## 概览

单页面聊天界面，通过 `/chat/agno` API 与后端三 Agent 主链交互。

## 目录结构

```
frontend/
├── app/                    Next.js App Router
│   ├── layout.tsx          根布局
│   └── page.tsx            唯一页面入口
├── components/
│   ├── chat/               聊天核心组件
│   │   ├── ChatExperience  容器（hooks 组合）
│   │   ├── ChatMessageList 消息列表渲染
│   │   ├── ChatComposer    输入框 + 发送
│   │   ├── ChatEmptyState  空态
│   │   ├── ContextRail     侧栏调试面板
│   │   ├── VideoCookiesGuide  cookies 上传引导
│   │   └── cookies-guide/  引导子组件
│   └── layout/
│       └── AppHeader.tsx   顶部导航
├── hooks/                  自定义 Hooks
│   ├── useChatSession.ts   会话/消息状态
│   ├── useHealthStatus.ts  后端健康检查
│   ├── useVideoGuide.ts    视频 cookies 弹卡逻辑
│   └── useCookiesUpload.ts cookies 上传/删除
├── lib/
│   ├── api.ts              后端 API 封装（内部走 client.ts）
│   ├── client.ts           fetch 包装 + `resolveApiUrl` + Bearer + 错误类
│   ├── types.ts            共享 TypeScript 类型
│   ├── contextMeta/        extra 字段提取（按维度拆分）
│   ├── answerSanitizer.ts  回答文本清洗
│   └── videoUrl.ts         URL 白名单/提取
└── public/                 静态资源
```

## 环境变量（`frontend/.env.local`，勿提交）

与 `next.config.ts` / `lib/client.ts` 的真实行为对齐：

1. **默认**：浏览器请求走 **同源** ` /api-proxy/*`，由 Next **rewrite** 转到后端（避免本地 CORS 配置负担）。
2. **`BACKEND_URL`**：仅服务端 / dev server 使用；控制 rewrite 目标（默认 `http://127.0.0.1:8000`）。示例：`BACKEND_URL=http://127.0.0.1:8000`。
3. **`NEXT_PUBLIC_API_BASE_URL`**：若设置，则 **浏览器直连** 该后端基址（需后端 CORS 放行）；未设置则继续走 `/api-proxy`。
4. **`NEXT_PUBLIC_API_BEARER_TOKEN`**：与后端 `API_BEARER_TOKEN` 对齐时填入；`client.ts` 会自动附加 `Authorization: Bearer ...`；留空则不发送。

视频 cookies：**上传**路径为 `POST /config/video_cookies/upload`（经 `lib/api.ts` 调用；见 `useCookiesUpload`）。

## 本地开发

```powershell
cd frontend
npm install
npm run dev          # 启动 http://localhost:3000
```

## Lint

```powershell
npm run lint         # eslint（pre-commit 已配置 --max-warnings=0）
```

## 构建

```powershell
npm run build        # next build（Turbopack）
npm run start        # 生产模式
```

## 与后端的关系

- 后端启动后前端才能正常对话（健康检查会自动检测）。
- 主链 API：`POST /chat/agno`（详见后端 `api/routes/chat_agno.py`）。
- Cookies：`POST /config/video_cookies/upload`（multipart）；状态/删除见 `lib/api.ts` 同前缀路由。
