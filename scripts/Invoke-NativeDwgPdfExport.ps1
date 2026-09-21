# Invoke-NativeDwgPdfExport.ps1 - shared native AutoCAD PDF export helper.
# ASCII-only file: no cyrillic, no unicode dashes, no BOM.
#
# Mechanism (proven by probe): AutoCAD Core Console (accoreconsole.exe) runs a
# generated script:
#   (LISP layout check -> LAYOUTCHECK:FOUND/MISSING in console output)
#   CTAB Layout1  -> activate the required paper layout
#   _.-EXPORT _PDF _C _N "<absolute output path>"  -> native Current-Layout export
#   _QUIT _N  (the DWG is never saved)
# Prompt sequence verified on AutoCAD 2024:
#   format [Dwf/dwfX/Pdf] -> _PDF
#   plot area [Current sheet/All sheets] -> _C
#   detailed configuration [Yes/No] -> _N
#   file name -> absolute path
#
# Production rule: LAYOUT_NAME=Layout1, EXPORT_SCOPE=Current Layout.
# No All Layouts, no Model extents, no manual page-setup overrides.
# This file uses NO COM, opens NO full AutoCAD session, sends NO commands
# to any live session. One accoreconsole process per call, killed on timeout.
# Throws on any failure (NATIVE_EXPORT_BLOCKED: <reason>). No fallback.
#
# Usage (dot-source, then call):
#   . (Join-Path $PSScriptRoot 'Invoke-NativeDwgPdfExport.ps1')
#   $r = Invoke-NativeDwgPdfExport -InputPath $dwg -OutputPdf $pdf -WorkDir $tempDir
#   $r = Invoke-NativeDwgPdfExport -InputPath $dwg -OutputPdf $pdf -WorkDir $tempDir -TimeoutSec 540 -LayoutName 'Layout1' -Trace { param($n) Write-Trace $n }

$script:NativeExportAccorePath = ""

function Find-NativeAccoreConsole {
  if ($script:NativeExportAccorePath -and (Test-Path -LiteralPath $script:NativeExportAccorePath -PathType Leaf)) {
    return $script:NativeExportAccorePath
  }
  $candidates = @(
    (Join-Path $env:ProgramFiles 'Autodesk\AutoCAD 2024\accoreconsole.exe')
  )
  try {
    $x86 = [System.Environment]::GetEnvironmentVariable('ProgramFiles(x86)')
    if ($x86) { $candidates += (Join-Path $x86 'Autodesk\AutoCAD 2024\accoreconsole.exe') }
  } catch {}
  foreach ($c in $candidates) {
    if ($c -and (Test-Path -LiteralPath $c -PathType Leaf)) {
      $script:NativeExportAccorePath = $c
      return $c
    }
  }
  throw 'NATIVE_EXPORT_BLOCKED: accoreconsole.exe not found, native export host unavailable.'
}

function Read-NativeConsoleLog([string]$path) {
  try { return Get-Content -LiteralPath $path -Encoding UTF8 -Raw -ErrorAction Stop } catch {}
  try { return Get-Content -LiteralPath $path -Encoding Unicode -Raw -ErrorAction Stop } catch {}
  return ""
}

function Invoke-NativeDwgPdfExport {
  param(
    [Parameter(Mandatory = $true)][string]$InputPath,
    [Parameter(Mandatory = $true)][string]$OutputPdf,
    [Parameter(Mandatory = $true)][string]$WorkDir,
    [int]$TimeoutSec = 540,
    [string]$LayoutName = 'Layout1',
    [scriptblock]$Trace = $null
  )
  $markSw = [System.Diagnostics.Stopwatch]::StartNew()
  $markPid = [System.Diagnostics.Process]::GetCurrentProcess().Id
  $traceFn = { param([string]$n) if ($Trace) { try { & $Trace $n } catch {} } }
  $mark = { param([string]$n) & $traceFn (("MARK {0} pid={1} in='{2}' out='{3}' elapsed_ms={4}" -f $n, $markPid, $InputPath, $OutputPdf, [int]$markSw.ElapsedMilliseconds)) }
  if (-not (Test-Path -LiteralPath $InputPath -PathType Leaf)) {
    throw "DWG file not found: $InputPath"
  }
  if ([string]::IsNullOrWhiteSpace($OutputPdf)) { throw 'NATIVE_EXPORT_BLOCKED: empty output path.' }
  try { New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null } catch {}
  try { Remove-Item -LiteralPath $OutputPdf -Force -ErrorAction SilentlyContinue } catch {}

  & $traceFn 'LAYOUT_SELECT'
  $accore = Find-NativeAccoreConsole
  $scrFile = Join-Path $WorkDir 'native_export.scr'
  $consoleLog = Join-Path $WorkDir 'native_export.log'
  $scriptLines = @(
    ('(princ (strcat "LAYOUTCHECK:" (if (tblsearch "LAYOUT" "{0}") "FOUND" "MISSING")))' -f $LayoutName),
    'CTAB',
    $LayoutName,
    '_.-EXPORT',
    '_PDF',
    '_C',
    '_N',
    ('"{0}"' -f $OutputPdf),
    '_QUIT',
    '_N'
  )
  [System.IO.File]::WriteAllLines($scrFile, $scriptLines, [System.Text.UTF8Encoding]::new($false))

  & $traceFn 'NATIVE_EXPORT_BEGIN'
  $sw = [System.Diagnostics.Stopwatch]::StartNew()
  $runStart = Get-Date
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $accore
  $psi.Arguments = ('/i "{0}" /s "{1}"' -f $InputPath, $scrFile)
  $psi.UseShellExecute = $false
  $psi.CreateNoWindow = $true
  $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $proc = [System.Diagnostics.Process]::Start($psi)
  & $mark 'ACCORECONSOLE_START'
  & $mark ('ACCORECONSOLE_PROCESS_READY conpid={0}' -f $proc.Id)
  & $mark 'PDF_EXPORT_COMMAND_START'
  try {
    $outTask = $proc.StandardOutput.ReadToEndAsync()
    $errTask = $proc.StandardError.ReadToEndAsync()
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    $timedOut = $false
    $firstSeenLogged = $false
    while (-not $proc.WaitForExit(500)) {
      if (-not $firstSeenLogged -and (Test-Path -LiteralPath $OutputPdf)) {
        try {
          if ((Get-Item -LiteralPath $OutputPdf).Length -gt 0) {
            $firstSeenLogged = $true
            & $mark 'PDF_FILE_FIRST_SEEN'
          }
        } catch {}
      }
      if ((Get-Date) -ge $deadline) { $timedOut = $true; break }
    }
    if ($timedOut) {
      try { $proc.Kill() } catch {}
      throw ('NATIVE_EXPORT_BLOCKED: accoreconsole timeout after {0}s.' -f $TimeoutSec)
    }
    try { ($outTask.Result + "`n" + $errTask.Result) | Out-File -LiteralPath $consoleLog -Encoding utf8 -Force } catch {}
  } finally {
    try {
      if (-not $proc.HasExited) { $proc.Kill() }
    } catch {}
    try { $proc.Dispose() } catch {}
  }
  try { [string]$proc.ExitCode | Out-File -LiteralPath (Join-Path $WorkDir "native_export.rc") -Encoding ascii -Force } catch {}
  & $traceFn 'NATIVE_EXPORT_END'

  $logText = Read-NativeConsoleLog $consoleLog
  if ($logText -match 'LAYOUTCHECK:MISSING') {
    try { Remove-Item -LiteralPath $OutputPdf -Force -ErrorAction SilentlyContinue } catch {}
    throw ('NATIVE_EXPORT_BLOCKED: layout {0} not present, wrong-layout export discarded.' -f $LayoutName)
  }

  & $traceFn 'PDF_WAIT'
  if (-not (Test-Path -LiteralPath $OutputPdf)) {
    throw 'NATIVE_EXPORT_BLOCKED: native export finished but PDF was not created.'
  }
  $info = Get-Item -LiteralPath $OutputPdf
  if ($info.Length -le 1024) { throw 'NATIVE_EXPORT_BLOCKED: native PDF too small, export failed.' }
  if ($info.LastWriteTime -lt $runStart.AddSeconds(-5)) {
    throw 'NATIVE_EXPORT_BLOCKED: native PDF timestamp predates this run (stale file).'
  }
  try {
    $fs = [System.IO.File]::OpenRead($OutputPdf)
    $sig = New-Object byte[] 5
    [void]$fs.Read($sig, 0, 5)
    $fs.Close()
    if ([System.Text.Encoding]::ASCII.GetString($sig) -ne '%PDF-') {
      throw 'NATIVE_EXPORT_BLOCKED: output has no %PDF- signature.'
    }
  } catch {
    if ($_.Exception.Message -like 'NATIVE_EXPORT_BLOCKED*') { throw }
    throw ('NATIVE_EXPORT_BLOCKED: cannot read output PDF: {0}' -f $_.Exception.Message)
  }
  & $mark 'PDF_VALIDATED'
  return [ordered]@{
    ok        = $true
    pdfPath   = $OutputPdf
    exportMs  = [int]$sw.ElapsedMilliseconds
    pageCount = 1
    layout    = $LayoutName
    progId    = 'AutoCAD Core Console 2024 (native -EXPORT)'
  }
}
