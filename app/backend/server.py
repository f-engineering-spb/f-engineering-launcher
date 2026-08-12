from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import shutil
import subprocess
import time
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO_ROOT / "app" / "frontend"
RUNTIME_DIR = REPO_ROOT / "runtime"
MANIFESTS_DIR = RUNTIME_DIR / "manifests"
PDF_CACHE_DIR = RUNTIME_DIR / "cache" / "pdf"
VERSION = "0.4.0-v3-pdf-render"
SKIP_DIR_NAMES = {".git", "__pycache__", "node_modules", ".venv", "venv"}
DEFAULT_PDF_DPI = 300
PDF_PAGE_TIMEOUT_SECONDS = 25
PDF_DOCUMENT_TIMEOUT_SECONDS = 75
POPPLER_BIN_DIR = (
    Path.home()
    / ".cache"
    / "codex-runtimes"
    / "codex-primary-runtime"
    / "dependencies"
    / "native"
    / "poppler"
    / "Library"
    / "bin"
)


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


def pdf_cache_key(path: Path, dpi: int) -> str:
    stat = path.stat()
    raw = f"{path.resolve()}|{stat.st_mtime_ns}|{stat.st_size}|{dpi}"
    return hashlib.sha1(raw.casefold().encode("utf-8")).hexdigest()[:20]


def pdf_page_item(path: Path, key: str, page: int, png: Path) -> dict:
    return {
        "page": page,
        "name": f"{path.name} · стр. {page}",
        "url": f"/cache/pdf/{key}/{png.name}",
        "bytes": png.stat().st_size,
    }


def read_pdf_cache_manifest(path: Path, dpi: int, key: str, target_dir: Path) -> dict | None:
    manifest_path = target_dir / "manifest.json"
    manifest = None
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = None
        if manifest and (manifest.get("path") != str(path) or manifest.get("dpi") != dpi or manifest.get("cacheKey") != key):
            manifest = None
    if not manifest:
        legacy_items = []
        for png in sorted(target_dir.glob("page-*.png")):
            try:
                page = int(png.stem.removeprefix("page-"))
            except ValueError:
                continue
            if page > 0 and png.stat().st_size > 0:
                legacy_items.append(pdf_page_item(path, key, page, png))
        if not legacy_items:
            return None
        return {
            "name": path.name,
            "path": str(path),
            "dpi": dpi,
            "pages": max(item["page"] for item in legacy_items),
            "renderedPages": len(legacy_items),
            "cacheKey": key,
            "complete": False,
            "errors": [],
            "items": legacy_items,
        }
    items = []
    for item in manifest.get("items", []):
        page = int(item.get("page") or 0)
        png = target_dir / f"page-{page}.png"
        if page > 0 and png.exists() and png.stat().st_size > 0:
            items.append(pdf_page_item(path, key, page, png))
    if not items:
        return None
    manifest["items"] = items
    return manifest


def write_pdf_cache_manifest(
    path: Path,
    dpi: int,
    key: str,
    target_dir: Path,
    page_count: int,
    items: list[dict],
    errors: list[dict],
) -> None:
    manifest = {
        "name": path.name,
        "path": str(path),
        "dpi": dpi,
        "pages": page_count,
        "renderedPages": len(items),
        "cacheKey": key,
        "complete": len(items) == page_count and not errors,
        "errors": errors,
        "items": items,
        "updatedAt": datetime.now().isoformat(timespec="seconds"),
    }
    (target_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def poppler_tool(name: str) -> str | None:
    exe = POPPLER_BIN_DIR / f"{name}.exe"
    if exe.exists():
        return str(exe)
    found = shutil.which(name)
    if found and not found.lower().endswith(".cmd"):
        return found
    return found


def run_poppler(args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        process.kill()
        stdout, stderr = process.communicate()
        raise subprocess.TimeoutExpired(args, timeout, output=stdout, stderr=stderr) from error
    return subprocess.CompletedProcess(args=args, returncode=process.returncode, stdout=stdout, stderr=stderr)


def pdf_page_count(path: Path) -> int:
    pdfinfo = poppler_tool("pdfinfo")
    if not pdfinfo:
        raise RuntimeError("pdfinfo не найден. Нужен Poppler из runtime.")
    result = run_poppler(
        [pdfinfo, str(path)],
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "pdfinfo не смог прочитать PDF")
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise RuntimeError("pdfinfo не вернул количество страниц PDF")


def render_pdf(path: Path, dpi: int = DEFAULT_PDF_DPI) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"PDF не найден: {path}")
    if not path.is_file() or path.suffix.casefold() != ".pdf":
        raise ValueError(f"Это не PDF-файл: {path}")

    key = pdf_cache_key(path, dpi)
    target_dir = PDF_CACHE_DIR / key
    target_dir.mkdir(parents=True, exist_ok=True)
    cached_manifest = read_pdf_cache_manifest(path, dpi, key, target_dir)
    if cached_manifest:
        cached_items = cached_manifest["items"]
        cached_errors = cached_manifest.get("errors", [])
        return {
            "name": path.name,
            "path": str(path),
            "dpi": dpi,
            "pages": cached_manifest.get("pages", len(cached_items)),
            "renderedPages": len(cached_items),
            "cacheKey": key,
            "cacheHit": True,
            "cacheHitPages": len(cached_items),
            "newRenderedPages": 0,
            "errors": cached_errors,
            "items": cached_items,
        }

    pdftoppm = poppler_tool("pdftoppm")
    if not pdftoppm:
        raise RuntimeError("pdftoppm не найден. Нужен Poppler из runtime.")

    page_count = pdf_page_count(path)
    started_at = time.monotonic()

    pages = []
    errors = []
    rendered_count = 0
    cache_hit_count = 0

    for page in range(1, page_count + 1):
        if time.monotonic() - started_at > PDF_DOCUMENT_TIMEOUT_SECONDS:
            for skipped_page in range(page, page_count + 1):
                errors.append({"page": skipped_page, "error": f"PDF остановлен по лимиту {PDF_DOCUMENT_TIMEOUT_SECONDS} сек. на файл."})
            break

        png = target_dir / f"page-{page}.png"
        if png.exists() and png.stat().st_size > 0:
            cache_hit_count += 1
        else:
            for stale in target_dir.glob(f"page-{page}*.png"):
                stale.unlink()
            prefix = target_dir / f"page-{page}"
            try:
                result = run_poppler(
                    [
                        pdftoppm,
                        "-f",
                        str(page),
                        "-l",
                        str(page),
                        "-singlefile",
                        "-r",
                        str(dpi),
                        "-png",
                        str(path),
                        str(prefix),
                    ],
                    timeout=PDF_PAGE_TIMEOUT_SECONDS,
                )
                candidate = target_dir / f"page-{page}.png"
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "pdftoppm не смог отрендерить страницу")
                if not candidate.exists() or candidate.stat().st_size <= 0:
                    raise RuntimeError("pdftoppm не создал PNG страницы")
                rendered_count += 1
            except subprocess.TimeoutExpired:
                errors.append({"page": page, "error": f"Таймаут рендера страницы {page}: {PDF_PAGE_TIMEOUT_SECONDS} сек."})
                continue
            except (RuntimeError, OSError) as error:
                errors.append({"page": page, "error": str(error)})
                continue

        if png.exists() and png.stat().st_size > 0:
            pages.append(pdf_page_item(path, key, page, png))

    if not pages:
        result = run_poppler(
            [pdftoppm, "-v"],
            timeout=10,
        )
        tool_version = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"Не удалось отрендерить ни одной страницы PDF. {tool_version}. Ошибки: {errors}")

    write_pdf_cache_manifest(path, dpi, key, target_dir, page_count, pages, errors)
    return {
        "name": path.name,
        "path": str(path),
        "dpi": dpi,
        "pages": page_count,
        "renderedPages": len(pages),
        "cacheKey": key,
        "cacheHit": cache_hit_count == page_count,
        "cacheHitPages": cache_hit_count,
        "newRenderedPages": rendered_count,
        "errors": errors,
        "items": pages,
    }


def render_pdf_page(path: Path, page: int, dpi: int = DEFAULT_PDF_DPI) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"PDF не найден: {path}")
    if not path.is_file() or path.suffix.casefold() != ".pdf":
        raise ValueError(f"Это не PDF-файл: {path}")

    pdftoppm = poppler_tool("pdftoppm")
    if not pdftoppm:
        raise RuntimeError("pdftoppm не найден. Нужен Poppler из runtime.")

    page_count = pdf_page_count(path)
    if page < 1 or page > page_count:
        raise ValueError(f"Страница {page} вне диапазона 1-{page_count}")

    key = pdf_cache_key(path, dpi)
    target_dir = PDF_CACHE_DIR / key
    target_dir.mkdir(parents=True, exist_ok=True)
    png = target_dir / f"page-{page}.png"
    cache_hit = png.exists() and png.stat().st_size > 0

    if not cache_hit:
        for stale in target_dir.glob(f"page-{page}*.png"):
            stale.unlink()
        prefix = target_dir / f"page-{page}"
        try:
            result = run_poppler(
                [
                    pdftoppm,
                    "-f",
                    str(page),
                    "-l",
                    str(page),
                    "-singlefile",
                    "-r",
                    str(dpi),
                    "-png",
                    str(path),
                    str(prefix),
                ],
                timeout=PDF_PAGE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(f"Таймаут рендера страницы {page}: {PDF_PAGE_TIMEOUT_SECONDS} сек.") from error
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "pdftoppm не смог отрендерить страницу")
    if not png.exists() or png.stat().st_size <= 0:
        raise RuntimeError("pdftoppm не создал PNG страницы")

    item = pdf_page_item(path, key, page, png)
    cached_manifest = read_pdf_cache_manifest(path, dpi, key, target_dir)
    items_by_page = {existing["page"]: existing for existing in (cached_manifest or {}).get("items", [])}
    items_by_page[page] = item
    items = [items_by_page[index] for index in sorted(items_by_page)]
    write_pdf_cache_manifest(path, dpi, key, target_dir, page_count, items, (cached_manifest or {}).get("errors", []))

    return {
        "name": path.name,
        "path": str(path),
        "dpi": dpi,
        "pages": page_count,
        "page": page,
        "cacheKey": key,
        "cacheHit": cache_hit,
        "item": item,
    }


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

        if parsed.path.startswith("/cache/"):
            self.serve_cache(parsed.path)
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

        if parsed.path == "/api/pdf/render":
            try:
                body = self.read_json()
                raw_files = body.get("files", [])
                dpi = int(body.get("dpi") or DEFAULT_PDF_DPI)
                if dpi < 72 or dpi > 600:
                    raise ValueError("DPI должен быть в диапазоне 72-600")
                if not isinstance(raw_files, list) or not raw_files:
                    raise ValueError("Не выбраны PDF-файлы для отображения")
                if len(raw_files) > 25:
                    raise ValueError("За один раз пока можно отрендерить не больше 25 PDF")
                documents = [render_pdf(Path(str(file_path)), dpi=dpi) for file_path in raw_files]
                document_errors = [
                    {"document": document["name"], "path": document["path"], **error}
                    for document in documents
                    for error in document.get("errors", [])
                ]
                self.send_json(
                    HTTPStatus.OK,
                    {
                        "dpi": dpi,
                        "documents": documents,
                        "totalPages": sum(document["pages"] for document in documents),
                        "renderedPages": sum(document["renderedPages"] for document in documents),
                        "errors": document_errors,
                        "renderedAt": datetime.now().isoformat(timespec="seconds"),
                    },
                )
            except (ValueError, FileNotFoundError, RuntimeError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return

        if parsed.path == "/api/pdf/page":
            try:
                body = self.read_json()
                raw_file = str(body.get("file", "")).strip()
                page = int(body.get("page") or 1)
                dpi = int(body.get("dpi") or DEFAULT_PDF_DPI)
                if dpi < 72 or dpi > 600:
                    raise ValueError("DPI должен быть в диапазоне 72-600")
                if not raw_file:
                    raise ValueError("Не выбран PDF-файл для отображения")
                self.send_json(HTTPStatus.OK, render_pdf_page(Path(raw_file), page=page, dpi=dpi))
            except (ValueError, FileNotFoundError, RuntimeError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return

        if parsed.path == "/api/open-file":
            try:
                body = self.read_json()
                raw_file = str(body.get("path", "")).strip()
                if not raw_file:
                    raise ValueError("Не выбран файл для открытия")
                target = Path(raw_file).expanduser()
                if not target.exists() or not target.is_file():
                    raise FileNotFoundError(f"Файл не найден: {target}")
                if os.name == "nt":
                    os.startfile(str(target))  # type: ignore[attr-defined]
                else:
                    subprocess.Popen(["xdg-open", str(target)])
                self.send_json(HTTPStatus.OK, {"ok": True, "path": str(target)})
            except (ValueError, FileNotFoundError, OSError, json.JSONDecodeError) as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return

        self.send_json(HTTPStatus.NOT_FOUND, {"error": "Маршрут не найден"})

    def serve_cache(self, request_path: str) -> None:
        relative = unquote(request_path).removeprefix("/cache/").lstrip("/")
        target = (RUNTIME_DIR / "cache" / relative).resolve()

        try:
            target.relative_to((RUNTIME_DIR / "cache").resolve())
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
            return

        if not target.exists() or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "private, max-age=31536000, immutable")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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
    PDF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    MANIFESTS_DIR.mkdir(exist_ok=True)
    (RUNTIME_DIR / "logs").mkdir(exist_ok=True)

    server = ThreadingHTTPServer((args.host, args.port), LauncherHandler)
    print(f"F-Engineering Launcher v3: http://{args.host}:{args.port}/", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
