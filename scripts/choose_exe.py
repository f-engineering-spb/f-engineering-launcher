import os
import sys
import json
import subprocess

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

def _hidden_powershell_flags():
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

def pick_exe():
    ps_script = os.path.join(os.path.dirname(__file__), "choose_exe.ps1")
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

    # Fallback tkinter
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askopenfilename(
            title="Выберите программу для запуска (.exe)",
            filetypes=[("Исполняемые файлы", "*.exe"), ("Все файлы", "*.*")]
        )
        root.destroy()
        if selected and os.path.exists(selected):
            return selected
    except Exception:
        pass

    return ""

if __name__ == "__main__":
    exe = pick_exe()
    if exe:
        print(json.dumps(exe, ensure_ascii=False))
