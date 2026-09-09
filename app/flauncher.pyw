"""FLauncher — F-Engineering Launcher v3 как окно Windows.

Без консоли, без браузера: поднимает сервер в фоне (если ещё не поднят)
и показывает интерфейс в отдельном окне приложения.
Повторный запуск просто выводит уже открытое окно на передний план.
"""
import ctypes
import os
import socket
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(REPO_ROOT, "app", "backend", "server.py")
ICON = os.path.join(REPO_ROOT, "app", "frontend", "assets", "flauncher.ico")
PORT = 8780
GUI_MUTEX_PORT = 8799
URL = "http://127.0.0.1:%d/" % PORT
TITLE = "FLauncher"


def port_open(port):
    try:
        client = socket.create_connection(("127.0.0.1", port), timeout=0.3)
        client.close()
        return True
    except OSError:
        return False


def focus_existing_window():
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, TITLE)
        if hwnd:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
            return True
    except Exception:
        pass
    return False


def main():
    # Вторая копия не открывает новое окно, а показывает уже открытое.
    try:
        mutex = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        mutex.bind(("127.0.0.1", GUI_MUTEX_PORT))
    except OSError:
        focus_existing_window()
        return

    server_proc = None
    if not port_open(PORT):
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        server_proc = subprocess.Popen(
            [sys.executable, BACKEND, "--port", str(PORT)],
            cwd=REPO_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        deadline = time.time() + 25
        while time.time() < deadline:
            if port_open(PORT):
                break
            if server_proc.poll() is not None:
                return
            time.sleep(0.4)

    try:
        import webview

        webview.create_window(TITLE, URL, width=1400, height=900)
        webview.start(icon=ICON if os.path.exists(ICON) else None)
    finally:
        if server_proc is not None and server_proc.poll() is None:
            server_proc.terminate()


if __name__ == "__main__":
    main()
