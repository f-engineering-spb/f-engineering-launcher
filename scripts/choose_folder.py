import os
import sys
import json
import subprocess

def pick_files():
    ps_script = os.path.join(os.path.dirname(__file__), "choose_folder.ps1")
    if os.path.exists(ps_script):
        try:
            res = subprocess.run(
                ["powershell.exe", "-STA", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps_script],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=15
            )
            if res.returncode == 0:
                lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
                return [p for p in lines if os.path.exists(p)]
        except Exception:
            pass

    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askopenfilenames(
            title="Select project files",
            filetypes=[
                ("Supported files", "*.dwg *.pdf *.xlsx *.docx *.xls *.doc *.jpg *.png"),
                ("All files", "*.*")
            ]
        )
        root.destroy()
        return list(selected) if selected else []
    except Exception:
        pass

    return []

if __name__ == "__main__":
    files = pick_files()
    if files:
        print(json.dumps(files, ensure_ascii=False))
