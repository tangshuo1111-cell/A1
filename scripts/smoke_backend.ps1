#Requires -Version 5.1
<#
.SYNOPSIS
  最小 backend smoke：GET /health + POST /chat/agno（V9 R3 唯一默认主体）。
.PARAMETER Base
  API 根 URL，默认 http://127.0.0.1:8000
.NOTES
  V9 R3：旧 LangGraph 主链（POST /chat、POST /chat/async、GET /tasks/{id}）已物理删除，
  无替代脚本，无回退入口；上述路径会返回 HTTP 404。
#>
param(
    [string]$Base = "http://127.0.0.1:8000"
)
$ErrorActionPreference = "Stop"
chcp 65001 > $null
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONIOENCODING = "utf-8"

Write-Host "GET $Base/health" -ForegroundColor Cyan
$h = Invoke-RestMethod -Uri "$Base/health" -Method Get
$h | ConvertTo-Json -Depth 6

Write-Host "`nPOST $Base/chat/agno" -ForegroundColor Cyan
$body = @{
    message    = "你好，做一次连通性自检"
    session_id = $null
} | ConvertTo-Json -Compress
$c = Invoke-RestMethod -Uri "$Base/chat/agno" -Method Post -Body $body -ContentType "application/json; charset=utf-8"
Write-Host "ok=$($c.ok) primary_path=$($c.primary_path) pipeline_ok=$($c.pipeline_ok) session_id=$($c.session_id)"
$ans = [string]$c.answer
if ($ans.Length -gt 200) { $ans = $ans.Substring(0, 200) + "..." }
Write-Host "answer preview: $ans"
if (-not $c.ok) {
    Write-Error "POST /chat/agno returned ok=false"
}
