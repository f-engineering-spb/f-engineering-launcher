from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO_ROOT / "app" / "frontend"
RUNTIME_DIR = REPO_ROOT / "runtime"
MANIFESTS_DIR = RUNTIME_DIR / "manifests"
VERSION = "0.3.0-v3-left-panel"
SKIP_DIR_NAMES = {".git", "__pycache__", "node_modules", ".venv", "venv"}


def object_id_for_path(path: Path) -> str:
    return hashlib.sha1(str(path.resolve()).casefold().encode("utf-8")).hexdigest()[:16]


def file_extension(path: Path) -> str:
    suffix = path.suffix.upper().lstrip(".")
    return suffix or "NO_EXT"


def build_tree(folder: Path) -> tuple[dict, dict[str, int], int, int]:
    counts: dict[str, int] = {}
    folder_count = 0
    file_count = 0

    def walk(current: Path) -> dict:
        nonlocal folder_count, file_count
        folder_count += 1
        children = []
        try:
            entries = sorted(current.iterdir(), key=lambda item: (not item.is_dir(), item.name.casefold()))
        except OSError as error:
            return {
                "type": "folder",
                "name": current.name,
                "path": str(current),
                "error": str(error),
                "children": [],
            }

        for entry in entries:
            if entry.is_dir():
                if entry.name in SKIP_DIR_NAMES:
                    continue
                children.append(walk(entry))
            elif entry.is_file():
                ext = file_extension(entry)
                counts[ext] = counts.get(ext, 0) + 1
                file_count += 1
                children.append(
                    {
                        "type": "file",
                        "name": entry.name,
                        "path": str(entry),
                        "extension": ext,
                        "size": entry.stat().st_size,
                    }
                )

        return {"type": "folder", "name": current.name, "path": str(current), "children": children}

    return walk(folder), counts, folder_count, file_count


def scan_object(raw_path: str) -> dict:
    if not raw_path or not raw_path.strip():
        raise ValueError("Путь к папке объекта пустой")
    root = Path(raw_path.strip().strip('"')).expanduser()
    if not root.exists():
        raise FileNotFoundError(f"Папка не найдена: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Это не папка: {root}")

    tree, extension_counts, folder_count, file_count = build_tree(root)
    manifest = {
        "id": object_id_for_path(root),
        "name": root.name,
        "rootPath": str(root.resolve()),
        "scannedAt": datetime.now().isoformat(timespec="seconds"),
        "statistics": {
            "folders": folder_count,
            "files": file_count,
            "extensions": extension_counts,
        },
        "tree": tree,
    }
    MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)
    (MANIFESTS_DIR / f"{manifest['id']}.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def manifest_path(object_id: str) -> Path:
    return MANIFESTS_DIR / f"{object_id}.json"


def load_manifest(object_id: str) -> dict | None:
    path = manifest_path(object_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def manifest_summary(manifest: dict) -> dict:
    return {
        "id": manifest.get("id"),
        "name": manifest.get("name"),
        "rootPath": manifest.get("rootPath"),
        "scannedAt": manifest.get("scannedAt"),
        "statistics": manifest.get("statistics", {}),
    }


def list_object_summaries() -> list[dict]:
    MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)
    manifests: list[dict] = []
    for path in MANIFESTS_DIR.glob("*.json"):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifests.append(manifest_summary(manifest))
        except (OSError, json.JSONDecodeError):
            continue
    return sorted(manifests, key=lambda item: str(item.get("scannedAt", "")), reverse=True)


class LauncherHandler(BaseHTTPRequestHandler):
    server_version = "FEngineeringLauncherV3/0.1"

    def log_message(self, format: str, *args: object) -> None:
        logs_dir = RUNTIME_DIR / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        with (logs_dir / "server.log").open("a", encoding="utf-8") as log:
            log.write("%s - %s\n" % (self.log_date_time_string(), format % args))

    def send_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self.send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "service": "F-Engineering Launcher v3",
                    "version": VERSION,
                    "repoRoot": str(REPO_ROOT),
                    "runtime": str(RUNTIME_DIR),
                },
            )
            return

        if parsed.path == "/api/launcher-info":
            self.send_json(
                HTTPStatus.OK,
                {
                    "version": VERSION,
                    "frontend": str(FRONTEND_DIR),
                    "runtime": str(RUNTIME_DIR),
                    "port": self.server.server_port,
                },
            )
            return

        if parsed.path == "/api/objects":
            self.send_json(HTTPStatus.OK, {"items": list_object_summaries()})
            return

        if parsed.path.startswith("/api/objects/"):
            object_id = unquote(parsed.path.removeprefix("/api/objects/")).strip()
            manifest = load_manifest(object_id)
            if manifest:
                self.send_json(HTTPStatus.OK, manifest)
            else:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Объект не найден в manifest-хранилище"})
            return

        self.serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/objects/import":
            try:
                body = self.read_json()
                manifest = scan_object(str(body.get("path", "")))
                self.send_json(HTTPStatus.OK, manifest)
            except (ValueError, FileNotFoundError, NotADirectoryError, OSError, json.JSONDecodeError) as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return

        if parsed.path == "/api/objects/exclude":
            try:
                body = self.read_json()
                object_id = str(body.get("id", "")).strip()
                if not object_id:
                    raise ValueError("Не выбран объект для исключения")
                target = MANIFESTS_DIR / f"{object_id}.json"
                if target.exists():
                    target.unlink()
                self.send_json(HTTPStatus.OK, {"ok": True, "removed": object_id})
            except (ValueError, OSError, json.JSONDecodeError) as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return

        if parsed.path == "/api/choose-folder":
            try:
                import tkinter as tk
                from tkinter import filedialog

                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                selected = filedialog.askdirectory(title="Выберите папку объекта для F-Engineering Launcher v3")
                root.destroy()
                self.send_json(HTTPStatus.OK, {"path": selected})
            except Exception as error:
                self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"Диалог выбора папки недоступен: {error}"})
            return

        self.send_json(HTTPStatus.NOT_FOUND, {"error": "Маршрут не найден"})

    def serve_static(self, request_path: str) -> None:
        relative = "index.html" if request_path in ("", "/") else unquote(request_path).lstrip("/")
        target = (FRONTEND_DIR / relative).resolve()

        try:
            target.relative_to(FRONTEND_DIR.resolve())
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
            return

        if not target.exists() or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "text/javascript"}:
            content_type = f"{content_type}; charset=utf-8"
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run F-Engineering Launcher v3 local server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8780)
    args = parser.parse_args()

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    (RUNTIME_DIR / "cache").mkdir(exist_ok=True)
    MANIFESTS_DIR.mkdir(exist_ok=True)
    (RUNTIME_DIR / "logs").mkdir(exist_ok=True)

    server = ThreadingHTTPServer((args.host, args.port), LauncherHandler)
    print(f"F-Engineering Launcher v3: http://{args.host}:{args.port}/", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
