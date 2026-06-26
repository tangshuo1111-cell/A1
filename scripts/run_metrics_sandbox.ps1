#Requires -Version 5.1
<#
.SYNOPSIS
  一键跑产品指标隔离沙箱（北极星2 周报）。

.DESCRIPTION
  把本仓库指标沙箱的完整流程固化成防呆脚本，避免手工踩坑：
    1. 用固定 compose 项目名 `metrics_sandbox` 起隔离 PG（5433），
       绝不与主库 compose 复用 → 不会覆盖主 postgres 容器/端口。
    2. 等沙箱 PG healthy。
    3. 在后台拉起仅连沙箱库的 :8001 后端（EMBEDDING_ENABLED=0），等 /health=ok。
    4. 跑 scripts/run_metrics_sandbox_samples.py（--truncate-metrics --report）。
    5. 收尾按端口精确 Stop-Process 掉 :8001，避免后台后端残留。
  全程只触碰沙箱 5433 / :8001，不影响主链 8000 / 主库 5432。

.PARAMETER FakeLLM
  使用 FAKE_LLM 跑（默认 $false，即真实外部 LLM；需 backend/config/env.txt 已配 key）。

.PARAMETER Down
  跑完顺带 `compose down` 掉沙箱 PG（默认保留，便于复跑对照）。

.PARAMETER RefineV2
  开启 ENABLE_COMPLEX_REFINE_V2（003 answer_only 验收；默认关）。

.NOTES
  用法（项目根）:
    .\scripts\run_metrics_sandbox.ps1            # 真实 LLM 跑一轮并出周报
    .\scripts\run_metrics_sandbox.ps1 -FakeLLM   # 不打真实外部，仅验证管线
    .\scripts\run_metrics_sandbox.ps1 -RefineV2  # 003 行为修复验收
    .\scripts\run_metrics_sandbox.ps1 -Down      # 跑完销毁沙箱 PG
#>
param(
    [switch]$FakeLLM,
    [switch]$RefineV2,
    [switch]$Down
)

$ErrorActionPreference = "Stop"
chcp 65001 > $null
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$env:PYTHONIOENCODING = "utf-8"

$root = (Resolve-Path (Split-Path -Parent $PSScriptRoot)).Path
$backendRoot = Join-Path $root "backend"
$composeFile = Join-Path $root "docker-compose.metrics-sandbox.yml"
$sampleScript = Join-Path $root "scripts\run_metrics_sandbox_samples.py"
if (-not (Test-Path $composeFile)) { throw "未找到沙箱 compose: $composeFile" }
if (-not (Test-Path $sampleScript)) { throw "未找到样本脚本: $sampleScript" }

# 固定项目名，隔离于主库 compose（关键：防止覆盖主 postgres）
$project = "metrics_sandbox"
$sandboxApi = "http://127.0.0.1:8001"
$sandboxDb = "postgresql://light_maqa:light_maqa_dev@127.0.0.1:5433/light_maqa_metrics_sandbox"

$sep = [IO.Path]::PathSeparator
if ($env:PYTHONPATH) { $env:PYTHONPATH = "$backendRoot$sep$env:PYTHONPATH" } else { $env:PYTHONPATH = $backendRoot }
Set-Location $root

Write-Host "[sandbox] 1/5 起隔离 PG（项目名=$project，端口 5433）..." -ForegroundColor Cyan
docker compose -p $project -f $composeFile up -d | Out-Null

Write-Host "[sandbox] 2/5 等待沙箱 PG healthy..." -ForegroundColor Cyan
$pgReady = $false
for ($i = 0; $i -lt 30; $i++) {
    $state = (docker inspect -f '{{.State.Health.Status}}' "${project}-postgres-1" 2>$null)
    if ($state -eq "healthy") { $pgReady = $true; break }
    Start-Sleep -Seconds 2
}
if (-not $pgReady) { throw "沙箱 PG 未在超时内 healthy（容器 ${project}-postgres-1）" }

# 沙箱后端环境（仅本进程及其子进程，不污染主链）
$env:DATABASE_URL = $sandboxDb
$env:EMBEDDING_ENABLED = "0"
$env:TASK_TIMEOUT_SEC = "240"
$env:LIGHT_MAQA_FAKE_LLM = if ($FakeLLM) { "1" } else { "0" }
if ($RefineV2) { $env:ENABLE_COMPLEX_REFINE_V2 = "1" } else { Remove-Item Env:ENABLE_COMPLEX_REFINE_V2 -ErrorAction SilentlyContinue }

Write-Host "[sandbox] 3/5 后台拉起 :8001 后端（FAKE_LLM=$($env:LIGHT_MAQA_FAKE_LLM), REFINE_V2=$($env:ENABLE_COMPLEX_REFINE_V2)）..." -ForegroundColor Cyan
$be = Start-Process -FilePath "py" `
    -ArgumentList @("-3.12", "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", "8001") `
    -PassThru -WindowStyle Hidden

try {
    $beReady = $false
    for ($i = 0; $i -lt 40; $i++) {
        try {
            $h = Invoke-RestMethod -Uri "$sandboxApi/health" -TimeoutSec 5
            if ($h.status -eq "ok") { $beReady = $true; break }
        } catch { Start-Sleep -Seconds 2 }
    }
    if (-not $beReady) { throw ":8001 后端未在超时内就绪" }

    Write-Host "[sandbox] 4/5 跑样本 + 生成周报..." -ForegroundColor Cyan
    py -3.12 $sampleScript --api $sandboxApi --truncate-metrics --report
    $runExit = $LASTEXITCODE
}
finally {
    Write-Host "[sandbox] 5/5 收尾：停掉 :8001 后端..." -ForegroundColor Cyan
    # 按端口精确定位监听 PID（Start-Process 的句柄可能是父壳，端口法更可靠）
    $listenPid = (Get-NetTCPConnection -State Listen -LocalPort 8001 -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess)
    if ($listenPid) { Stop-Process -Id $listenPid -Force -ErrorAction SilentlyContinue }
    if ($be -and -not $be.HasExited) { Stop-Process -Id $be.Id -Force -ErrorAction SilentlyContinue }
    if ($Down) {
        Write-Host "[sandbox] 销毁沙箱 PG（-Down）..." -ForegroundColor DarkGray
        docker compose -p $project -f $composeFile down | Out-Null
    }
}

$report = Join-Path $root "_local\reports\metrics"
Write-Host ""
Write-Host "[sandbox] 完成。周报落点：$report\weekly_<日期>.{html,json}" -ForegroundColor Green
Write-Host "[sandbox] 主链未触碰：仅用了沙箱 PG(5433) 与 :8001。" -ForegroundColor Green
exit $runExit
