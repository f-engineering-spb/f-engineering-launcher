$ErrorActionPreference = "Stop"

# Единая точка запуска: запускает лаунчер как оконное приложение Windows (без консоли)
$appLauncher = Join-Path $PSScriptRoot "start_app.ps1"
& $appLauncher @args

