#Requires -Version 5.1
param(
    [Parameter(Mandatory = $true)][string]$Root,
    [Parameter(Mandatory = $true)][string]$BackendRoot,
    [Parameter(Mandatory = $true)][string]$DatabaseUrl,
    [Parameter(Mandatory = $true)][string]$FakeLLM,
    [Parameter(Mandatory = $true)][string]$RefineV2,
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
} else {
    Remove-Item Env:ENABLE_COMPLEX_REFINE_V2 -ErrorAction SilentlyContinue
}

Set-Location $Root
py -3.12 -m uvicorn api.main:app --host 127.0.0.1 --port $Port
