$ErrorActionPreference = "Stop"

# Запуск лаунчера как приложения Windows: без консоли, в отдельном окне.
# Если сервер ещё не запущен — поднимаем его скрыто, открываем окно,
# после закрытия окна останавливаем сервер, который сами запустили.
$port = 8780
$repoRoot = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $repoRoot "app\backend\server.py"
$url = "http://127.0.0.1:$port/"

function Test-PortOpen {
  param([int]$Port)
  try {
    $client = New-Object Net.Sockets.TcpClient
    $iar = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
    $ok = $iar.AsyncWaitHandle.WaitOne(300)
    $client.Close()
    return $ok
  } catch {
    return $false
  }
}

$weStartedServer = $false
$serverProc = $null
if (-not (Test-PortOpen -Port $port)) {
  $pythonw = "C:\Python314\pythonw.exe"
  if (-not (Test-Path -LiteralPath $pythonw)) {
    $pythonw = "C:\Python314\python.exe"
  }
  $serverProc = Start-Process -FilePath $pythonw `
    -ArgumentList "`"$backend`" --port $port" `
    -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru
  $weStartedServer = $true
  $deadline = (Get-Date).AddSeconds(25)
  while ((Get-Date) -lt $deadline) {
    if (Test-PortOpen -Port $port) { break }
    Start-Sleep -Milliseconds 400
    $serverProc.Refresh()
    if ($serverProc.HasExited) { exit 1 }
  }
}

$edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if (-not (Test-Path -LiteralPath $edge)) {
  $edge = "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
}
$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$profile = Join-Path $env:LOCALAPPDATA "FEngineeringLauncher\AppProfile"
New-Item -ItemType Directory -Path $profile -Force | Out-Null

if (Test-Path -LiteralPath $edge) {
  & $edge --app=$url --user-data-dir="$profile" --no-first-run
} elseif (Test-Path -LiteralPath $chrome) {
  & $chrome --app=$url --user-data-dir="$profile" --no-first-run
} else {
  Start-Process $url
}

if ($weStartedServer -and $serverProc) {
  $serverProc.Refresh()
  if (-not $serverProc.HasExited) {
    Stop-Process -InputObject $serverProc -Force
  }
}
