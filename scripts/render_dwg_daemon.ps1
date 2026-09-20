param(
  [Parameter(Mandatory = $true)][string]$JobDir,
  [Parameter(Mandatory = $false)][string]$ReadyFile = "",
  [Parameter(Mandatory = $false)][string]$LogFile = "",
  [Parameter(Mandatory = $false)][int]$IdleMinutes = 15
)

# Долгоживущий диспетчер DWG->PDF: CAD-сессий нет, DWG не открывается.
# Каждый job выполняет один accoreconsole.exe (native _.-EXPORT _PDF)
# через общий хелпер Invoke-NativeDwgPdfExport.ps1. Задания идут очередью.
#
# Протокол (файлы в $JobDir, имена-гуиды от сервера):
#   <id>.job.json  -> { inputPath, outputPath, fallbackCachePath, pythonExe }
#   <id>.done.json -> { ok: true, result: {...} } | { ok: false, error: "..." }
#   daemon.fatal   -> { error } если native-хост недоступен (сервер увидит и откатится).
# Без заданий дольше IdleMinutes демон выходит сам (сервер поднимет заново).

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

if (-not (Test-Path -LiteralPath $JobDir -PathType Container)) {
  New-Item -ItemType Directory -Force -Path $JobDir | Out-Null
}

function Write-DaemonLog([string]$message) {
  if ([string]::IsNullOrWhiteSpace($LogFile)) { return }
  try {
    $line = "{0:yyyy-MM-dd HH:mm:ss} [dwg-daemon] {1}" -f (Get-Date), $message
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8 -ErrorAction SilentlyContinue
  } catch {}
}

# NOTE: no COM, no message filter, no CAD session in dispatcher mode.

# --- Тело конвертации: один native export через общий хелпер. ---
# --- CAD-сессий нет: диспетчер только ведёт job/state/done протокол. ---
function Convert-DwgJob($job, [string]$jobId = "") {
  $InputPath = [string]$job.inputPath
  $OutputPath = [string]$job.outputPath
  $FallbackCachePath = [string]$job.fallbackCachePath
  $PythonExe = [string]$job.pythonExe

  if (-not (Test-Path -LiteralPath $InputPath -PathType Leaf)) {
    throw "DWG-файл не найден: $InputPath"
  }
  if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = [System.IO.Path]::ChangeExtension($InputPath, ".pdf")
  }
  $outputDir = Split-Path -Parent $OutputPath
  if (-not [string]::IsNullOrWhiteSpace($outputDir) -and -not (Test-Path -LiteralPath $outputDir)) {
    try {
      New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
    } catch {}
  }

  $document = $null
  $sessionGuid = [System.Guid]::NewGuid().ToString("N").Substring(0, 10)
  $tempDir = Join-Path ([System.IO.Path]::GetTempPath()) "FEng_dwg_render_$sessionGuid"
  New-Item -ItemType Directory -Force -Path $tempDir | Out-Null

  $stateFile = ""
  if (-not [string]::IsNullOrWhiteSpace($jobId) -and [string]::IsNullOrWhiteSpace($JobDir) -eq $false) {
    $stateFile = Join-Path $JobDir ($jobId + ".state.json")
  }
  $stateObj = [ordered]@{
    jobId = $jobId
    dwgPath = $InputPath
    pid = $PID
    documentOpened = $false
    startedAt = (Get-Date).ToString("o")
    status = "running"
    totalLayouts = 0
    completedLayouts = 0
  }
  $writeState = {
    if ($stateFile) {
      try { $stateObj | ConvertTo-Json -Compress | Out-File -LiteralPath $stateFile -Encoding utf8 -Force } catch {}
    }
  }
  & $writeState

  # Native export: single paper layout (Layout1, Current Layout) via AutoCAD
  # Core Console _.-EXPORT _PDF. Dispatcher opens no DWG and starts no CAD.
  . (Join-Path $PSScriptRoot 'Invoke-NativeDwgPdfExport.ps1')
  $nativePdf = Join-Path $tempDir "page_0001.pdf"
  try {
    $exportResult = Invoke-NativeDwgPdfExport -InputPath $InputPath -OutputPdf $nativePdf `
      -WorkDir $tempDir -TimeoutSec 540 -LayoutName 'Layout1' `
      -Trace { param($n) Write-DaemonLog ("native {0}" -f $n) }
    $stateObj.documentOpened = $true
    $stateObj.totalLayouts = 1
    $stateObj.completedLayouts = 1
    & $writeState
    $pagePdfPaths = [System.Collections.Generic.List[string]]::new()
    $pagePdfPaths.Add([string]$exportResult.pdfPath)

    if ($pagePdfPaths.Count -eq 0) {
      throw 'NATIVE_EXPORT_BLOCKED: native export produced no PDF page.'
    }

    # Native export yields exactly one page (Layout1, Current Layout): direct copy.
    $tempCombinedPdf = Join-Path $tempDir "combined.pdf"
    Copy-Item -LiteralPath $pagePdfPaths[0] -Destination $tempCombinedPdf -Force
    if (-not (Test-Path -LiteralPath $tempCombinedPdf)) {
      throw 'NATIVE_EXPORT_BLOCKED: combined PDF missing after native export.'
    }

    $finalDestination = $OutputPath
    $writeSuccess = $false
    try {
      Copy-Item -LiteralPath $tempCombinedPdf -Destination $OutputPath -Force -ErrorAction Stop
      $writeSuccess = $true
    } catch {
      if (-not [string]::IsNullOrWhiteSpace($FallbackCachePath)) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $FallbackCachePath) | Out-Null
        Copy-Item -LiteralPath $tempCombinedPdf -Destination $FallbackCachePath -Force
        $finalDestination = $FallbackCachePath
        $writeSuccess = $true
      } else {
        throw "Не удалось сохранить PDF в целевую папку '$OutputPath': $_"
      }
    }

    $stateObj.status = "done"
    $stateObj.completedLayouts = [int]$pagePdfPaths.Count
    & $writeState

    return @{
      ok = $true
      finalPath = $finalDestination
      isLocalFolder = ($finalDestination -eq $OutputPath)
      pageCount = $pagePdfPaths.Count
      progId = [string]$exportResult.progId
    }
  } finally {
    if ($stateFile -and (Test-Path -LiteralPath $stateFile)) {
      try { Remove-Item -LiteralPath $stateFile -Force -ErrorAction SilentlyContinue } catch {}
    }
    # Сессию НЕ гасим (переиспользуем), документ закрываем, мусор чистим.
    if ($document) {
      try { $document.Close($false) } catch {}
    }
    [System.GC]::Collect()
    [System.GC]::WaitForPendingFinalizers()
    if (Test-Path -LiteralPath $tempDir) {
      Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
  }
}

# --- Старт: CAD не поднимаем, проверяем только native-хост. ---

# P0: идентификатор этого демона-диспетчера.
$script:daemonGuid = [System.Guid]::NewGuid().ToString("N")
. (Join-Path $PSScriptRoot 'Invoke-NativeDwgPdfExport.ps1')
try {
  $null = Find-NativeAccoreConsole
} catch {
  $fatal = @{ error = [string]$_.Exception.Message }
  try {
    $fatal | ConvertTo-Json -Compress | Out-File -LiteralPath (Join-Path $JobDir "daemon.fatal") -Encoding utf8 -Force
  } catch {}
  Write-DaemonLog ("FATAL: " + [string]$_.Exception.Message)
  exit 1
}

$ready = @{
  pid = $PID
  acadPid = 0
  progId = 'AutoCAD Core Console 2024 (native -EXPORT)'
  startedAt = (Get-Date).ToString("o")
  jobDir = [string]$JobDir
  daemonGuid = [string]$script:daemonGuid
}
try {
  if ($ReadyFile) {
    $ready | ConvertTo-Json -Compress | Out-File -LiteralPath $ReadyFile -Encoding utf8 -Force
  }
} catch {}
Write-DaemonLog "ready dispatcher (no CAD session)"

# --- Главный цикл ---
$idleSeconds = 0
$idleLimit = [Math]::Max(60, $IdleMinutes * 60)
try {
  while ($true) {
    $jobFile = Get-ChildItem -LiteralPath $JobDir -Filter "*.job.json" -File -ErrorAction SilentlyContinue |
      Sort-Object CreationTime |
      Select-Object -First 1
    if (-not $jobFile) {
      Start-Sleep -Seconds 1
      $idleSeconds += 1
      if ($idleSeconds -ge $idleLimit) {
        Write-DaemonLog "idle timeout, exiting"
        break
      }
      continue
    }
    $idleSeconds = 0
    $jobStartTime = Get-Date
    $jobId = [System.IO.Path]::GetFileNameWithoutExtension([System.IO.Path]::GetFileNameWithoutExtension($jobFile.Name))
    $doneFile = Join-Path $JobDir ($jobId + ".done.json")
    try {
      $job = Get-Content -LiteralPath $jobFile.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
      $result = Convert-DwgJob $job $jobId
      @{ ok = $true; result = $result } | ConvertTo-Json -Compress -Depth 6 |
        Out-File -LiteralPath $doneFile -Encoding utf8 -Force
      Write-DaemonLog ("job {0} ok pages={1}" -f $jobId, $result.pageCount)
    } catch {
      $errText = $_.Exception.Message
      if (-not $errText) { $errText = "$_" }
      @{ ok = $false; error = [string]$errText } | ConvertTo-Json -Compress |
        Out-File -LiteralPath $doneFile -Encoding utf8 -Force
      Write-DaemonLog ("job {0} FAIL: {1}" -f $jobId, $errText)
    } finally {
      try { Remove-Item -LiteralPath $jobFile.FullName -Force -ErrorAction SilentlyContinue } catch {}
    }
    Start-Sleep -Seconds 5
  }
} finally {
  [System.GC]::Collect()
  [System.GC]::WaitForPendingFinalizers()
}
Write-DaemonLog "stopped"
