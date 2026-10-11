# Run the Waypoint API and UI on http://127.0.0.1:8000 (same as `make serve`, without --reload).
# Loopback only: asker_id is client-supplied and not authenticated (demo only).
# Usage from the repo root:  powershell -ExecutionPolicy Bypass -File scripts\serve.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "No virtualenv at $python. Create it first: py -3.14 -m venv .venv; .venv\Scripts\python.exe -m pip install -e .[dev]"
}
Set-Location $root
& $python -m uvicorn waypoint.api.app:app --host 127.0.0.1 --port 8000
exit $LASTEXITCODE
