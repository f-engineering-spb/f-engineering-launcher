param(
  [Parameter(Mandatory = $true)][string]$DwgPath,
  [Parameter(Mandatory = $true)][string]$OutputJson
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutputJson) | Out-Null

$app = $null
$document = $null
try {
  $app = New-Object -ComObject "ZWCAD.Application.2025"
  $app.Visible = $false
  $document = $app.Documents.Open($DwgPath, $true)
  $rows = @()
  $index = 0
  foreach ($entity in $document.ModelSpace) {
    $minPoint = $null
    $maxPoint = $null
    try {
      $entity.GetBoundingBox([ref]$minPoint, [ref]$maxPoint)
      $rows += [pscustomobject]@{
        index = $index
        type = [string]$entity.ObjectName
        minX = [double]$minPoint[0]
        minY = [double]$minPoint[1]
        maxX = [double]$maxPoint[0]
        maxY = [double]$maxPoint[1]
        width = [double]$maxPoint[0] - [double]$minPoint[0]
        height = [double]$maxPoint[1] - [double]$minPoint[1]
      }
    } catch {
      # Proxy and unsupported entities cannot contribute bounds.  They are
      # retained by ZWCAD at render time, but excluded from this diagnostics.
    }
    $index++
  }
  [pscustomobject]@{
    source = $DwgPath
    entityCount = $index
    boundedEntityCount = $rows.Count
    entities = $rows
  } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $OutputJson -Encoding utf8
} finally {
  if ($document) { $document.Close($false) }
  if ($app) { $app.Quit() }
}
