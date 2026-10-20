<#
  Pitch-day launcher for Windows PowerShell 5.1 (ASCII only, no command chaining).
    powershell -ExecutionPolicy Bypass -File .\run_demo.ps1            # fine-tuned 1.5B on this laptop (default)
    powershell -ExecutionPolicy Bypass -File .\run_demo.ps1 -Remote    # Modal 7B first: set FT_REMOTE_URL and FT_REMOTE_KEY in this window first
    powershell -ExecutionPolicy Bypass -File .\run_demo.ps1 -Rules     # fallback: rules engine, same numbers and refusals
    Add -Legacy to any of these to serve the v1 UI at / (the v2 UI build in app\web is committed, so no Node is needed; v1 is always at /legacy).
  Sets the demo settings, checks Ollama and the model, warms it, asks the model-segment questions (tools/preflight.py),
  prints READY / NOT READY, then starts the app on http://127.0.0.1:8000. Keys are never written to this file.
#>
param([switch]$Remote, [switch]$Rules, [switch]$SkipCheck, [switch]$Legacy, [int]$Port = 8000)
$ErrorActionPreference = "Continue"
Set-Location -Path $PSScriptRoot

$env:PYTHONUTF8 = "1"
$env:NP_BRAIN = "finetuned"
$env:FT_MODEL = "gowtham-nimbuspay-agent"
$env:FT_MODE = "hybrid"
$env:FT_KEEP_ALIVE = "24h"
$env:FT_TIMEOUT_S = "8"
$env:FT_ANSWER = "0"
$env:NP_DEMO = "1"
$env:HOST = "127.0.0.1"
$env:PORT = "$Port"
if ($Legacy) {
    $env:NP_UI = "legacy"
    Write-Host "UI: v1 (legacy) at http://127.0.0.1:$Port/" -ForegroundColor Yellow
} else {
    Remove-Item Env:NP_UI -ErrorAction SilentlyContinue
    if (-not (Test-Path (Join-Path $PSScriptRoot "app\web\index.html"))) {
        Write-Host "Note: app\web\index.html is missing, so the v1 UI is served. Rebuild: cd web; npm ci; npm run build" -ForegroundColor Yellow
    }
}

if ($Remote) {
    if (-not $env:FT_REMOTE_URL) {
        Write-Host "NOT READY: -Remote needs FT_REMOTE_URL (and FT_REMOTE_KEY) set in this window first." -ForegroundColor Red
        exit 1
    }
    $env:FT_REMOTE_TIMEOUT_S = "3"
    $env:FT_REMOTE_COOLDOWN_S = "600"
    Write-Host "Remote model on: $($env:FT_REMOTE_URL.Split('/')[2]) (laptop model as fallback)."
} else {
    Remove-Item Env:FT_REMOTE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:FT_REMOTE_KEY -ErrorAction SilentlyContinue
}

if ($Rules) {
    $env:NP_BRAIN = "rules"
    Write-Host "READY: rules engine (fallback mode). Starting the app on http://127.0.0.1:$Port" -ForegroundColor Yellow
    python -m app
    exit $LASTEXITCODE
}

$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama) {
    Write-Host "NOT READY: 'ollama' is not installed or not on PATH. Start Ollama, or use: .\run_demo.ps1 -Rules" -ForegroundColor Red
    exit 1
}
$list = (& ollama list 2>&1 | Out-String)
if ($list -notmatch "gowtham-nimbuspay-agent") {
    Write-Host "NOT READY: Ollama has no 'gowtham-nimbuspay-agent'. Run: ollama create gowtham-nimbuspay-agent -f Modelfile" -ForegroundColor Red
    Write-Host $list
    exit 1
}

if (-not $SkipCheck) {
    python tools/preflight.py
    if ($LASTEXITCODE -ne 0) {
        Write-Host "NOT READY: see the lines above. Fallback: .\run_demo.ps1 -Rules" -ForegroundColor Red
        exit 1
    }
}
Write-Host "Starting the app on http://127.0.0.1:$Port (Ctrl+C to stop). Keep this window open." -ForegroundColor Green
python -m app
