import os
import sys
import json
import subprocess

# Принудительно UTF-8 для stdout: иначе print кириллического пути в pipe
# кодирует системной страницей, и сервер видит знаки замены вместо букв.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

def _hidden_powershell_flags():
    # Запуск PowerShell без чёрного окна консоли: виден только сам диалог.
    if os.name != "nt":
        return {}
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {
            "startupinfo": startupinfo,
            "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
        }
    except Exception:
        return {}

def pick_folder():
    # Единственный путь: современный системный диалог выбора папки Windows.
    ps_script = os.path.join(os.path.dirname(__file__), "choose_folder.ps1")
    if os.path.exists(ps_script):
        try:
            res = subprocess.run(
                ["powershell.exe", "-STA", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps_script],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=120,
                **_hidden_powershell_flags()
            )
            if res.returncode == 0:
                lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
                valid = [p for p in lines if os.path.exists(p)]
                if valid:
                    return valid[0]
        except Exception:
            pass

    # Запасной путь: системный диалог выбора папки tkinter.
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(title="Выберите папку объекта")
        root.destroy()
        if selected and os.path.exists(selected):
            return selected
    except Exception:
        pass

    return ""

if __name__ == "__main__":
    folder = pick_folder()
    if folder:
        print(json.dumps(folder, ensure_ascii=False))
