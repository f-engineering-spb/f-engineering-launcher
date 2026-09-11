import os
import sys
import shutil
import subprocess
from pathlib import Path

SOURCE_PORTABLE = Path(r"C:\Codex\FEngineering_Launcher_Portable")
SOURCE_ZIP = Path(r"C:\Codex\FEngineering_Launcher_v3_Portable.zip")

def get_removable_drives():
    drives = []
    import ctypes
    kernel32 = ctypes.windll.kernel32
    bitmask = kernel32.GetLogicalDrives()
    for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
        if bitmask & (1 << (ord(letter) - ord('A'))):
            root = f"{letter}:\\"
            dtype = kernel32.GetDriveTypeW(root)
            if dtype == 2:  # DRIVE_REMOVABLE
                drives.append(letter)
    return drives

def main():
    print("=" * 72)
    print("  F-Engineering Launcher v3 — Запись на флешку (USB Deploy)")
    print("=" * 72)

    # 1. Определение целевого диска
    target_drive = sys.argv[1].upper().rstrip(":\\") if len(sys.argv) > 1 else None
    if not target_drive:
        removables = get_removable_drives()
        if len(removables) == 1:
            target_drive = removables[0]
            print(f"Автоматически обнаружена флешка: [{target_drive}:]")
        elif len(removables) > 1:
            print("Обнаружено несколько флешек:")
            for i, d in enumerate(removables, 1):
                print(f"  [{i}] Диск {d}:")
            choice = input(f"Выберите диск (1-{len(removables)}): ").strip()
            target_drive = removables[int(choice) - 1]
        else:
            target_drive = input("Введите букву флешки (например, D): ").strip().upper().rstrip(":\\")

    usb_root = Path(f"{target_drive}:\\")
    if not usb_root.exists():
        print(f"ОШИБКА: Диск {usb_root} не найден!")
        sys.exit(1)

    print(f"Целевой диск: {usb_root}")
    print()

    # 2. Проверка исходных файлов
    if not SOURCE_PORTABLE.exists() or not SOURCE_ZIP.exists():
        print("Подготовка локальной сборки в C:\\Codex...")
        subprocess.run([sys.executable, str(Path(__file__).parent / "export_usb_package.py")], check=True)

    # 3. Копирование папки FEngineering_Launcher
    dest_folder = usb_root / "FEngineering_Launcher"
    print(f"[1/4] Копирование автономной папки программы в {dest_folder}...")
    print("      (Это займет около 15-25 секунд, файлы копируются без сжатия)...", flush=True)

    # Используем robocopy для максимальной скорости на Windows
    cmd = ["robocopy", str(SOURCE_PORTABLE), str(dest_folder), "/E", "/R:1", "/W:1", "/NFL", "/NDL", "/NP", "/NJH", "/NJS"]
    subprocess.run(cmd)
    print("      [OK] Папка программы скопирована.")

    # 4. Копирование ZIP-архива
    print("[2/4] Копирование компактного архива для передачи коллегам...", end=" ", flush=True)
    shutil.copy2(SOURCE_ZIP, usb_root / SOURCE_ZIP.name)
    print("[OK]")

    # 5. Создание файлов запуска в корне флешки
    print("[3/4] Создание файлов быстрого запуска на флешке...", end=" ", flush=True)

    # 5.1. Запуск_Лаунчера.cmd (прямо с флешки)
    run_cmd = """@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0FEngineering_Launcher"
call "Запуск_Лаунчера.cmd"
endlocal
"""
    (usb_root / "Запуск_Лаунчера.cmd").write_text(run_cmd, encoding="utf-8")

    # 5.2. Установить_на_этот_компьютер.cmd (в 1 клик на рабочий стол)
    install_cmd = """@echo off
setlocal
chcp 65001 >nul
echo ========================================================================
echo    Установка F-Engineering Launcher на данный компьютер
echo ========================================================================
echo.
echo 1. Копирование файлов программы в профиль пользователя...
set "TARGET_DIR=%LOCALAPPDATA%\\FEngineering_Launcher"
if not exist "%TARGET_DIR%" mkdir "%TARGET_DIR%"
xcopy "%~dp0FEngineering_Launcher\\*" "%TARGET_DIR%\\" /E /I /Y /Q >nul

echo 2. Создание ярлыка на Рабочем столе...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$wsh = New-Object -ComObject WScript.Shell; $desktop = [Environment]::GetFolderPath('Desktop'); $s = $wsh.CreateShortcut(\\"$desktop\\F-Engineering Launcher.lnk\\"); $s.TargetPath = '%TARGET_DIR%\\runtime\\python\\pythonw.exe'; $s.Arguments = '\\"%TARGET_DIR%\\app\\flauncher.pyw\\"'; $s.WorkingDirectory = '%TARGET_DIR%'; $ico = '%TARGET_DIR%\\app\\frontend\\assets\\flauncher.ico'; if (Test-Path $ico) { $s.IconLocation = $ico + ',0' }; $s.Save();"

echo.
echo [OK] Установка успешно завершена!
echo      Ярлык «F-Engineering Launcher» создан на вашем Рабочем столе.
echo.
echo Запуск приложения...
start "" "%TARGET_DIR%\\runtime\\python\\pythonw.exe" "%TARGET_DIR%\\app\\flauncher.pyw"
timeout /t 3 >nul
endlocal
"""
    (usb_root / "Установить_на_этот_компьютер.cmd").write_text(install_cmd, encoding="utf-8")

    # 5.3. ИНСТРУКЦИЯ.txt
    readme = """========================================================================
   F-Engineering Launcher v3 — Автономный пакет (USB)
========================================================================

На целевом компьютере НЕ ТРЕБУЕТСЯ ничего устанавливать (ни Python, ни библиотеки).
Всё уже встроено в папку программы!

ВАРИАНТ 1 (Запуск прямо с флешки без установки):
Дважды кликните по файлу:
«Запуск_Лаунчера.cmd»
Лаунчер сразу откроется в отдельном окне.

ВАРИАНТ 2 (Установка на компьютер в 1 клик):
Дважды кликните по файлу:
«Установить_на_этот_компьютер.cmd»
Программа скопируется на ПК, создаст ярлык на Рабочем столе и сразу запустится.
После этого флешку можно извлечь.

ВАРИАНТ 3 (Через архив):
Если вы хотите отправить программу коллеге по почте или через сетевой диск,
возьмите файл «FEngineering_Launcher_v3_Portable.zip» (78 МБ).
"""
    (usb_root / "ИНСТРУКЦИЯ.txt").write_text(readme, encoding="utf-8")
    print("[OK]")

    # 6. Проверка
    print("[4/4] Проверка готовности...", end=" ", flush=True)
    if (usb_root / "Запуск_Лаунчера.cmd").exists() and (dest_folder / "runtime" / "python" / "pythonw.exe").exists():
        print("[OK]")
        print()
        print("=" * 72)
        print("  ФЛЕШКА УСПЕШНО ПОДГОТОВЛЕНА И ГОТОВА К РАБОТЕ!")
        print("=" * 72)
        print(f"  Диск: {usb_root}")
        print("  Содержимое флешки:")
        print("    1. Запуск_Лаунчера.cmd              (запуск прямо с флешки)")
        print("    2. Установить_на_этот_компьютер.cmd  (копирование на ПК + ярлык)")
        print("    3. FEngineering_Launcher\\           (автономное ядро программы)")
        print("    4. FEngineering_Launcher_v3_Portable.zip (архив для пересылки)")
        print("    5. ИНСТРУКЦИЯ.txt")
        print("=" * 72)
        print()
        print("Теперь можно извлекать флешку и использовать на любом компьютере!")
    else:
        print("[ПРЕДУПРЕЖДЕНИЕ: Некоторые файлы не найдены]")

if __name__ == "__main__":
    main()
