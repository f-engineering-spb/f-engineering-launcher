$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $repoRoot "app\backend\server.py"
$port = 8780

if (-not (Test-Path -LiteralPath $backend)) {
  Write-Host "Backend is not implemented yet: $backend"
  exit 1
}

python $backend --port $port
