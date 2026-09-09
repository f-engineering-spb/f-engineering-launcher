"""FLauncher — F-Engineering Launcher v3 как окно Windows.

Без консоли: проверяет и поднимает backend-сервер в фоне (порты 8780..8789)
и открывает интерфейс в отдельном окне приложения через pywebview.
При отсутствии pywebview или ошибке вебвью открывает окно в Edge/Chrome.
"""
import ctypes
import os
import socket
import subprocess
import sys
import time
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(REPO_ROOT, "app", "backend", "server.py")
ICON = os.path.join(REPO_ROOT, "app", "frontend", "assets", "flauncher.ico")
TITLE = "F-Engineering Launcher"
GUI_MUTEX_PORT = 8799
LOGS_DIR = os.path.join(REPO_ROOT, "runtime", "logs")


def log(msg: str) -> None:
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        log_file = os.path.join(LOGS_DIR, "launcher_gui.log")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def is_server_healthy(port: int) -> bool:
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/health")
        with urllib.request.urlopen(req, timeout=0.8) as resp:
            return resp.status == 200
    except Exception:
        return False


def is_port_free(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))
            return True
    except OSError:
        return False


def find_or_start_server() -> int:
    # 1. Проверяем, может сервер уже работает на одном из портов 8780..8789
    for p in range(8780, 8790):
        if is_server_healthy(p):
            log(f"Found already healthy server on port {p}")
            return p

    # 2. Ищем первый свободный порт
    target_port = None
    for p in range(8780, 8790):
        if is_port_free(p):
            target_port = p
            break

    if target_port is None:
        target_port = 8781

    log(f"Starting backend on port {target_port}")
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    # Запускаем server.py
    python_exe = sys.executable
    subprocess.Popen(
        [python_exe, BACKEND, "--port", str(target_port)],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )

    deadline = time.time() + 20
    while time.time() < deadline:
        if is_server_healthy(target_port):
            log(f"Server on port {target_port} became healthy")
            return target_port
        time.sleep(0.3)

    log(f"Warning: server on port {target_port} health check timed out, attempting to use it anyway")
    return target_port


def focus_existing_window() -> bool:
    try:
        user32 = ctypes.windll.user32
        for t in [TITLE, "FLauncher"]:
            hwnd = user32.FindWindowW(None, t)
            if hwnd:
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                user32.SetForegroundWindow(hwnd)
                return True
    except Exception:
        pass
    return False


def open_browser_window(url: str) -> None:
    edge_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for p in edge_paths:
        if os.path.exists(p):
            profile = os.path.join(os.environ.get("LOCALAPPDATA", ""), "FEngineeringLauncher", "AppProfile")
            os.makedirs(profile, exist_ok=True)
            subprocess.Popen([p, f"--app={url}", f"--user-data-dir={profile}", "--no-first-run"])
            return

    import webbrowser
    webbrowser.open(url)


def main():
    try:
        mutex = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        mutex.bind(("127.0.0.1", GUI_MUTEX_PORT))
    except OSError:
        if focus_existing_window():
            log("Focused existing window, exiting duplicate process")
            return

    port = find_or_start_server()
    url = f"http://127.0.0.1:{port}/"

    opened_webview = False
    try:
        import webview
        log(f"Opening pywebview window at {url}")
        webview.create_window(TITLE, url, width=1400, height=900)
        opened_webview = True
        webview.start(icon=ICON if os.path.exists(ICON) else None)
    except Exception as e:
        log(f"pywebview failed: {e}, falling back to browser window")
        if not opened_webview:
            open_browser_window(url)


if __name__ == "__main__":
    main()
