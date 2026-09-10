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

$app = $null
$document = $null
try {
  # Open read-only.  The original DWG and its source directory are never a
  # write target for the preview pipeline.
  $comProgIds = @(
    "AutoCAD.Application.24",
    "AutoCAD.Application",
    "ZWCAD.Application.2025",
    "ZWCAD.Application"
  )
  $app = $null
  foreach ($progId in $comProgIds) {
    try {
      $app = New-Object -ComObject $progId -ErrorAction Stop
      if ($app) { break }
    } catch {}
  }
  if (-not $app) {
    throw "CAD COM error: neither AutoCAD nor ZWCAD could be initialized."
  }
  $app.Visible = $false
  $document = $app.Documents.Open($InputPath, $true)
  $document.SetVariable("BACKGROUNDPLOT", 0)

  # Model Space overview: full A0 page, extents, scale-to-fit and no plotted
  # lineweights.  It is a fast visual map, not a replacement for CAD layouts.
  $layout = $document.ModelSpace.Layout
  $devices = @($layout.GetPlotDeviceNames())
  $preferredDevices = @(
    "DWG To PDF.pc3",
    "AutoCAD PDF (General Documentation).pc3",
    "AutoCAD PDF (High Quality Print).pc3",
    "ZWCAD PDF(High Quality Print).pc5",
    "DWG to PDF.pc5",
    "Microsoft Print to PDF"
  )
  foreach ($dev in $preferredDevices) {
    if ($devices -contains $dev) {
      $layout.ConfigName = $dev
      $layout.RefreshPlotDeviceInfo()
      break
    }
  }
  $layout.RefreshPlotDeviceInfo()
  $a0Media = @($layout.GetCanonicalMediaNames() | Where-Object { $_ -match "A0" } | Select-Object -First 1)
  if ($a0Media.Count -ne 1) {
    throw "CAD PDF-плоттер не предоставил формат A0."
  }
  $layout.CanonicalMediaName = $a0Media[0]
  $layout.PlotType = 1 # acExtents
  $layout.CenterPlot = $true
  $layout.UseStandardScale = $true
  $layout.StandardScale = 0 # acScaleToFit
  $layout.PlotWithLineweights = $false
  $layout.PlotWithPlotStyles = $true

  if (-not $document.Plot.PlotToFile($OutputPath)) {
    throw "CAD-система не подтвердила создание PDF для пространства модели."
  }
  if (-not (Test-Path -LiteralPath $OutputPath) -or (Get-Item -LiteralPath $OutputPath).Length -le 1024) {
    throw "CAD-система не создала PDF-файл превью."
  }
} finally {
  if ($document) { $document.Close($false) }
  if ($app) { $app.Quit() }
}
