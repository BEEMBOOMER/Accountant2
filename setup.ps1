$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectRoot

if (-not (Test-Path -LiteralPath ".venv")) {
    python -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r ".\backend\requirements.txt"

Push-Location ".\frontend"
try {
    & npm.cmd ci
    & npm.cmd run build
}
finally {
    Pop-Location
}

Write-Host "Setup complete. Run .\start.ps1 to open the dashboard at http://127.0.0.1:8000"
