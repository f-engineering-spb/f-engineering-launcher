param(
  [Parameter(Mandatory = $true)][string]$InputPath,
  [Parameter(Mandatory = $true)][string]$OutputPath
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

if (-not (Test-Path -LiteralPath $InputPath -PathType Leaf)) {
  throw "DWG file was not found: $InputPath"
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutputPath) | Out-Null
Remove-Item -LiteralPath $OutputPath -Force -ErrorAction SilentlyContinue

# Dormant fallback: executed only if render_dwg_smart.ps1 is missing
# (see server.py script_to_run selection). Same production contract as the
# primary paths: Layout1 / Current Layout via native AutoCAD -EXPORT PDF.
# No legacy plotting API, no manual page-setup overrides.
. (Join-Path $PSScriptRoot 'Invoke-NativeDwgPdfExport.ps1')

$app = $null
$document = $null
try {
  $workDir = Join-Path ([System.IO.Path]::GetTempPath()) ("FEng_dwg_modelspace_" + [System.Guid]::NewGuid().ToString("N").Substring(0, 10))
  New-Item -ItemType Directory -Force -Path $workDir | Out-Null
  try {
    $nativePdf = Join-Path $workDir "page_0001.pdf"
    $exportResult = Invoke-NativeDwgPdfExport -InputPath $InputPath -OutputPdf $nativePdf `
      -WorkDir $workDir -TimeoutSec 540 -LayoutName 'Layout1'
    Copy-Item -LiteralPath ([string]$exportResult.pdfPath) -Destination $OutputPath -Force
  } finally {
    Remove-Item -LiteralPath $workDir -Recurse -Force -ErrorAction SilentlyContinue
  }
  if (-not (Test-Path -LiteralPath $OutputPath) -or (Get-Item -LiteralPath $OutputPath).Length -le 1024) {
    throw "NATIVE_EXPORT_BLOCKED: model-space fallback produced no PDF."
  }
} finally {
  if ($document) { try { $document.Close($false) } catch {} }
  if ($app) { try { $app.Quit() } catch {} }
}
