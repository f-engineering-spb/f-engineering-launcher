@echo off
setlocal
chcp 65001 >nul

echo ========================================================================
echo    F-Engineering Launcher v3 — Сборка автономного пакета (USB)
echo ========================================================================
echo Этот мастер подготовит готовую версию лаунчера «Всё включено»
echo со встроенным автономным Python, всеми библиотеками и Poppler.
echo На целевом ПК не потребуется ничего устанавливать.
echo.
echo Укажите букву диска флешки (например, E: или F:)
echo или просто нажмите ENTER для сборки в C:\Codex\FEngineering_Launcher_Portable:
set "USB_TARGET="
set /p USB_TARGET="Диск флешки или путь: "

if "%USB_TARGET%"=="" (
    set "USB_TARGET=C:\Codex\FEngineering_Launcher_Portable"
)

echo.
echo Запуск сборщика...
if exist "C:\Python314\python.exe" (
    "C:\Python314\python.exe" "%~dp0scripts\export_usb_package.py" "%USB_TARGET%"
) else (
    python "%~dp0scripts\export_usb_package.py" "%USB_TARGET%"
)

echo.
pause
endlocal