$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectRoot

if (-not (Test-Path -LiteralPath ".\.venv\Scripts\python.exe")) {
    throw "Dependencies are not installed. Run .\setup.ps1 first."
}

if (-not (Test-Path -LiteralPath ".\frontend\dist\index.html")) {
    throw "The frontend has not been built. Run .\setup.ps1 first."
}

& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000

