@echo off
setlocal
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
    "$wsh = New-Object -ComObject WScript.Shell; " ^
    "$desktop = [Environment]::GetFolderPath('Desktop'); " ^
    "$shortcut = $wsh.CreateShortcut(\"$desktop\F-Engineering Launcher.lnk\"); " ^
    "$pyw = Join-Path '%~dp0' 'runtime\python\pythonw.exe'; " ^
    "$app = Join-Path '%~dp0' 'app\flauncher.pyw'; " ^
    "$runCmd = Join-Path '%~dp0' 'Запуск_Лаунчера.cmd'; " ^
    "$ico = Join-Path '%~dp0' 'app\frontend\assets\flauncher.ico'; " ^
    "if (Test-Path $pyw) { $shortcut.TargetPath = $pyw; $shortcut.Arguments = '\"' + $app + '\"'; } else { $shortcut.TargetPath = $runCmd; }; " ^
    "$shortcut.WorkingDirectory = '%~dp0'; " ^
    "$shortcut.Description = 'F-Engineering Launcher v3'; " ^
    "if (Test-Path $ico) { $shortcut.IconLocation = $ico + ',0'; }; " ^
    "$shortcut.Save(); " ^
    "Write-Host ''; Write-Host '  [OK] Ярлык успешно создан на вашем Рабочем столе!' -ForegroundColor Green; Write-Host ''"
pause
endlocal