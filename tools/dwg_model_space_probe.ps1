param(
  [Parameter(Mandatory = $true)][string]$DwgPath,
  [Parameter(Mandatory = $true)][string]$OutputPdf,
  [Parameter(Mandatory = $true)][string]$LogPath
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

function Write-ProbeLog([string]$Message) {
  $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  "$stamp  $Message" | Add-Content -LiteralPath $LogPath -Encoding utf8
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutputPdf) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $LogPath) | Out-Null
Remove-Item -LiteralPath $OutputPdf -Force -ErrorAction SilentlyContinue
Set-Content -LiteralPath $LogPath -Value "" -Encoding utf8

$app = $null
$document = $null
try {
  Write-ProbeLog "Starting ZWCAD 2025 COM automation."
  $app = New-Object -ComObject "ZWCAD.Application.2025"
  $app.Visible = $false
  Write-ProbeLog "Opening source DWG read-only: $DwgPath"
  $document = $app.Documents.Open($DwgPath, $true)
  $document.SetVariable("BACKGROUNDPLOT", 0)

  # ModelSpace.Layout makes the preview independent of the tab that happened
  # to be active when the DWG was last saved.  The source DWG stays read-only.
  $layout = $document.ModelSpace.Layout
  $layout.ConfigName = "ZWCAD PDF(High Quality Print).pc5"
  $layout.RefreshPlotDeviceInfo()
  $a0Media = @($layout.GetCanonicalMediaNames() | Where-Object { $_ -match "A0" } | Select-Object -First 1)
  if ($a0Media.Count -ne 1) {
    throw "The configured ZWCAD PDF device did not expose an A0 paper size."
  }
  $layout.CanonicalMediaName = $a0Media[0]
  $layout.PlotType = 1 # acExtents
  $layout.CenterPlot = $true
  $layout.UseStandardScale = $true
  $layout.StandardScale = 0 # acScaleToFit
  # Preview rule: Model Space is printed on A0 without lineweights, so thin
  # drawing geometry does not turn into visually heavy bars in the PDF.
  $layout.PlotWithLineweights = $false
  $layout.PlotWithPlotStyles = $true
  Write-ProbeLog "Plotting Model Space: A0, extents, scale-to-fit, lineweights off: $OutputPdf"
  $success = $document.Plot.PlotToFile($OutputPdf)
  Write-ProbeLog "PlotToFile result: $success"
  if (-not (Test-Path -LiteralPath $OutputPdf)) {
    throw "ZWCAD returned without creating the expected PDF."
  }
  Write-ProbeLog "PDF created: $((Get-Item -LiteralPath $OutputPdf).Length) bytes"
}
catch {
  Write-ProbeLog "ERROR: $($_.Exception.Message)"
  exit 1
}
finally {
  if ($document) { $document.Close($false) }
  if ($app) { $app.Quit() }
}
