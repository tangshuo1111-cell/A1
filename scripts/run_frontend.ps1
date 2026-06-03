#Requires -Version 5.1
<#
.SYNOPSIS
  启动 Next.js 开发服务器。

.DESCRIPTION
  V9 R3：唯一默认前端启动脚本。
  - 前端真实路径：`frontend\`（已废弃重复的 `web\`）。
  - 默认通过 `lib/api.ts: postChat` 连后端 `POST /chat/agno`（V9 R3 唯一公开 chat 主路由）。
  - 需在 frontend 目录配置环境（如有 `.env.example` 可复制为 `.env.local` 配置 `BACKEND_URL`）。
#>
$ErrorActionPreference = "Stop"
chcp 65001 > $null
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONIOENCODING = "utf-8"
$root = (Resolve-Path (Split-Path -Parent $PSScriptRoot)).Path
$webDir = Join-Path $root "frontend"

if (-not (Test-Path $webDir)) {
    throw "未找到前端目录: $webDir"
}

Set-Location $webDir
Write-Host "[V9 R3] frontend cwd=$webDir" -ForegroundColor DarkGray
Write-Host "[V9 R3] 前端默认 postChat 路径 = /chat/agno（见 lib/api.ts）" -ForegroundColor DarkGray

if (-not (Test-Path "node_modules")) {
    Write-Host "Running npm install..." -ForegroundColor Yellow
    npm install
}
npm run dev
