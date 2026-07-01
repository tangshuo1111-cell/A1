#Requires -Version 5.1
param(
    [Parameter(Mandatory = $true)][string]$Root,
    [Parameter(Mandatory = $true)][string]$BackendRoot,
    [Parameter(Mandatory = $true)][string]$DatabaseUrl,
    [Parameter(Mandatory = $true)][string]$FakeLLM,
    [Parameter(Mandatory = $true)][string]$RefineV2,
    [string]$ExitShadow = "0",
    [string]$Port = "8001"
)

$ErrorActionPreference = "Stop"
$env:PYTHONPATH = $BackendRoot
$env:DATABASE_URL = $DatabaseUrl
$env:EMBEDDING_ENABLED = "0"
$env:TASK_TIMEOUT_SEC = "240"
$env:LIGHT_MAQA_FAKE_LLM = $FakeLLM
$env:PYTHONIOENCODING = "utf-8"
if ($RefineV2 -eq "1") {
    $env:ENABLE_COMPLEX_REFINE_V2 = "1"
} elseif ($RefineV2 -eq "0") {
    $env:ENABLE_COMPLEX_REFINE_V2 = "0"
} else {
    Remove-Item Env:ENABLE_COMPLEX_REFINE_V2 -ErrorAction SilentlyContinue
}
if ($ExitShadow -eq "1") {
    $env:ENABLE_TURN_EXIT_GATE_SHADOW = "1"
} else {
    Remove-Item Env:ENABLE_TURN_EXIT_GATE_SHADOW -ErrorAction SilentlyContinue
}

Set-Location $Root
$preferredPython = Join-Path "D:\软件\Python312" "python.exe"
$pythonBin = $env:LIGHT_MAQA_PYTHON
if (-not $pythonBin) {
    if (Test-Path $preferredPython) {
        $pythonBin = $preferredPython
    } else {
        $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
        if ($pythonCmd) {
            $pythonBin = $pythonCmd.Source
        }
    }
}
if (-not $pythonBin) {
    throw "未找到可用 Python 运行时。请设置 LIGHT_MAQA_PYTHON，或安装 Python 3.11+。"
}
& $pythonBin -m uvicorn api.main:app --host 127.0.0.1 --port $Port
