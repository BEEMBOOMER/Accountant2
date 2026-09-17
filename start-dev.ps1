$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectRoot

if (-not (Test-Path -LiteralPath ".\.venv\Scripts\python.exe")) {
    throw "Dependencies are not installed. Run .\setup.ps1 first."
}

$backend = Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList @("-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--reload", "--host", "127.0.0.1", "--port", "8000") -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru

try {
    Set-Location -LiteralPath ".\frontend"
    & npm.cmd run dev
}
finally {
    if (-not $backend.HasExited) {
        Stop-Process -Id $backend.Id
    }
}
