#Requires -Version 5.1
<#
.SYNOPSIS
  V9 R3 端到端 smoke：从 Next.js dev server (默认 3000) 经 rewrites 打到 backend 的唯一公开 chat 主路由 POST /chat/agno。

.DESCRIPTION
  V9 R3"前端真实可用"硬证据脚本：
    1) GET http://127.0.0.1:3000/                       → 必须 HTTP 200，HTML 含 <title>Light MAQA</title>
    2) POST http://127.0.0.1:3000/api-proxy/chat/agno   → 必须 HTTP 200，extra.lane='agno_basic' 且含 v6_takeover/v7_* 关键字段

  本脚本**不替代** smoke_backend.ps1（直接打 8000）；它的存在意义是：
  额外证明"浏览器经 Next 同源转发"这一层也真的命中了默认主体（V9 R3 已无可绕到的旧链路由）。

.PARAMETER FrontBase
  Next dev server 根 URL，默认 http://127.0.0.1:3000

.PARAMETER BackHealthBase
  backend 健康检查根 URL（用于打印参考；默认 http://127.0.0.1:8000）

.NOTES
  前置：先跑 .\scripts\run_backend.ps1 与 .\scripts\run_frontend.ps1 各启一个进程。
#>
param(
    [string]$FrontBase = "http://127.0.0.1:3000",
    [string]$BackHealthBase = "http://127.0.0.1:8000"
)
$ErrorActionPreference = "Stop"
chcp 65001 > $null
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONIOENCODING = "utf-8"

Write-Host "[V9 R3 E2E] backend health (参考):" -ForegroundColor DarkCyan
try {
    $h = Invoke-RestMethod -Uri "$BackHealthBase/health" -Method Get -TimeoutSec 5
    Write-Host "  health.status = $($h.status)"
} catch {
    Write-Host "  WARN: backend /health unreachable ($($_.Exception.Message))" -ForegroundColor Yellow
}

Write-Host "`n[V9 R3 E2E] STEP 1: GET $FrontBase/  → 期望 HTTP 200 + 真 HTML" -ForegroundColor Cyan
$pageResp = Invoke-WebRequest -Uri "$FrontBase/" -Method Get -UseBasicParsing -TimeoutSec 30
if ($pageResp.StatusCode -ne 200) {
    Write-Error "STEP 1 FAIL: 首屏 GET 返回 HTTP $($pageResp.StatusCode)（前端默认页未起来）"
}
$titleMatch = [regex]::Match($pageResp.Content, '<title[^>]*>(.*?)</title>')
$pageTitle = if ($titleMatch.Success) { $titleMatch.Groups[1].Value } else { '<no-title>' }
Write-Host "  HTTP 200, bytes=$($pageResp.RawContentLength), title=`"$pageTitle`""
if ($pageTitle -ne "Light MAQA") {
    Write-Error "STEP 1 FAIL: <title> 不是 Light MAQA（疑似被代理掉），实际=`"$pageTitle`""
}

Write-Host "`n[V9 R3 E2E] STEP 2: POST $FrontBase/api-proxy/chat/agno  → 期望命中默认主体" -ForegroundColor Cyan
$body = @{
    message    = "V9 R3 端到端 smoke：你好"
    session_id = "v9r3-smoke-e2e"
} | ConvertTo-Json -Compress
$chatResp = Invoke-WebRequest -Uri "$FrontBase/api-proxy/chat/agno" -Method Post `
    -Body $body -ContentType "application/json; charset=utf-8" `
    -UseBasicParsing -TimeoutSec 60
if ($chatResp.StatusCode -ne 200) {
    Write-Error "STEP 2 FAIL: HTTP $($chatResp.StatusCode)"
}
$rid = $chatResp.Headers.'X-Request-Id'
$j = $chatResp.Content | ConvertFrom-Json
Write-Host "  HTTP 200, request_id=$rid, ok=$($j.ok), primary_path=$($j.primary_path)"

# 默认主体硬证据
if ($j.extra -eq $null) {
    Write-Error "STEP 2 FAIL: 响应无 extra 字段（默认主体未命中）"
}
$lane = $j.extra.lane
if ($lane -ne "agno_basic") {
    Write-Error "STEP 2 FAIL: extra.lane=`"$lane`"，应为 `"agno_basic`"（默认主体未命中）"
}
Write-Host "  extra.lane = $lane  (✔ default main body)"

# V6 / V7 关键字段硬证据（任一缺失都算回归）
$mustExist = @(
    'v6_takeover',
    'v6_main_pan_renwu',
    'v7_middle_pan_video_decision',
    'v8_middle_history_used'
)
$missing = @()
foreach ($k in $mustExist) {
    if ($j.extra.PSObject.Properties[$k] -eq $null) {
        $missing += $k
    }
}
if ($missing.Count -gt 0) {
    Write-Error "STEP 2 FAIL: 响应 extra 缺少 V6/V7 关键字段：$($missing -join ', ')"
}
Write-Host "  extra 含 V6/V7 关键字段：$($mustExist -join ', ')"

Write-Host "`n[V9 R3 E2E] PASS  (前端真页面 200 + 经 rewrites 命中默认主体 + V6/V7 字段齐全)" -ForegroundColor Green
