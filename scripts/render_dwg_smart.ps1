param(
  [Parameter(Mandatory = $true)][string]$InputPath,
  [Parameter(Mandatory = $false)][string]$OutputPath = "",
  [Parameter(Mandatory = $false)][string]$FallbackCachePath = "",
  [Parameter(Mandatory = $false)][string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

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

# Подключение к CAD через COM-интерфейс
$comProgIds = @(
  "ZWCAD.Application.2025",
  "ZWCAD.Application",
  "AutoCAD.Application.2025",
  "AutoCAD.Application"
)

$app = $null
$usedProgId = ""
foreach ($progId in $comProgIds) {
  try {
    $app = New-Object -ComObject $progId -ErrorAction Stop
    if ($app) {
      $usedProgId = $progId
      break
    }
  } catch {}
}

if (-not $app) {
  throw "Не удалось подключиться к ZWCAD или AutoCAD через COM (проверены: $($comProgIds -join ', '))."
}

$app.Visible = $false
$document = $null

$sessionGuid = [System.Guid]::NewGuid().ToString("N").Substring(0, 10)
$tempDir = Join-Path ([System.IO.Path]::GetTempPath()) "FEng_dwg_render_$sessionGuid"
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null

try {
  # Открытие в режиме 'только чтение'
  $document = $app.Documents.Open($InputPath, $true)
  $document.SetVariable("BACKGROUNDPLOT", 0)

  # Проверка листов (Layouts)
  $candidateLayouts = @($document.Layouts | Where-Object { -not $_.ModelType } | Sort-Object TabOrder)
  $nonEmptyLayouts = @($candidateLayouts | Where-Object { $_.Block.Count -gt 1 })

  $pagePdfPaths = [System.Collections.Generic.List[string]]::new()

  if ($nonEmptyLayouts.Count -gt 0) {
    # Экспорт листов чертежа
    foreach ($layout in $nonEmptyLayouts) {
      $document.ActiveLayout = $layout
      $layout.RefreshPlotDeviceInfo()

      # Выбор виртуального PDF-плоттера
      $devices = @($layout.GetPlotDeviceNames())
      $preferredDevices = @(
        "ZWCAD PDF(High Quality Print).pc5",
        "DWG to PDF.pc5",
        "DWG To PDF.pc3",
        "ZWCAD PDF(General Documentation).pc5",
        "Microsoft Print to PDF"
      )
      foreach ($dev in $preferredDevices) {
        if ($devices -contains $dev) {
          $layout.ConfigName = $dev
          $layout.RefreshPlotDeviceInfo()
          break
        }
      }

      # Проверка формата листа
      $availableMedia = @($layout.GetCanonicalMediaNames())
      if ($availableMedia.Count -gt 0) {
        $curMedia = $layout.CanonicalMediaName
        if (-not ($curMedia -and ($availableMedia -contains $curMedia))) {
          $matched = $null
          foreach ($code in @("A0", "A1", "A2", "A3", "A4")) {
            if ($curMedia -match $code) {
              $matched = @($availableMedia | Where-Object { $_ -match $code } | Select-Object -First 1)
              if ($matched.Count -gt 0) { break }
            }
          }
          if ($matched -and $matched.Count -gt 0) {
            $layout.CanonicalMediaName = $matched[0]
          } elseif ($availableMedia -contains "ISO_full_bleed_A3_(420.00_x_297.00_MM)") {
            $layout.CanonicalMediaName = "ISO_full_bleed_A3_(420.00_x_297.00_MM)"
          } else {
            $layout.CanonicalMediaName = $availableMedia[0]
          }
        }
      }

      $layout.PlotType = 4 # acLayout
      $layout.PlotWithLineweights = $true
      $layout.PlotWithPlotStyles = $true

      $pageFile = Join-Path $tempDir ("page_{0:D4}.pdf" -f $layout.TabOrder)
      if ($document.Plot.PlotToFile($pageFile)) {
        if ((Test-Path -LiteralPath $pageFile) -and (Get-Item -LiteralPath $pageFile).Length -gt 1024) {
          $pagePdfPaths.Add($pageFile)
        }
      }
    }
  }

  # Если в чертеже только пространство модели (Model Space)
  if ($pagePdfPaths.Count -eq 0) {
    $layout = $document.ModelSpace.Layout
    $devices = @($layout.GetPlotDeviceNames())
    $preferredDevices = @(
      "ZWCAD PDF(High Quality Print).pc5",
      "DWG to PDF.pc5",
      "DWG To PDF.pc3",
      "ZWCAD PDF(General Documentation).pc5",
      "Microsoft Print to PDF"
    )
    foreach ($dev in $preferredDevices) {
      if ($devices -contains $dev) {
        $layout.ConfigName = $dev
        $layout.RefreshPlotDeviceInfo()
        break
      }
    }
    $allMedia = @($layout.GetCanonicalMediaNames())
    $a0 = @($allMedia | Where-Object { $_ -match "A0" } | Select-Object -First 1)
    if ($a0.Count -gt 0) {
      $layout.CanonicalMediaName = $a0[0]
    } elseif ($allMedia.Count -gt 0) {
      $layout.CanonicalMediaName = $allMedia[0]
    }

    $layout.PlotType = 1 # acExtents
    $layout.CenterPlot = $true
    $layout.UseStandardScale = $true
    $layout.StandardScale = 0 # acScaleToFit
    $layout.PlotWithLineweights = $false
    $layout.PlotWithPlotStyles = $true

    $modelPageFile = Join-Path $tempDir "page_model.pdf"
    if ($document.Plot.PlotToFile($modelPageFile)) {
      if ((Test-Path -LiteralPath $modelPageFile) -and (Get-Item -LiteralPath $modelPageFile).Length -gt 1024) {
        $pagePdfPaths.Add($modelPageFile)
      }
    }
  }

  if ($pagePdfPaths.Count -eq 0) {
    throw "ZWCAD не смог сгенерировать ни одного листа PDF для чертежа."
  }

  # Объединение страниц в единый многостраничный PDF
  $tempCombinedPdf = Join-Path $tempDir "combined.pdf"
  if ($pagePdfPaths.Count -eq 1) {
    Copy-Item -LiteralPath $pagePdfPaths[0] -Destination $tempCombinedPdf -Force
  } else {
    $mergeScript = @'
import sys
try:
    import fitz
    doc = fitz.open()
    for p in sys.argv[2:]:
        with fitz.open(p) as page_doc:
            doc.insert_pdf(page_doc)
    doc.save(sys.argv[1])
    doc.close()
except ImportError:
    import pypdf
    writer = pypdf.PdfWriter()
    for p in sys.argv[2:]:
        reader = pypdf.PdfReader(p)
        for page in reader.pages:
            writer.add_page(page)
    with open(sys.argv[1], "wb") as f:
        writer.write(f)
'@
    $mergePyFile = Join-Path $tempDir "merge.py"
    [System.IO.File]::WriteAllText($mergePyFile, $mergeScript, [System.Text.Encoding]::UTF8)

    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $PythonExe
    $psi.Arguments = "`"$mergePyFile`" `"$tempCombinedPdf`" " + (($pagePdfPaths | ForEach-Object { "`"$_`"" }) -join " ")
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $psi.RedirectStandardError = $true
    $pyProc = [System.Diagnostics.Process]::Start($psi)
    $pyProc.WaitForExit(120000)
    if ($pyProc.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $tempCombinedPdf)) {
      $err = $pyProc.StandardError.ReadToEnd()
      throw "Ошибка объединения страниц PDF: $err"
    }
  }

  # Сохранение в целевую папку рядом с DWG или резервный кэш
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

  $result = @{
    ok = $true
    finalPath = $finalDestination
    isLocalFolder = ($finalDestination -eq $OutputPath)
    pageCount = $pagePdfPaths.Count
    progId = $usedProgId
  }
  Write-Output ($result | ConvertTo-Json -Compress)
} finally {
  if ($document) {
    try { $document.Close($false) } catch {}
  }
  if ($app) {
    try { $app.Quit() } catch {}
  }
  [System.GC]::Collect()
  [System.GC]::WaitForPendingFinalizers()

  if (Test-Path -LiteralPath $tempDir) {
    Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue
  }
}
