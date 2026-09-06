param(
  [Parameter(Mandatory = $true)][string]$InputPath
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public static class LauncherWin32
{
  [DllImport("user32.dll")]
  public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")]
  public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
  [DllImport("user32.dll")]
  public static extern bool BringWindowToTop(IntPtr hWnd);
  [DllImport("user32.dll")]
  public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")]
  public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
  [DllImport("user32.dll")]
  public static extern bool AttachThreadInput(uint idAttach, uint idAttachTo, bool fAttach);
  [DllImport("user32.dll")]
  public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);
  [DllImport("kernel32.dll")]
  public static extern uint GetCurrentThreadId();

  public static void ActivateMainWindow(string processName)
  {
    System.Diagnostics.Process[] processes =
      System.Diagnostics.Process.GetProcessesByName(processName);
    foreach (System.Diagnostics.Process proc in processes)
    {
      if (proc.MainWindowHandle == IntPtr.Zero) continue;
      Activate(proc.MainWindowHandle);
      return;
    }
  }

  public static void Activate(IntPtr hWnd)
  {
    if (hWnd == IntPtr.Zero) return;
    ShowWindow(hWnd, 3);
    BringWindowToTop(hWnd);
    uint cur = GetCurrentThreadId();
    uint fgPid;
    uint targetPid;
    uint fg = GetWindowThreadProcessId(GetForegroundWindow(), out fgPid);
    uint target = GetWindowThreadProcessId(hWnd, out targetPid);
    bool ok1 = false;
    bool ok2 = false;
    if (fg != 0 && target != 0)
    {
      ok1 = AttachThreadInput(cur, target, true);
      ok2 = (fg != target) && AttachThreadInput(cur, fg, true);
    }
    keybd_event(0x12, 0, 0x0001, UIntPtr.Zero);
    keybd_event(0x12, 0, 0x0003, UIntPtr.Zero);
    SetForegroundWindow(hWnd);
    if (ok1) AttachThreadInput(cur, target, false);
    if (ok2) AttachThreadInput(cur, fg, false);
  }
}
"@

function Activate-ZwcadWindow {
  for ($attempt = 0; $attempt -lt 24; $attempt += 1) {
    if (Get-Process -Name "ZWCAD" -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 }) {
      [LauncherWin32]::ActivateMainWindow("ZWCAD")
      return
    }
    Start-Sleep -Milliseconds 500
  }
}

if (-not (Test-Path -LiteralPath $InputPath -PathType Leaf)) {
  throw "DWG file was not found: $InputPath"
}

$running = Get-Process -Name "ZWCAD" -ErrorAction SilentlyContinue
if (-not $running) {
  Start-Process -FilePath $InputPath
  Activate-ZwcadWindow
  exit 0
}

$app = $null
try {
  # Attach to the already running ZWCAD session.  GetActiveObject throws when
  # ZWCAD is not registered, so the association launch is used as a fallback.
  $app = [System.Runtime.InteropServices.Marshal]::GetActiveObject("ZWCAD.Application.2025")
} catch {
  Start-Process -FilePath $InputPath
  Activate-ZwcadWindow
  exit 0
}

if ($null -eq $app) {
  Start-Process -FilePath $InputPath
  Activate-ZwcadWindow
  exit 0
}

$app.Visible = $true
$document = $app.Documents.Open($InputPath, $true)
if (-not $document) {
  throw "ZWCAD did not open the DWG file."
}
try {
  # Fit the whole drawing into the viewport and center it, the same way the
  # ZOOM / Extents command works in ZWCAD and AutoCAD.  Without this ZWCAD
  # keeps the previous viewport, which can look shifted and over-zoomed.
  $app.ZoomExtents()
} catch {
  # ZoomExtents is not present in every ZWCAD build; the document is already
  # open, so the lack of auto-fit is not fatal.
}
Activate-ZwcadWindow
