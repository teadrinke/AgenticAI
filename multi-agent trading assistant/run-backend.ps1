$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $Root "backend"
$Python = Join-Path $BackendDir ".venv\Scripts\python.exe"

Set-Location -LiteralPath $BackendDir
& $Python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
