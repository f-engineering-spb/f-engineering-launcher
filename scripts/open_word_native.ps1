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

function Activate-AppWindow([string]$ProcessName) {
  for ($attempt = 0; $attempt -lt 20; $attempt += 1) {
    if (Get-Process -Name $ProcessName -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 }) {
      [LauncherWin32]::ActivateMainWindow($ProcessName)
      return
    }
    Start-Sleep -Milliseconds 500
  }
}

if (-not (Test-Path -LiteralPath $InputPath -PathType Leaf)) {
  throw "Word file was not found: $InputPath"
}

$word = $null
$document = $null
try {
  try {
    # Attach to an already running Word session.  GetActiveObject throws when
    # no Word instance is running, so a fresh one is created below.  It never
    # silently spawns a hidden /Automation copy like GetObject can.
    $word = [System.Runtime.InteropServices.Marshal]::GetActiveObject("Word.Application")
  } catch {
    $word = New-Object -ComObject Word.Application
  }
  $word.Visible = $true
  $document = $word.Documents.Open($InputPath, $false, $false)
  if (-not $document) {
    throw "Word did not open the document."
  }
  $word.Activate()
  Activate-AppWindow "WINWORD"
} finally {
  if ($document) { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($document) | Out-Null }
  if ($word) { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null }
  [GC]::Collect()
  [GC]::WaitForPendingFinalizers()
}
