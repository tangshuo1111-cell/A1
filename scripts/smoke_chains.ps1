#Requires -Version 5.1
<#
.SYNOPSIS
  默认主链三拍冒烟：POST /chat/agno —— V1 基础 / V2 本地知识 / V4 协作轨迹（Windows PowerShell）。
.DESCRIPTION
  需本机已启动 API（默认 http://127.0.0.1:8000）。与 `shuoming.md` 演示主口径对齐。
  V9 R3：旧 POST /chat 的 direct/kb/tool 三链已物理删除，无对照脚本，无回退入口。
  用法（在仓库根目录）:
    .\scripts\smoke_chains.ps1
    .\scripts\smoke_chains.ps1 -BaseUrl "http://127.0.0.1:8000"
#>
param(
    [string]$BaseUrl = "http://127.0.0.1:8000"
)
$ErrorActionPreference = "Stop"
chcp 65001 > $null
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONIOENCODING = "utf-8"

function Invoke-Agno {
    param(
        [string]$Message,
        [string]$Session,
        [bool]$UseKnowledge = $false
    )
    $uri = "$BaseUrl/chat/agno"
    $body = @{
        message       = $Message
        session_id    = $Session
        use_knowledge = $UseKnowledge
    } | ConvertTo-Json -Compress
    return Invoke-RestMethod -Uri $uri -Method Post -Body $body -ContentType "application/json; charset=utf-8"
}

function Write-AgnoSummary {
    param($R)
    Write-Host "  ok=$($R.ok) primary_path=$($R.primary_path) pipeline_ok=$($R.pipeline_ok)"
    if ($R.extra) {
        $ex = $R.extra
        if ($ex.collaboration_trace) {
            $t = @($ex.collaboration_trace) -join " | "
            Write-Host "  collaboration_trace: $t"
        }
        if ($ex.v4_path_fingerprint) {
            Write-Host "  v4_path_fingerprint=$($ex.v4_path_fingerprint)"
        }
    }
}

Write-Host "=== LightMultiAgentQA smoke_chains (POST /chat/agno) ===" -ForegroundColor Cyan
Write-Host "BaseUrl: $BaseUrl`n" -ForegroundColor Gray

# 1) V1 基础问答
Write-Host "[1/3] V1 basic: 你好" -ForegroundColor Yellow
$d = Invoke-Agno -Message "你好" -Session "smoke-agno-v1" -UseKnowledge $false
Write-AgnoSummary $d

# 2) V2 本地知识（与 shuoming 演示表一致）
Write-Host "`n[2/3] V2 knowledge: use_knowledge=true, 项目代号是什么？" -ForegroundColor Yellow
$k = Invoke-Agno -Message "项目代号是什么？" -Session "smoke-agno-v2" -UseKnowledge $true
Write-AgnoSummary $k

# 3) V4 轨迹：任意一问即可观察 collaboration_trace（不依赖外网）
Write-Host "`n[3/3] V4 trace: 任意短问（看 extra 协作痕迹）" -ForegroundColor Yellow
$t = Invoke-Agno -Message "用一句话说明你是谁" -Session "smoke-agno-v4" -UseKnowledge $false
Write-AgnoSummary $t

Write-Host "`n完成。主验收仍以 shuoming.md 四文件 pytest 为准；V9 R3 已无旧 POST /chat 三链。" -ForegroundColor Green
