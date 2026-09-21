param(
  [Parameter(Mandatory = $true)][string]$InputPath,
  [Parameter(Mandatory = $false)][string]$OutputPath = "",
  [Parameter(Mandatory = $false)][string]$FallbackCachePath = "",
  [Parameter(Mandatory = $false)][string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

# TRACE-ONLY: monotonic timestamps, no logic changes.
$script:traceT0 = [System.Diagnostics.Stopwatch]::StartNew()
$script:startTime = (Get-Date).ToString("o")
$script:tracePid = [System.Diagnostics.Process]::GetCurrentProcess().Id
$script:traceLayout = ""
function Write-Trace([string]$name) {
    $line = ("T {0} stage={1} elapsed_ms={2} pid={3} dwg='{4}' layout='{5}' output='{6}'" -f (Get-Date -Format o), $name, [int]$script:traceT0.ElapsedMilliseconds, $script:tracePid, $InputPath, $script:traceLayout, $OutputPath)
    [Console]::Error.WriteLine($line)
}
Write-Trace "T_START"

# P0: при любой ошибке пишем диагноз и сохраняем temp-каталог для разбора.
# Удаление temp — только при успехе (см. finally в конце файла).
$script:renderStage = "init"
$script:keepTempDir = $false
trap {
  $script:keepTempDir = $true
  $errMsg = ""
  try { $errMsg = [string]$_.Exception.Message } catch {}
  $endTime = Get-Date
  try {
    $diag = [ordered]@{
      ok = $false
      stage = [string]$script:renderStage
      error = $errMsg
      time = $endTime.ToString("o")
      dwg_path = [string]$InputPath
      output_pdf_path = [string]$OutputPath
      start_time = [string]$script:startTime
      end_time = $endTime.ToString("o")
      elapsed_ms = [int]$script:traceT0.ElapsedMilliseconds
      stage_last_reached = [string]$script:renderStage
      layout_current = [string]$script:traceLayout
      layout_target = "Layout1"
      layouts_total = 1
    }
    $pdfExists = $false
    $pdfSize = 0
    $pdfHeader = ""
    try {
      $pagePdf = Join-Path $tempDir "page_0001.pdf"
      if ($tempDir -and (Test-Path -LiteralPath $pagePdf)) {
        $pdfExists = $true
        $pdfSize = (Get-Item -LiteralPath $pagePdf).Length
        $sigBytes = [System.IO.File]::ReadAllBytes($pagePdf)[0..4]
        $pdfHeader = [System.Text.Encoding]::ASCII.GetString($sigBytes)
      }
    } catch {}
    $consoleRc = $null
    try {
      $rcPath = Join-Path $tempDir "native_export.rc"
      if ($tempDir -and (Test-Path -LiteralPath $rcPath)) {
        $consoleRc = [int](Get-Content -LiteralPath $rcPath -Raw -ErrorAction Stop).Trim()
      }
    } catch {}
    $mergeStarted = ([string]$script:renderStage -in @("merge", "save"))
    $mergeFinished = $false
    try {
      $combinedPdf = Join-Path $tempDir "combined.pdf"
      if ($tempDir -and (Test-Path -LiteralPath $combinedPdf) -and (Get-Item -LiteralPath $combinedPdf).Length -gt 1024) {
        $mergeFinished = $true
      }
    } catch {}
    $diag.process_returncode = $consoleRc
    $diag.temp_dir = [string]$tempDir
    $diag.pdf_exists = [bool]$pdfExists
    $diag.pdf_size = [long]$pdfSize
    $diag.pdf_header = [string]$pdfHeader
    $diag.merge_started = [bool]$mergeStarted
    $diag.merge_finished = [bool]$mergeFinished
    $preserved = ""
    try {
      $repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
      $failRoot = Join-Path $repoRoot "runtime\failed-renders"
      New-Item -ItemType Directory -Force -Path $failRoot | Out-Null
      $stem = [System.IO.Path]::GetFileNameWithoutExtension([string]$InputPath)
      $safe = ($stem -replace "[^A-Za-z0-9_-]", "_")
      if ($safe.Length -gt 40) { $safe = $safe.Substring(0, 40) }
      if ([string]::IsNullOrWhiteSpace($safe)) { $safe = "dwg" }
      $preserved = Join-Path $failRoot ((Get-Date -Format "yyyyMMdd-HHmmss") + "-" + $safe)
      if ($tempDir -and (Test-Path -LiteralPath $tempDir)) {
        Copy-Item -LiteralPath $tempDir -Destination $preserved -Recurse -Force -ErrorAction Stop
      }
    } catch { $preserved = "" }
    $diag.preserved_dir = [string]$preserved
    $ej = ($diag | ConvertTo-Json -Compress)
    try {
      if ($tempDir -and (Test-Path -LiteralPath $tempDir)) {
        $ej | Out-File -LiteralPath (Join-Path $tempDir "error.json") -Encoding utf8 -Force
      }
    } catch {}
    try {
      if ($preserved -and (Test-Path -LiteralPath $preserved)) {
        $ej | Out-File -LiteralPath (Join-Path $preserved "error.json") -Encoding utf8 -Force
      }
    } catch {}
  } catch {}
  exit 1
}

if (-not (Test-Path -LiteralPath $InputPath -PathType Leaf)) {
  throw "DWG-файл не найден: $InputPath"
}

# Целевой путь по умолчанию: та же папка, то же имя, расширение .pdf
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
  $OutputPath = [System.IO.Path]::ChangeExtension($InputPath, ".pdf")
}

$outputDir = Split-Path -Parent $OutputPath
if (-not [string]::IsNullOrWhiteSpace($outputDir) -and -not (Test-Path -LiteralPath $outputDir)) {
  try {
    New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
  } catch {}
}

# Thin oneshot fallback: no CAD session, no COM, the document is never opened
# here. One native export via the shared helper (identical to daemon path).
$sessionGuid = [System.Guid]::NewGuid().ToString("N").Substring(0, 10)
$tempDir = Join-Path ([System.IO.Path]::GetTempPath()) "FEng_dwg_render_$sessionGuid"
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null
# P0: owner record for backend diagnostics and targeted cleanup (no CAD here).
try {
  @{ acadPid = 0; startedAt = (Get-Date).ToString("o"); inputPath = [string]$InputPath } | ConvertTo-Json -Compress | Out-File -LiteralPath (Join-Path $tempDir "owner.json") -Encoding utf8 -Force
} catch {}

try {
  $script:renderStage = "native-export"

  # Native export: single paper layout (Layout1, Current Layout) via AutoCAD
  # Core Console _.-EXPORT _PDF. No legacy plotting API, no manual page-setup overrides.
  . (Join-Path $PSScriptRoot 'Invoke-NativeDwgPdfExport.ps1')
  $script:renderStage = "native-export"
  $script:traceLayout = "Layout1"
  Write-Trace "T_LAYOUT_SELECTED"
  $nativePdf = Join-Path $tempDir "page_0001.pdf"
  $exportResult = Invoke-NativeDwgPdfExport -InputPath $InputPath -OutputPdf $nativePdf `
    -WorkDir $tempDir -TimeoutSec 540 -LayoutName 'Layout1' `
    -Trace { param($n) Write-Trace $n }
  $pagePdfPaths = [System.Collections.Generic.List[string]]::new()
  $pagePdfPaths.Add([string]$exportResult.pdfPath)

  if ($pagePdfPaths.Count -eq 0) {
    throw "NATIVE_EXPORT_BLOCKED: native export produced no PDF page."
  }

  # Native export yields exactly one page (Layout1, Current Layout): direct copy.
  $script:renderStage = "merge"
  $tempCombinedPdf = Join-Path $tempDir "combined.pdf"
  Copy-Item -LiteralPath $pagePdfPaths[0] -Destination $tempCombinedPdf -Force
  if (-not (Test-Path -LiteralPath $tempCombinedPdf)) {
    throw "NATIVE_EXPORT_BLOCKED: combined PDF missing after native export."
  }

  # Сохранение в целевую папку рядом с DWG или резервный кэш
  $script:renderStage = "save"
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

  try {
    $outExists = Test-Path -LiteralPath $finalDestination
    $outSize = 0
    $outSig = ""
    if ($outExists) {
      $outSize = (Get-Item -LiteralPath $finalDestination).Length
      $sigBytes = [System.IO.File]::ReadAllBytes($finalDestination)[0..4]
      $outSig = ($sigBytes | ForEach-Object { $_.ToString("X2") }) -join " "
    }
    [Console]::Error.WriteLine(("OUTPUT exists={0} size={1} sig={2} path='{3}'" -f $outExists, $outSize, $outSig, $finalDestination))
  } catch {}
  $result = @{
    ok = $true
    finalPath = $finalDestination
    isLocalFolder = ($finalDestination -eq $OutputPath)
    pageCount = $pagePdfPaths.Count
    progId = [string]$exportResult.progId
  }
  Write-Trace "T_END"
  Write-Output ($result | ConvertTo-Json -Compress)
} finally {
  Write-Trace "T_CLEANUP_BEGIN"
  # No CAD session exists in this path: nothing to close or quit.
  [System.GC]::Collect()
  [System.GC]::WaitForPendingFinalizers()

  # P0: при ошибке temp оставляем вместе с error.json для разбора.
  if ((Test-Path -LiteralPath $tempDir) -and -not $script:keepTempDir) {
    Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue
  }
  Write-Trace "T_CLEANUP_END"
}
