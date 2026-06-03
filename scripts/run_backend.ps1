#Requires -Version 5.1
<#
.SYNOPSIS
  启动 FastAPI 后端（开发用）。

.DESCRIPTION
  - 从项目根读取 .env（由 Python python-dotenv 在 import settings 时加载）。
  - 与 ``python scripts/run_dev.py --backend`` 一致：**PYTHONPATH** 仅追加 ``backend/``，
    以便 ``python -m uvicorn api.main:app`` 在**仓库根** cwd 下解析 ``api.main``。
  - 位置：``scripts/`` — 在**项目根**通过 PowerShell 调用。

.NOTES
  用法（在项目根）:
    .\scripts\run_backend.ps1
#>
$ErrorActionPreference = "Stop"
chcp 65001 > $null
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONIOENCODING = "utf-8"
$root = (Resolve-Path (Split-Path -Parent $PSScriptRoot)).Path
$backendRoot = Join-Path $root "backend"
if (-not (Test-Path (Join-Path $backendRoot "api\main.py"))) {
    throw "未找到后端入口文件: $(Join-Path $backendRoot 'api\main.py')"
}

$sep = [IO.Path]::PathSeparator
if ($env:PYTHONPATH) {
  $env:PYTHONPATH = "$backendRoot$sep$env:PYTHONPATH"
} else {
  $env:PYTHONPATH = $backendRoot
}
Set-Location $root

$hostAddr = $env:API_HOST
if (-not $hostAddr) { $hostAddr = "127.0.0.1" }
$port = $env:API_PORT
if (-not $port) { $port = "8000" }

Write-Host "[run_backend] PYTHONPATH=$env:PYTHONPATH" -ForegroundColor DarkGray
Write-Host "[run_backend] cwd=$root" -ForegroundColor DarkGray
Write-Host "Starting uvicorn api.main:app at http://${hostAddr}:${port}/ (POST /chat/agno)" -ForegroundColor Cyan
python -m uvicorn api.main:app --host $hostAddr --port $port --reload
