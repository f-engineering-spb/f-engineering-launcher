from __future__ import annotations

import argparse
import hashlib
import html
import json
import mimetypes
import os
import shutil
import string
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

try:
    import openpyxl
except ImportError:  # pragma: no cover - reported through the local API
    openpyxl = None


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO_ROOT / "app" / "frontend"
RUNTIME_DIR = REPO_ROOT / "runtime"
MANIFESTS_DIR = RUNTIME_DIR / "manifests"
PDF_CACHE_DIR = RUNTIME_DIR / "cache" / "pdf"
WORD_CACHE_DIR = RUNTIME_DIR / "cache" / "word"
EXCEL_CACHE_DIR = RUNTIME_DIR / "cache" / "excel"
DWG_CACHE_DIR = RUNTIME_DIR / "cache" / "dwg"
WORD_CONVERT_SCRIPT = REPO_ROOT / "scripts" / "convert_word_to_pdf.ps1"
EXCEL_CONVERT_SCRIPT = REPO_ROOT / "scripts" / "convert_excel_to_pdf.ps1"
EXCEL_XLS_CONVERT_SCRIPT = REPO_ROOT / "scripts" / "convert_xls_to_xlsx.ps1"
DWG_RENDER_SCRIPT = REPO_ROOT / "scripts" / "render_dwg_model_space.ps1"
DWG_SMART_RENDER_SCRIPT = REPO_ROOT / "scripts" / "render_dwg_smart.ps1"
DWG_REVIEW_OPEN_SCRIPT = REPO_ROOT / "scripts" / "open_dwg_review_copy.ps1"
WORD_NATIVE_OPEN_SCRIPT = REPO_ROOT / "scripts" / "open_word_native.ps1"
EXCEL_NATIVE_OPEN_SCRIPT = REPO_ROOT / "scripts" / "open_excel_native.ps1"
VERSION = "0.4.0-v3-pdf-render"
SKIP_DIR_NAMES = {".git", "__pycache__", "node_modules", ".venv", "venv"}
DEFAULT_PDF_DPI = 300
PDF_PAGE_TIMEOUT_SECONDS = 25
PDF_DOCUMENT_TIMEOUT_SECONDS = 600
WORD_CONVERT_TIMEOUT_SECONDS = 120
EXCEL_CONVERT_TIMEOUT_SECONDS = 180
DWG_RENDER_TIMEOUT_SECONDS = 600
DWG_MODEL_PAGE_TIMEOUT_SECONDS = 120
DWG_OPEN_TIMEOUT_SECONDS = 60
NATIVE_OPEN_TIMEOUT_SECONDS = 60
MAX_XLSX_ROWS = 2000
MAX_XLSX_COLS = 100
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
# Portable Poppler shipped inside a release archive.  Checked before the
# machine-wide cache path so a copied release works on a fresh computer.
PORTABLE_POPPLER_BIN_DIR = REPO_ROOT / "runtime" / "tools" / "poppler" / "Library" / "bin"


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
            if entry.name.startswith("~$") or entry.name.startswith(".~"):
                continue
            if entry.is_dir():
                if entry.name in SKIP_DIR_NAMES:
                    continue
                children.append(walk(entry))
            elif entry.is_file():
                ext = file_extension(entry)
                counts[ext] = counts.get(ext, 0) + 1
                file_count += 1
                try:
                    stat = entry.stat()
                    size = stat.st_size
                    mtime_ns = stat.st_mtime_ns
                    stat_error = None
                except OSError as stat_err:
                    size = 0
                    mtime_ns = 0
                    stat_error = str(stat_err)
                node = {
                    "type": "file",
                    "name": entry.name,
                    "path": str(entry),
                    "extension": ext,
                    "size": size,
                    "mtimeNs": mtime_ns,
                }
                if stat_error:
                    node["error"] = stat_error
                children.append(node)

        return {"type": "folder", "name": current.name, "path": str(current), "children": children}

    return walk(folder), counts, folder_count, file_count


def tree_file_signatures(tree: dict | None) -> dict[str, dict]:
    result: dict[str, dict] = {}

    def walk(node: dict) -> None:
        if node.get("type") == "file":
            path = node.get("path") or ""
            result[path.casefold()] = {
                "path": path,
                "name": node.get("name"),
                "size": node.get("size"),
                "mtimeNs": node.get("mtimeNs"),
            }
        for child in node.get("children") or []:
            walk(child)

    if tree:
        walk(tree)
    return result


def diff_trees(old_tree: dict | None, new_tree: dict | None) -> dict:
    old = tree_file_signatures(old_tree)
    new = tree_file_signatures(new_tree)

    def signature(entry: dict) -> tuple:
        return (entry.get("size"), entry.get("mtimeNs"))

    added: list[str] = []
    changed: list[str] = []
    removed: list[str] = []
    unchanged: list[str] = []

    for key, entry in new.items():
        old_entry = old.get(key)
        if old_entry is None:
            added.append(entry["path"])
        elif signature(old_entry) != signature(entry):
            changed.append(entry["path"])
        else:
            unchanged.append(entry["path"])

    for key, entry in old.items():
        if key not in new:
            removed.append(entry["path"])

    # Эвристика переименования: если исчез ровно один файл и появился ровно
    # один новый с тем же размером, считаем это переносом/заменой имени,
    # а не «удалён + добавлен». Срабатывает только для однозначной пары,
    # чтобы не объединять случайные файлы одинакового размера.
    renamed: set[str] = set()
    if len(removed) == 1 and len(added) == 1:
        removed_path = removed[0]
        added_path = added[0]
        removed_entry = old.get(removed_path.casefold())
        added_entry = new.get(added_path.casefold())
        if (
            removed_entry is not None
            and added_entry is not None
            and removed_entry.get("size") == added_entry.get("size")
        ):
            renamed.add(added_path.casefold())
            renamed.add(removed_path.casefold())
            changed.append(added_path)
    if renamed:
        added = [path for path in added if path.casefold() not in renamed]
        removed = [path for path in removed if path.casefold() not in renamed]

    return {
        "added": sorted(added),
        "changed": sorted(changed),
        "removed": sorted(removed),
        "unchanged": sorted(unchanged),
    }



def get_available_drives() -> list[dict]:
    drives = []
    for letter in string.ascii_uppercase:
        drive_path = Path(f"{letter}:\\")
        if drive_path.exists():
            label = f"Диск {letter}:"
            if letter == "H":
                label = "Google Drive (H:)"
            elif letter == "C":
                label = "Локальный диск (C:)"
            drives.append({"letter": f"{letter}:", "path": str(drive_path), "label": label})
    return drives


def discover_quick_projects() -> list[dict]:
    candidates = [
        Path(r"C:\Users\a9379\Downloads\Фасады корпуса 7.2"),
        Path(r"C:\Users\a9379\Downloads\Фасады корпуса 7.2\Фасады корпуса 7.2"),
        Path(r"H:\Общие диски\000_Объекты СПб\02_2026\03_ЖК МОД"),
        Path(r"H:\Общие диски\000_Объекты СПб\02_2026\03_ЖК МОД\01-КБ"),
        Path(r"H:\Общие диски\000_Объекты СПб\02_2026\03_ЖК МОД\01-КБ\04- Проекты"),
        Path(r"H:\Общие диски\000_Объекты СПб\02_2026\01 _Голден сити Г9 Корпус 1 22193-09"),
        Path(r"H:\Общие диски\000_Объекты СПб\01_2022-2025\12_ЖК МОД 21081-03"),
        Path(r"C:\Users\a9379\Downloads\01. Фасады_Тендерный пакет (2)"),
    ]
    projects = []
    seen = set()
    for candidate in candidates:
        try:
            if candidate.exists() and candidate.is_dir() and str(candidate).casefold() not in seen:
                seen.add(str(candidate).casefold())
                projects.append({
                    "name": candidate.name,
                    "path": str(candidate.resolve()),
                    "parentName": candidate.parent.name,
                })
        except Exception:
            continue
    return projects


def browse_filesystem(raw_path: str = "") -> dict:
    drives = get_available_drives()
    quick_projects = discover_quick_projects()
    if not raw_path or not raw_path.strip():
        default_dir = Path("H:/Общие диски/000_Объекты СПб") if Path("H:/Общие диски/000_Объекты СПб").exists() else Path("C:/Users/a9379")
        target = default_dir
    else:
        target = Path(raw_path.strip().strip('"')).expanduser()

    if not target.exists():
        target = Path.home()

    if target.is_file():
        target = target.parent

    target = target.resolve()

    folders = []
    files = []
    dwg_count = 0
    pdf_count = 0
    excel_count = 0
    word_count = 0

    try:
        for entry in target.iterdir():
            try:
                if entry.name.startswith("~$") or entry.name.startswith(".~"):
                    continue
                if entry.is_dir():
                    folders.append({
                        "name": entry.name,
                        "path": str(entry.resolve()),
                    })
                elif entry.is_file():
                    ext = entry.suffix.lower()
                    if ext == ".dwg":
                        dwg_count += 1
                    elif ext == ".pdf":
                        pdf_count += 1
                    elif ext in (".xlsx", ".xls"):
                        excel_count += 1
                    elif ext in (".docx", ".doc"):
                        word_count += 1
                    files.append({
                        "name": entry.name,
                        "path": str(entry.resolve()),
                        "ext": ext,
                        "size": entry.stat().st_size,
                    })
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError):
        pass

    folders.sort(key=lambda x: x["name"].casefold())
    files.sort(key=lambda x: x["name"].casefold())

    parent_path = str(target.parent.resolve()) if target.parent != target else None

    return {
        "current": str(target),
        "parent": parent_path,
        "drives": drives,
        "folders": folders,
        "files": files[:100],
        "totalFiles": len(files),
        "totalFolders": len(folders),
        "stats": {
            "dwg": dwg_count,
            "pdf": pdf_count,
            "excel": excel_count,
            "word": word_count,
            "other": len(files) - (dwg_count + pdf_count + excel_count + word_count),
        },
        "quickProjects": quick_projects,
    }


def scan_object(raw_path: str) -> dict:
    if not raw_path or not raw_path.strip():
        raise ValueError("Путь к папке объекта пустой")
    root = Path(raw_path.strip().strip('"')).expanduser()
    if not root.exists():
        raise FileNotFoundError(f"Путь не найден: {root}")
    if root.is_file():
        root = root.parent
    if not root.is_dir():
        raise NotADirectoryError(f"Это не папка: {root}")

    object_id = object_id_for_path(root)
    previous = load_manifest(object_id)
    previous_tree = (previous or {}).get("tree")

    tree, extension_counts, folder_count, file_count = build_tree(root)
    last_diff = diff_trees(previous_tree, tree)
    manifest = {
        "id": object_id,
        "name": root.name,
        "rootPath": str(root.resolve()),
        "scannedAt": datetime.now().isoformat(timespec="seconds"),
        "statistics": {
            "folders": folder_count,
            "files": file_count,
            "extensions": extension_counts,
        },
        "tree": tree,
        "lastDiff": last_diff,
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


def file_cache_key(path: Path, purpose: str) -> str:
    stat = path.stat()
    raw = f"{purpose}|{path.resolve()}|{stat.st_mtime_ns}|{stat.st_size}"
    return hashlib.sha1(raw.casefold().encode("utf-8")).hexdigest()[:20]


def is_word_file(path: Path) -> bool:
    if path.name.startswith("~$") or path.name.startswith(".~"):
        return False
    return path.suffix.casefold() in {".doc", ".docx"}


def is_excel_file(path: Path) -> bool:
    if path.name.startswith("~$") or path.name.startswith(".~"):
        return False
    return path.suffix.casefold() in {".xls", ".xlsx", ".xlsm"}


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
    for candidate in (PORTABLE_POPPLER_BIN_DIR, POPPLER_BIN_DIR):
        exe = candidate / f"{name}.exe"
        if exe.exists():
            return str(exe)
    found = shutil.which(name)
    if found and not found.lower().endswith(".cmd"):
        return found
    return found


def hidden_process_kwargs() -> dict:
    """Флаги скрытого запуска фоновых процессов: никаких чёрных окон консоли."""
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


def run_poppler(args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        **hidden_process_kwargs(),
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


def word_to_pdf(path: Path) -> tuple[Path, bool]:
    if not path.exists():
        raise FileNotFoundError(f"Word-файл не найден: {path}")
    if not path.is_file() or not is_word_file(path):
        raise ValueError(f"Это не Word-файл: {path}")
    if not WORD_CONVERT_SCRIPT.exists():
        raise RuntimeError(f"Скрипт конвертации Word не найден: {WORD_CONVERT_SCRIPT}")

    key = file_cache_key(path, "word-pdf")
    target_dir = WORD_CACHE_DIR / key
    target_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = target_dir / f"{path.stem}.pdf"
    manifest_path = target_dir / "manifest.json"

    cached = False
    if pdf_path.exists() and pdf_path.stat().st_size > 0 and manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            cached = (
                manifest.get("sourcePath") == str(path)
                and manifest.get("cacheKey") == key
                and manifest.get("sourceMtimeNs") == path.stat().st_mtime_ns
                and manifest.get("sourceSize") == path.stat().st_size
            )
        except (OSError, json.JSONDecodeError):
            cached = False

    if cached:
        return pdf_path, True

    if pdf_path.exists():
        pdf_path.unlink()

    process = subprocess.run(
        [
            "powershell",
            "-STA",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(WORD_CONVERT_SCRIPT),
            "-InputPath",
            str(path),
            "-OutputPath",
            str(pdf_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=WORD_CONVERT_TIMEOUT_SECONDS,
        **hidden_process_kwargs(),
    )
    if process.returncode != 0:
        message = process.stderr.strip() or process.stdout.strip() or "Word не смог конвертировать документ в PDF"
        raise RuntimeError(message)
    if not pdf_path.exists() or pdf_path.stat().st_size <= 0:
        raise RuntimeError("Word не создал PDF для preview")

    manifest_path.write_text(
        json.dumps(
            {
                "sourcePath": str(path),
                "sourceName": path.name,
                "sourceMtimeNs": path.stat().st_mtime_ns,
                "sourceSize": path.stat().st_size,
                "cacheKey": key,
                "pdfPath": str(pdf_path),
                "convertedAt": datetime.now().isoformat(timespec="seconds"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return pdf_path, False


def render_word(path: Path, dpi: int = DEFAULT_PDF_DPI) -> dict:
    pdf_path, convert_cache_hit = word_to_pdf(path)
    document = render_pdf(pdf_path, dpi=dpi)
    document["sourcePath"] = str(path)
    document["sourceName"] = path.name
    document["sourceType"] = file_extension(path)
    document["convertedPdfPath"] = str(pdf_path)
    document["convertCacheHit"] = convert_cache_hit
    return document


def dwg_to_model_pdf(path: Path) -> tuple[Path, bool]:
    """Экспорт чертежа DWG в многостраничный векторный PDF через ZWCAD COM.

    Сохраняет парный PDF рядом с исходным DWG-файлом (при наличии прав записи)
    либо в резервный локальный кэш, если папка защищена от записи.
    """
    if not path.exists():
        raise FileNotFoundError(f"DWG-файл не найден: {path}")
    if not path.is_file() or path.suffix.casefold() != ".dwg":
        raise ValueError(f"Это не DWG-файл: {path}")

    # 1. Проверяем парный PDF рядом с исходником DWG
    paired_pdf = path.with_suffix(".pdf")
    if paired_pdf.exists() and paired_pdf.is_file() and paired_pdf.stat().st_size > 1024:
        try:
            if paired_pdf.stat().st_mtime_ns >= path.stat().st_mtime_ns:
                return paired_pdf, True
        except OSError:
            pass

    # 2. Проверяем резервный кэш
    key = file_cache_key(path, "dwg-smart-cad-v2")
    target_dir = DWG_CACHE_DIR / key
    target_dir.mkdir(parents=True, exist_ok=True)
    fallback_pdf = target_dir / f"{path.stem}.pdf"
    manifest_path = target_dir / "manifest.json"
    if fallback_pdf.exists() and fallback_pdf.stat().st_size > 1024 and manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if (
                manifest.get("sourcePath") == str(path)
                and manifest.get("cacheKey") == key
                and manifest.get("sourceMtimeNs") == path.stat().st_mtime_ns
                and manifest.get("sourceSize") == path.stat().st_size
            ):
                return fallback_pdf, True
        except (OSError, json.JSONDecodeError):
            pass

    script_to_run = DWG_SMART_RENDER_SCRIPT if DWG_SMART_RENDER_SCRIPT.exists() else DWG_RENDER_SCRIPT
    process = subprocess.run(
        [
            "powershell",
            "-STA",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_to_run),
            "-InputPath",
            str(path),
            "-OutputPath",
            str(paired_pdf),
            "-FallbackCachePath",
            str(fallback_pdf),
            "-PythonExe",
            str(sys.executable),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=DWG_RENDER_TIMEOUT_SECONDS,
        **hidden_process_kwargs(),
    )
    if process.returncode != 0:
        message = process.stderr.strip() or process.stdout.strip() or "ZWCAD не смог создать PDF для чертежа"
        raise RuntimeError(message)

    final_pdf = None
    if paired_pdf.exists() and paired_pdf.stat().st_size > 1024:
        final_pdf = paired_pdf
    elif fallback_pdf.exists() and fallback_pdf.stat().st_size > 1024:
        final_pdf = fallback_pdf
    else:
        for line in reversed((process.stdout or "").splitlines()):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    data = json.loads(line)
                    cand = Path(data.get("finalPath", ""))
                    if cand.exists() and cand.stat().st_size > 1024:
                        final_pdf = cand
                        break
                except Exception:
                    pass

    if not final_pdf or not final_pdf.exists() or final_pdf.stat().st_size <= 1024:
        raise RuntimeError("ZWCAD не создал PDF-файл для чертежа")

    if final_pdf == fallback_pdf:
        manifest_path.write_text(
            json.dumps(
                {
                    "sourcePath": str(path),
                    "sourceName": path.name,
                    "sourceMtimeNs": path.stat().st_mtime_ns,
                    "sourceSize": path.stat().st_size,
                    "cacheKey": key,
                    "pdfPath": str(fallback_pdf),
                    "mode": "smart-layouts-fallback-cache",
                    "renderedAt": datetime.now().isoformat(timespec="seconds"),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return final_pdf, False


def render_dwg_model(path: Path, dpi: int = DEFAULT_PDF_DPI) -> dict:
    pdf_path, convert_cache_hit = dwg_to_model_pdf(path)
    document = render_pdf(pdf_path, dpi=dpi, page_timeout_seconds=DWG_MODEL_PAGE_TIMEOUT_SECONDS)
    document["name"] = path.name
    document["sourcePath"] = str(path)
    document["sourceName"] = path.name
    document["sourceType"] = "DWG"
    document["convertedPdfPath"] = str(pdf_path)
    document["convertCacheHit"] = convert_cache_hit
    document["previewMode"] = "cad-smart-layouts"
    return document


def set_windows_clipboard(text: str) -> bool:
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.EmptyClipboard.argtypes = []
        user32.EmptyClipboard.restype = wintypes.BOOL
        user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        user32.SetClipboardData.restype = wintypes.HANDLE
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = wintypes.BOOL

        kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = wintypes.LPVOID
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalUnlock.restype = wintypes.BOOL

        GMEM_MOVEABLE = 0x0002
        CF_UNICODETEXT = 13

        normalized_text = os.path.normpath(text)

        if not user32.OpenClipboard(None):
            return False
        try:
            user32.EmptyClipboard()
            encoded = (normalized_text + "\0").encode("utf-16le")
            h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
            if not h_mem:
                return False
            p_mem = kernel32.GlobalLock(h_mem)
            if not p_mem:
                return False
            ctypes.memmove(p_mem, encoded, len(encoded))
            kernel32.GlobalUnlock(h_mem)
            return bool(user32.SetClipboardData(CF_UNICODETEXT, h_mem))
        finally:
            user32.CloseClipboard()
    except Exception:
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Set-Clipboard", "-Value", text],
                timeout=3,
                check=True
            )
            return True
        except Exception:
            return False


def launch_native_file(path: Path) -> str:
    """Показать файл или папку в Проводнике Windows без зависаний."""
    if not path.exists():
        raise FileNotFoundError(f"Файл или папка не найдены: {path}")

    if os.name != "nt":
        target = path if path.is_dir() else path.parent
        subprocess.Popen(["xdg-open", str(target)])
        return "xdg-open"

    resolved = os.path.normpath(str(path.resolve()))
    target_dir = resolved if path.is_dir() else os.path.dirname(resolved)

    try:
        import ctypes
        # Разрешаем новому окну Проводника выйти на передний план
        ctypes.windll.user32.AllowSetForegroundWindow(ctypes.c_uint32(0xFFFFFFFF))
    except Exception:
        pass

    try:
        if path.is_dir():
            cmd = f'explorer.exe "{resolved}"'
            subprocess.Popen(cmd)
            return "explorer-open-folder"
        else:
            cmd = f'explorer.exe /select,"{resolved}"'
            subprocess.Popen(cmd)
            return "explorer-select"
    except Exception:
        try:
            os.startfile(target_dir)
            return "explorer-open-folder-fallback"
        except Exception:
            subprocess.Popen(["cmd.exe", "/c", "start", "", target_dir], shell=True)
            return "explorer-open-cmd"

    suffix = path.suffix.casefold()

    # 1. DWG / DXF -> ZWCAD / AutoCAD
    if suffix in {".dwg", ".dxf"}:
        zwcad_candidates = [
            Path(r"C:\Program Files\ZWSOFT\ZWCAD 2025\ZWCAD.exe"),
            Path(r"C:\Program Files\ZWSOFT\ZWCAD 2024\ZWCAD.exe"),
            Path(r"C:\Program Files\ZWSOFT\ZWCAD 2025\ZwLauncher.exe"),
        ]
        for cand in zwcad_candidates:
            if cand.exists():
                subprocess.Popen([str(cand), str(path)], cwd=str(cand.parent))
                return f"zwcad-direct:{cand.name}"
        try:
            os.startfile(str(path))
            return "dwg-startfile"
        except Exception:
            subprocess.Popen(["cmd.exe", "/c", "start", "", str(path)])
            return "dwg-cmd-start"

    # 2. Excel / Spreadsheets -> Microsoft Excel
    if suffix in {".xlsx", ".xls", ".xlsm", ".xlsb", ".csv", ".ods"}:
        excel_candidates = [
            Path(r"C:\Program Files\Microsoft Office\Root\Office16\EXCEL.EXE"),
            Path(r"C:\Program Files (x86)\Microsoft Office\Root\Office16\EXCEL.EXE"),
            Path(r"C:\Program Files\Microsoft Office\Office16\EXCEL.EXE"),
            Path(r"C:\Program Files (x86)\Microsoft Office\Office16\EXCEL.EXE"),
            Path(r"C:\Program Files\Microsoft Office\Office15\EXCEL.EXE"),
        ]
        for cand in excel_candidates:
            if cand.exists():
                subprocess.Popen([str(cand), str(path)], cwd=str(cand.parent))
                return f"excel-direct:{cand.name}"
        try:
            os.startfile(str(path))
            return "excel-startfile"
        except Exception:
            subprocess.Popen(["cmd.exe", "/c", "start", "", str(path)])
            return "excel-cmd-start"

    # 3. Word / Documents -> Microsoft Word
    if suffix in {".docx", ".doc", ".docm", ".rtf", ".dotx", ".odt"}:
        word_candidates = [
            Path(r"C:\Program Files\Microsoft Office\Root\Office16\WINWORD.EXE"),
            Path(r"C:\Program Files (x86)\Microsoft Office\Root\Office16\WINWORD.EXE"),
            Path(r"C:\Program Files\Microsoft Office\Office16\WINWORD.EXE"),
            Path(r"C:\Program Files (x86)\Microsoft Office\Office16\WINWORD.EXE"),
            Path(r"C:\Program Files\Microsoft Office\Office15\WINWORD.EXE"),
        ]
        for cand in word_candidates:
            if cand.exists():
                subprocess.Popen([str(cand), str(path)], cwd=str(cand.parent))
                return f"word-direct:{cand.name}"
        try:
            os.startfile(str(path))
            return "word-startfile"
        except Exception:
            subprocess.Popen(["cmd.exe", "/c", "start", "", str(path)])
            return "word-cmd-start"

    # 4. PDF -> ONLYOFFICE Desktop Editors / Edge / Chrome
    if suffix == ".pdf":
        pdf_candidates = [
            Path(r"C:\Program Files\ONLYOFFICE\DesktopEditors\DesktopEditors.exe"),
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        ]
        for cand in pdf_candidates:
            if cand.exists():
                subprocess.Popen([str(cand), str(path)], cwd=str(cand.parent))
                return f"pdf-direct:{cand.name}"
        try:
            os.startfile(str(path))
            return "pdf-startfile"
        except Exception:
            subprocess.Popen(["cmd.exe", "/c", "start", "", str(path)])
            return "pdf-cmd-start"

    # 5. Images -> Modern Paint / Photo Viewer
    if suffix in {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif", ".ico", ".tif", ".tiff"}:
        paint_candidates = [
            Path.home() / "AppData" / "Local" / "Microsoft" / "WindowsApps" / "mspaint.exe",
            Path(r"C:\Windows\system32\mspaint.exe"),
        ]
        for cand in paint_candidates:
            if cand.exists():
                subprocess.Popen([str(cand), str(path)])
                return f"paint-direct:{cand.name}"
        try:
            os.startfile(str(path))
            return "image-startfile"
        except Exception:
            subprocess.Popen(["cmd.exe", "/c", "start", "", str(path)])
            return "image-cmd-start"

    # 6. Video / Audio -> VLC or default media player
    if suffix in {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".wma"}:
        vlc_candidates = [
            Path(r"C:\Program Files\VideoLAN\VLC\vlc.exe"),
            Path(r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe"),
        ]
        for cand in vlc_candidates:
            if cand.exists():
                subprocess.Popen([str(cand), str(path)], cwd=str(cand.parent))
                return f"vlc-direct:{cand.name}"
        try:
            os.startfile(str(path))
            return "media-startfile"
        except Exception:
            subprocess.Popen(["cmd.exe", "/c", "start", "", str(path)])
            return "media-cmd-start"

    # 7. Archives -> 7-Zip or WinRAR
    if suffix in {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"}:
        archive_candidates = [
            Path(r"C:\Program Files\7-Zip\7zFM.exe"),
            Path(r"C:\Program Files (x86)\WinRAR\WinRAR.exe"),
            Path(r"C:\Program Files\WinRAR\WinRAR.exe"),
        ]
        for cand in archive_candidates:
            if cand.exists():
                subprocess.Popen([str(cand), str(path)], cwd=str(cand.parent))
                return f"archive-direct:{cand.name}"
        try:
            os.startfile(str(path))
            return "archive-startfile"
        except Exception:
            subprocess.Popen(["cmd.exe", "/c", "start", "", str(path)])
            return "archive-cmd-start"

    # 8. Text / Config / Code files -> Notepad
    if suffix in {".txt", ".log", ".cfg", ".ini", ".conf", ".json", ".xml", ".yaml", ".yml", ".sql", ".bat", ".cmd", ".ps1", ".py", ".js", ".html", ".css"}:
        try:
            subprocess.Popen(["notepad.exe", str(path)])
            return "notepad-direct"
        except Exception:
            pass

    # 9. General fallback for all remaining file types
    try:
        os.startfile(str(path))
        return "os-startfile"
    except Exception:
        subprocess.Popen(["cmd.exe", "/c", "start", "", str(path)])
        return "cmd-start"


def open_dwg_for_review(path: Path) -> str:
    return launch_native_file(path)


def open_word_native(path: Path) -> str:
    return launch_native_file(path)


def open_excel_native(path: Path) -> str:
    return launch_native_file(path)


def open_pdf_native(path: Path) -> str:
    return launch_native_file(path)


def find_msedge() -> str | None:
    for program_files in ("C:/Program Files (x86)/Microsoft/Edge/Application", "C:/Program Files/Microsoft/Edge/Application"):
        candidate = Path(program_files) / "msedge.exe"
        if candidate.exists():
            return str(candidate)
    found = shutil.which("msedge")
    return found if found else None


NATIVE_OPEN_LOG_LOCK = threading.Lock()


def append_native_open_log(event: dict) -> None:
    """Write one UTF-8 diagnostic record for a native-open attempt.

    ThreadingHTTPServer serves each request on its own thread, so concurrent
    /api/open-file calls can interleave partial JSON lines.  A lock keeps each
    record as one atomic write.
    """
    logs_dir = RUNTIME_DIR / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, ensure_ascii=False) + "\n"
    with NATIVE_OPEN_LOG_LOCK:
        with (logs_dir / "native-open.jsonl").open("a", encoding="utf-8") as log:
            log.write(line)


IMPORT_LOG_LOCK = threading.Lock()


def append_import_log(event: dict) -> None:
    """Записать одну UTF-8 строку диагностики загрузки объекта в файл."""
    try:
        logs_dir = RUNTIME_DIR / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event, ensure_ascii=False) + "\n"
        with IMPORT_LOG_LOCK:
            with (logs_dir / "import.jsonl").open("a", encoding="utf-8") as log:
                log.write(line)
    except Exception:
        pass


def excel_html_cache_dir(path: Path) -> Path:
    """Return an immutable cache location for one exact workbook revision."""
    return EXCEL_CACHE_DIR / "html" / file_cache_key(path, "excel-html")


def excel_convert_xls_to_xlsx(path: Path) -> tuple[Path, bool]:
    """Convert a legacy .xls workbook to .xlsx via Excel COM, cached by source.

    openpyxl can only read the OpenXML formats, so legacy .xls books are
    converted once through the installed Excel and reused until the source
    file changes.  The converted copy is only a preview source: nothing is
    written next to the original workbook.
    """
    if path.suffix.casefold() not in {".xls"}:
        raise ValueError(f"Это не файл XLS: {path}")
    if not EXCEL_XLS_CONVERT_SCRIPT.exists():
        raise RuntimeError(f"Скрипт конвертации XLS не найден: {EXCEL_XLS_CONVERT_SCRIPT}")

    key = file_cache_key(path, "excel-xls-convert")
    target_dir = EXCEL_CACHE_DIR / "xlsx" / key
    target_dir.mkdir(parents=True, exist_ok=True)
    xlsx_path = target_dir / f"{path.stem}.xlsx"
    manifest_path = target_dir / "manifest.json"

    cached = False
    if xlsx_path.exists() and xlsx_path.stat().st_size > 0 and manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            cached = (
                manifest.get("sourcePath") == str(path)
                and manifest.get("sourceMtimeNs") == path.stat().st_mtime_ns
                and manifest.get("sourceSize") == path.stat().st_size
            )
        except (OSError, json.JSONDecodeError):
            cached = False

    if cached:
        return xlsx_path, True

    if xlsx_path.exists():
        xlsx_path.unlink()

    process = subprocess.run(
        [
            "powershell",
            "-STA",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(EXCEL_XLS_CONVERT_SCRIPT),
            "-InputPath",
            str(path),
            "-OutputPath",
            str(xlsx_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=EXCEL_CONVERT_TIMEOUT_SECONDS,
        **hidden_process_kwargs(),
    )
    if process.returncode != 0:
        message = process.stderr.strip() or process.stdout.strip() or "Excel не смог сконвертировать книгу XLS"
        raise RuntimeError(message)
    if not xlsx_path.exists() or xlsx_path.stat().st_size <= 0:
        raise RuntimeError("Excel не создал XLSX для preview")

    manifest_path.write_text(
        json.dumps(
            {
                "sourcePath": str(path),
                "sourceName": path.name,
                "sourceMtimeNs": path.stat().st_mtime_ns,
                "sourceSize": path.stat().st_size,
                "cacheKey": key,
                "xlsxPath": str(xlsx_path),
                "convertedAt": datetime.now().isoformat(timespec="seconds"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return xlsx_path, False


def excel_preview_source(path: Path) -> Path:
    """Return an .xlsx/.xlsm path openpyxl can read, converting legacy .xls.

    HTML rendering and sheet extraction both need the OpenXML workbook.
    .xlsx/.xlsm files are used as-is; .xls is converted through Excel COM.
    """
    if path.name.startswith("~$") or path.name.startswith(".~"):
        raise ValueError(f"Временный файл блокировки Office: {path.name}")
    if path.suffix.casefold() in {".xlsx", ".xlsm"}:
        return path
    if path.suffix.casefold() == ".xls":
        xlsx_path, _ = excel_convert_xls_to_xlsx(path)
        return xlsx_path
    raise ValueError("HTML-просмотр пока поддерживает XLSX/XLSM. Откройте XLS в Excel.")


def excel_cell_color(color: object) -> str | None:
    value = getattr(color, "rgb", None)
    value = str(value) if value is not None else ""
    if not value or len(value) < 6 or (len(value) == 8 and value[:2] == "00"):
        return None
    return f"#{value[-6:]}"


def excel_sheet_html(path: Path, sheet_index: int) -> tuple[str, dict]:
    """Create a read-only HTML sheet with authored geometry.

    The Launcher is a fast navigator, not a replacement for Excel.  The limit is
    intentional: long operational registers are opened in the native program.
    """
    if openpyxl is None:
        raise RuntimeError("Для HTML-просмотра Excel нужен пакет openpyxl")

    preview_source = excel_preview_source(path)

    styles_book = openpyxl.load_workbook(preview_source, read_only=False, data_only=False)
    values_book = openpyxl.load_workbook(preview_source, read_only=False, data_only=True)
    try:
        sheet = styles_book.worksheets[sheet_index]
        values = values_book.worksheets[sheet_index]
        # Some valid workbooks (notably registers exported by third-party
        # systems) have no stored dimension in one of the loaded views.
        # openpyxl then returns None, which must mean an empty 1x1 sheet here,
        # not an unhandled server exception and a blank Launcher screen.
        sheet_max_row = int(sheet.max_row or 1)
        values_max_row = int(values.max_row or 1)
        sheet_max_column = int(sheet.max_column or 1)
        values_max_column = int(values.max_column or 1)
        max_column = min(max(sheet_max_column, values_max_column), MAX_XLSX_COLS)
        columns = [
            column
            for column in range(1, max_column + 1)
            if not sheet.column_dimensions[openpyxl.utils.get_column_letter(column)].hidden
        ]
        column_pixels = {}
        for column in columns:
            width = sheet.column_dimensions[openpyxl.utils.get_column_letter(column)].width or 8.43
            column_pixels[column] = max(4, min(720, round(width * 7 + 5)))

        merged_start = {}
        merged_skip = set()
        for area in sheet.merged_cells.ranges:
            shown_columns = [column for column in columns if area.min_col <= column <= area.max_col]
            if not shown_columns:
                continue
            start = (area.min_row, shown_columns[0])
            merged_start[start] = (len(shown_columns), area.max_row - area.min_row + 1)
            for row in range(area.min_row, area.max_row + 1):
                for column in shown_columns:
                    if (row, column) != start:
                        merged_skip.add((row, column))

        first_value_row = 0
        last_value_row = 0
        for row in range(1, min(values_max_row, MAX_XLSX_ROWS) + 1):
            if any(values.cell(row, column).value is not None for column in columns):
                if not first_value_row:
                    first_value_row = row
                last_value_row = row
        last_merge_row = max((area.max_row for area in sheet.merged_cells.ranges), default=0)
        rendered_rows = min(max(last_value_row, last_merge_row), MAX_XLSX_ROWS)
        was_limited = max(sheet_max_row, values_max_row) > MAX_XLSX_ROWS

        first_rendered_row = first_value_row or 1
        rows = []
        for row in range(first_rendered_row, rendered_rows + 1):
            if sheet.row_dimensions[row].hidden:
                continue
            cells = []
            for column in columns:
                if (row, column) in merged_skip:
                    continue
                cell = sheet.cell(row, column)
                raw_value = values.cell(row, column).value
                value = "" if raw_value is None else str(raw_value)
                css = []
                # A single neutral grid is supplied by the page stylesheet.
                # Re-emitting four border declarations for every cell made a
                # 2,000-row workbook produce 8–9 MB of HTML and a long white
                # screen before Chrome could paint it.  This is a navigator,
                # so fast first paint has priority over reproducing every
                # individual spreadsheet border colour.
                if cell.font.bold:
                    css.append("font-weight:500")
                if cell.font.italic:
                    css.append("font-style:italic")
                # Defaults are already declared once in the HTML stylesheet.
                # Repeating Calibri 11px on every one of 52,000 cells turns a
                # normal workbook into a multi-megabyte page that opens white.
                if cell.font.sz and round(cell.font.sz) != 11:
                    css.append(f"font-size:{max(6, min(32, cell.font.sz))}px")
                if cell.font.name and cell.font.name.casefold() not in {"calibri", "arial", "segoe ui"}:
                    css.append(f"font-family:{html.escape(cell.font.name, quote=True)}")
                font_color = excel_cell_color(cell.font.color)
                if font_color:
                    css.append(f"color:{font_color}")
                fill = excel_cell_color(cell.fill.fgColor)
                if cell.fill.fill_type == "solid" and fill:
                    css.append(f"background:{fill}")
                if cell.alignment.horizontal in {"left", "center", "right"}:
                    css.append(f"text-align:{cell.alignment.horizontal}")
                if cell.alignment.vertical in {"top", "center", "bottom"}:
                    css.append(f"vertical-align:{cell.alignment.vertical}")
                if cell.alignment.wrap_text is False:
                    css.append("white-space:pre;overflow:hidden")
                colspan, rowspan = merged_start.get((row, column), (1, 1))
                span = (f' colspan="{colspan}"' if colspan > 1 else "") + (f' rowspan="{rowspan}"' if rowspan > 1 else "")
                cells.append(f'<td{span} style="{";".join(css)}">{html.escape(value)}</td>')
            authored_height = sheet.row_dimensions[row].height
            row_style = f' style="height:{max(1, round(authored_height * 1.33))}px"' if authored_height else ""
            rows.append(f"<tr{row_style}><th>{row}</th>{''.join(cells)}</tr>")

        cols = '<col class="row-number">' + "".join(
            f'<col style="width:{column_pixels[column]}px">' for column in columns
        )
        table_width = 38 + sum(column_pixels.values())
        notice = (
            f"Показаны первые {MAX_XLSX_ROWS:,} строк. Полный рабочий файл откройте в Excel."
            if was_limited else "Просмотр без редактирования"
        )
        rendered = {
            "name": sheet.title,
            "rows": max(0, rendered_rows - first_rendered_row + 1),
            "firstRow": first_rendered_row,
            "columns": len(columns),
            "limited": was_limited,
        }
        page = f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>{html.escape(sheet.title)}</title>
<style>
html,body{{margin:0;min-width:max-content;background:#fff;color:#20262d;font:11px "Segoe UI",Arial,sans-serif;overflow:auto}}
#sheet-canvas{{position:relative;transform-origin:0 0}}#sheet{{position:absolute;left:0;top:0;transform-origin:50% 50%}}
.notice{{position:sticky;top:0;z-index:2;padding:6px 10px;border-bottom:1px solid #d3dde4;background:#f7fafc;color:#607080;font-size:11px}}
table{{border-collapse:collapse;table-layout:fixed;width:{table_width}px}}col.row-number{{width:38px}}
th,td{{box-sizing:border-box;border:1px solid #cbd5dc;padding:2px 4px;vertical-align:top;white-space:pre-wrap;overflow-wrap:break-word}}
th{{position:sticky;left:0;z-index:1;background:#f1f5f7;color:#657687;font:10px "Segoe UI",Arial,sans-serif;text-align:right}}td{{overflow:hidden}}
</style></head><body><div id="sheet-canvas"><div id="sheet"><table><colgroup>{cols}</colgroup><tbody>{''.join(rows)}</tbody></table></div></div>
<script>const canvas=document.getElementById('sheet-canvas'),sheet=document.getElementById('sheet');let width=0,height=0,padding=0,scale=1,rotation=0,hand=true,dragging=false,startX=0,startY=0,startLeft=0,startTop=0;function dimensions(){{return Math.abs(rotation%180)===90?{{width:height,height:width}}:{{width,height}}}}function zoom(value){{if(!width){{width=sheet.offsetWidth;height=sheet.offsetHeight}}scale=Math.max(.35,Math.min(3,value));padding=Math.max(innerWidth,innerHeight);const size=dimensions();canvas.style.width=(size.width*scale+padding*2)+'px';canvas.style.height=(size.height*scale+padding*2)+'px';sheet.style.transform='translate('+(padding+size.width*scale/2-width/2)+'px,'+(padding+size.height*scale/2-height/2)+'px) rotate('+rotation+'deg) scale('+scale+')'}}function fit(){{if(!width)zoom(1);const size=dimensions(),value=Math.min(1,(innerWidth-48)/size.width,(innerHeight-48)/size.height);zoom(value);requestAnimationFrame(()=>{{scrollTo(padding,padding);parent.postMessage({{type:'launcher-sheet-fitted',value:scale}},'*')}})}}function cursor(){{document.body.style.cursor=hand?(dragging?'grabbing':'grab'):'default'}}addEventListener('load',()=>{{zoom(1);cursor();requestAnimationFrame(()=>scrollTo(padding,padding))}});addEventListener('wheel',event=>{{if(!event.ctrlKey)return;event.preventDefault();zoom(scale*(event.deltaY<0?1.12:.89))}},{{passive:false}});addEventListener('pointerdown',event=>{{if(!hand||event.button!==0)return;dragging=true;startX=event.clientX;startY=event.clientY;startLeft=scrollX;startTop=scrollY;document.body.setPointerCapture?.(event.pointerId);cursor();event.preventDefault()}});addEventListener('pointermove',event=>{{if(!dragging)return;scrollTo(startLeft-(event.clientX-startX),startTop-(event.clientY-startY))}});addEventListener('pointerup',event=>{{if(!dragging)return;dragging=false;document.body.releasePointerCapture?.(event.pointerId);cursor()}});addEventListener('pointercancel',()=>{{dragging=false;cursor()}});addEventListener('message',event=>{{if(!event.data)return;if(event.data.type==='launcher-sheet-zoom')zoom(event.data.value);if(event.data.type==='launcher-sheet-fit')fit();if(event.data.type==='launcher-sheet-rotate'){{rotation=((Number(event.data.value)||0)%360+360)%360;zoom(scale)}}if(event.data.type==='launcher-sheet-hand'){{hand=Boolean(event.data.value);dragging=false;cursor()}}}});</script></body></html>'''
        return page, rendered
    finally:
        styles_book.close()
        values_book.close()


def excel_sheet_preview(path: Path, sheet_index: int) -> dict:
    """Build one sheet on demand; opening a book must not wait for every tab."""
    cache_dir = excel_html_cache_dir(path)
    cache_dir.mkdir(parents=True, exist_ok=True)
    # A new cache version makes existing pages harmless without deleting a
    # user's cache, including the viewer controls embedded in this HTML.
    output = cache_dir / f"sheet-{sheet_index + 1}-v9.html"
    metadata_path = cache_dir / f"sheet-{sheet_index + 1}-v9.json"
    metadata = None
    if output.exists() and metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            metadata = None
    if metadata is None:
        page, metadata = excel_sheet_html(path, sheet_index)
        output.write_text(page, encoding="utf-8")
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    return {
        "index": sheet_index,
        "url": f"/cache/excel/html/{cache_dir.name}/{output.name}",
        **metadata,
    }


def excel_thumbnail_preview(path: Path) -> str:
    """Build a visual card from the exact same HTML sheet as the large view.

    A workbook must have one visual source of truth.  The former thumbnail
    constructed a second, simplified table with its own font and row rules;
    it could therefore disagree with the readable sheet.  The card is now a
    scaled viewport of the cached HTML sheet used by the full viewer.
    """
    if openpyxl is None:
        raise RuntimeError("Для HTML-просмотра Excel нужен пакет openpyxl")
    # The rail already places this page in a scaled, clipped iframe.  Returning
    # the sheet directly means its geometry, fonts and initial position are
    # exactly the same in the card and in the large viewer.
    return excel_sheet_preview(path, 0)["url"]


def excel_workbook_preview(path: Path) -> dict:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Excel-файл не найден: {path}")
    if path.name.startswith("~$") or path.name.startswith(".~"):
        raise ValueError(f"Временный файл блокировки Office: {path.name}")
    if not is_excel_file(path):
        raise ValueError(f"Это не Excel-файл: {path}")
    if openpyxl is None:
        raise RuntimeError("Для HTML-просмотра Excel нужен пакет openpyxl")

    preview_source = excel_preview_source(path)
    book = openpyxl.load_workbook(preview_source, read_only=True, data_only=False)
    try:
        sheet_names = book.sheetnames
    finally:
        book.close()

    sheets = [{"index": index, "name": name} for index, name in enumerate(sheet_names)]
    return {
        "name": path.name,
        "path": str(path),
        "sheets": sheets,
        "maxRows": MAX_XLSX_ROWS,
        "cacheKey": excel_html_cache_dir(path).name,
        "thumbnailUrl": excel_thumbnail_preview(path),
    }


def excel_to_pdf(path: Path) -> tuple[Path, bool]:
    if not path.exists():
        raise FileNotFoundError(f"Excel-файл не найден: {path}")
    if not path.is_file() or not is_excel_file(path):
        raise ValueError(f"Это не Excel-файл: {path}")
    if not EXCEL_CONVERT_SCRIPT.exists():
        raise RuntimeError(f"Скрипт конвертации Excel не найден: {EXCEL_CONVERT_SCRIPT}")

    key = file_cache_key(path, "excel-pdf")
    target_dir = EXCEL_CACHE_DIR / key
    target_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = target_dir / f"{path.stem}.pdf"
    manifest_path = target_dir / "manifest.json"

    cached = False
    if pdf_path.exists() and pdf_path.stat().st_size > 0 and manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            cached = (
                manifest.get("sourcePath") == str(path)
                and manifest.get("cacheKey") == key
                and manifest.get("sourceMtimeNs") == path.stat().st_mtime_ns
                and manifest.get("sourceSize") == path.stat().st_size
            )
        except (OSError, json.JSONDecodeError):
            cached = False

    if cached:
        return pdf_path, True

    if pdf_path.exists():
        pdf_path.unlink()

    process = subprocess.run(
        [
            "powershell",
            "-STA",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(EXCEL_CONVERT_SCRIPT),
            "-InputPath",
            str(path),
            "-OutputPath",
            str(pdf_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=EXCEL_CONVERT_TIMEOUT_SECONDS,
        **hidden_process_kwargs(),
    )
    if process.returncode != 0:
        message = process.stderr.strip() or process.stdout.strip() or "Excel не смог экспортировать книгу в PDF"
        raise RuntimeError(message)
    if not pdf_path.exists() or pdf_path.stat().st_size <= 0:
        raise RuntimeError("Excel не создал PDF для preview")

    manifest_path.write_text(
        json.dumps(
            {
                "sourcePath": str(path),
                "sourceName": path.name,
                "sourceMtimeNs": path.stat().st_mtime_ns,
                "sourceSize": path.stat().st_size,
                "cacheKey": key,
                "pdfPath": str(pdf_path),
                "convertedAt": datetime.now().isoformat(timespec="seconds"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return pdf_path, False


def render_excel(path: Path, dpi: int = DEFAULT_PDF_DPI) -> dict:
    pdf_path, convert_cache_hit = excel_to_pdf(path)
    document = render_pdf(pdf_path, dpi=dpi)
    document["sourcePath"] = str(path)
    document["sourceName"] = path.name
    document["sourceType"] = file_extension(path)
    document["convertedPdfPath"] = str(pdf_path)
    document["convertCacheHit"] = convert_cache_hit
    return document


def render_pdf(path: Path, dpi: int = DEFAULT_PDF_DPI, page_timeout_seconds: int = PDF_PAGE_TIMEOUT_SECONDS) -> dict:
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
        cached_total = cached_manifest.get("pages", len(cached_items)) or 0
        if cached_total and len(cached_items) >= cached_total:
            return {
                "name": path.name,
                "path": str(path),
                "dpi": dpi,
                "pages": cached_total,
                "renderedPages": len(cached_items),
                "cacheKey": key,
                "cacheHit": True,
                "cacheHitPages": len(cached_items),
                "newRenderedPages": 0,
                "errors": cached_errors,
                "items": cached_items,
            }
        # Недоделанный кэш (обрезка по лимиту): не отдаём partial навсегда,
        # а дорисовываем недостающие страницы ниже — готовые PNG reused.

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
                        timeout=page_timeout_seconds,
                )
                candidate = target_dir / f"page-{page}.png"
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "pdftoppm не смог отрендерить страницу")
                if not candidate.exists() or candidate.stat().st_size <= 0:
                    raise RuntimeError("pdftoppm не создал PNG страницы")
                rendered_count += 1
            except subprocess.TimeoutExpired:
                errors.append({"page": page, "error": f"Таймаут рендера страницы {page}: {page_timeout_seconds} сек."})
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


def render_pdf_page(path: Path, page: int, dpi: int = DEFAULT_PDF_DPI, page_timeout_seconds: int = PDF_PAGE_TIMEOUT_SECONDS) -> dict:
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
                timeout=page_timeout_seconds,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(f"Таймаут рендера страницы {page}: {page_timeout_seconds} сек.") from error
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
                    "wordPreview": True,
                    "excelPreview": True,
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

        if parsed.path == "/api/file/raw":
            try:
                params = parse_qs(parsed.query)
                raw_path = params.get("path", [""])[0].strip()
                if not raw_path:
                    self.send_error(HTTPStatus.BAD_REQUEST, "Missing path")
                    return
                target = Path(raw_path).expanduser().resolve()
                if not target.exists() or not target.is_file():
                    self.send_error(HTTPStatus.NOT_FOUND, "File not found")
                    return
                content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
                body = target.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as error:
                self.send_error(HTTPStatus.BAD_REQUEST, str(error))
            return

        if parsed.path == "/api/browse":
            try:
                params = parse_qs(parsed.query)
                target_path = params.get("path", [""])[0].strip()
                result = browse_filesystem(target_path)
                self.send_json(HTTPStatus.OK, result)
            except Exception as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
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
            raw_path = ""
            try:
                body = self.read_json()
                raw_path = str(body.get("path", ""))
                manifest = scan_object(raw_path)
                self.send_json(HTTPStatus.OK, manifest)
            except (ValueError, FileNotFoundError, NotADirectoryError, OSError, json.JSONDecodeError) as error:
                append_import_log(
                    {
                        "at": datetime.now().isoformat(timespec="seconds"),
                        "status": "error",
                        "path": raw_path,
                        "error": str(error),
                    }
                )
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            except Exception as error:
                append_import_log(
                    {
                        "at": datetime.now().isoformat(timespec="seconds"),
                        "status": "unexpected-error",
                        "path": raw_path,
                        "error": "%s: %s" % (type(error).__name__, error),
                        "traceback": traceback.format_exc(limit=12),
                    }
                )
                self.send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": "Загрузка не удалась (%s). Подробности записаны в runtime/logs/import.jsonl." % type(error).__name__},
                )
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

        if parsed.path == "/api/objects/diff":
            try:
                body = self.read_json()
                object_id = str(body.get("id", "")).strip()
                manifest = load_manifest(object_id)
                if not manifest:
                    raise ValueError("Объект не найден")
                root = Path(manifest.get("rootPath", ""))
                if not root.exists():
                    raise FileNotFoundError(f"Папка объекта не найдена: {root}")
                tree, extension_counts, folder_count, file_count = build_tree(root)
                last_diff = diff_trees(manifest.get("tree"), tree)
                self.send_json(
                    HTTPStatus.OK,
                    {
                        "id": object_id,
                        "scannedAt": datetime.now().isoformat(timespec="seconds"),
                        "statistics": {
                            "folders": folder_count,
                            "files": file_count,
                            "extensions": extension_counts,
                        },
                        "lastDiff": last_diff,
                    },
                )
            except (ValueError, FileNotFoundError, OSError, json.JSONDecodeError) as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return

        if parsed.path == "/api/open-explorer":
            try:
                body = self.read_json()
                raw_path = str(body.get("path", "")).strip()
                if not raw_path:
                    raw_path = str(REPO_ROOT)
                target = Path(raw_path.strip('"')).resolve()
                if target.exists():
                    mode = launch_native_file(target)
                    self.send_json(HTTPStatus.OK, {"ok": True, "path": str(target), "mode": mode})
                else:
                    self.send_json(HTTPStatus.NOT_FOUND, {"error": f"Путь не найден: {target}"})
            except Exception as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return

        if parsed.path == "/api/choose-folder":
            try:
                choose_script = REPO_ROOT / "scripts" / "choose_folder.py"
                choose_env = dict(os.environ)
                choose_env["PYTHONUTF8"] = "1"
                choose_env["PYTHONIOENCODING"] = "utf-8"
                proc = subprocess.run(
                    [sys.executable, str(choose_script)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="strict",
                    timeout=120,
                    env=choose_env,
                )
                raw = proc.stdout.strip()
                files = []
                selected = ""
                if raw:
                    try:
                        parsed_json = json.loads(raw)
                        if isinstance(parsed_json, list) and parsed_json:
                            files = parsed_json
                            first_file = Path(files[0])
                            selected = str(first_file.parent if first_file.is_file() else first_file.resolve())
                        elif isinstance(parsed_json, str) and parsed_json.strip():
                            p = Path(parsed_json.strip())
                            selected = str(p.resolve()) if p.exists() else parsed_json.strip()
                    except json.JSONDecodeError:
                        first_line = raw.splitlines()[0].strip()
                        p = Path(first_line)
                        selected = str(p.resolve()) if p.exists() else first_line
                self.send_json(HTTPStatus.OK, {"path": selected, "files": files})
            except subprocess.TimeoutExpired:
                self.send_json(
                    HTTPStatus.OK,
                    {
                        "path": "",
                        "files": [],
                        "timedOut": True,
                        "error": "Системный диалог выбора папки Windows не ответил за 120 секунд. Попробуйте ещё раз или укажите путь вручную.",
                    },
                )
            except Exception as error:
                self.send_json(HTTPStatus.OK, {"path": "", "files": [], "error": f"Системный диалог выбора папки недоступен: {error}"})
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

        if parsed.path == "/api/word/render":
            try:
                body = self.read_json()
                raw_files = body.get("files", [])
                dpi = int(body.get("dpi") or DEFAULT_PDF_DPI)
                if dpi < 72 or dpi > 600:
                    raise ValueError("DPI должен быть в диапазоне 72-600")
                if not isinstance(raw_files, list) or not raw_files:
                    raise ValueError("Не выбраны Word-файлы для отображения")
                if len(raw_files) > 10:
                    raise ValueError("За один раз пока можно отрендерить не больше 10 Word-файлов")
                documents = [render_word(Path(str(file_path)), dpi=dpi) for file_path in raw_files]
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

        if parsed.path == "/api/word/page":
            try:
                body = self.read_json()
                raw_file = str(body.get("file", "")).strip()
                page = int(body.get("page") or 1)
                dpi = int(body.get("dpi") or DEFAULT_PDF_DPI)
                if dpi < 72 or dpi > 600:
                    raise ValueError("DPI должен быть в диапазоне 72-600")
                if not raw_file:
                    raise ValueError("Не выбран Word-файл для отображения")
                pdf_path, convert_cache_hit = word_to_pdf(Path(raw_file))
                payload = render_pdf_page(pdf_path, page=page, dpi=dpi)
                payload["sourcePath"] = raw_file
                payload["sourceType"] = file_extension(Path(raw_file))
                payload["convertedPdfPath"] = str(pdf_path)
                payload["convertCacheHit"] = convert_cache_hit
                self.send_json(HTTPStatus.OK, payload)
            except (ValueError, FileNotFoundError, RuntimeError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return

        if parsed.path == "/api/dwg/model-render":
            try:
                body = self.read_json()
                raw_files = body.get("files", [])
                dpi = int(body.get("dpi") or DEFAULT_PDF_DPI)
                if dpi < 72 or dpi > 600:
                    raise ValueError("DPI должен быть в диапазоне 72-600")
                if not isinstance(raw_files, list) or not raw_files:
                    raise ValueError("Не выбраны DWG-файлы для отображения")
                if len(raw_files) > 1:
                    raise ValueError("Model Space preview пока создаётся по одному DWG-файлу")
                documents = [render_dwg_model(Path(str(file_path)), dpi=dpi) for file_path in raw_files]
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

        if parsed.path == "/api/dwg/model-page":
            try:
                body = self.read_json()
                raw_file = str(body.get("file", "")).strip()
                page = int(body.get("page") or 1)
                dpi = int(body.get("dpi") or DEFAULT_PDF_DPI)
                if dpi < 72 or dpi > 600:
                    raise ValueError("DPI должен быть в диапазоне 72-600")
                if not raw_file:
                    raise ValueError("Не выбран DWG-файл для отображения")
                pdf_path, convert_cache_hit = dwg_to_model_pdf(Path(raw_file))
                payload = render_pdf_page(pdf_path, page=page, dpi=dpi, page_timeout_seconds=DWG_MODEL_PAGE_TIMEOUT_SECONDS)
                payload["sourcePath"] = raw_file
                payload["sourceType"] = "DWG"
                payload["convertedPdfPath"] = str(pdf_path)
                payload["convertCacheHit"] = convert_cache_hit
                self.send_json(HTTPStatus.OK, payload)
            except (ValueError, FileNotFoundError, RuntimeError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return

        if parsed.path == "/api/excel/workbook":
            try:
                body = self.read_json()
                raw_file = str(body.get("file", "")).strip()
                if not raw_file:
                    raise ValueError("Не выбран Excel-файл для отображения")
                self.send_json(HTTPStatus.OK, excel_workbook_preview(Path(raw_file)))
            except Exception as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return

        if parsed.path == "/api/excel/sheet":
            try:
                body = self.read_json()
                raw_file = str(body.get("file", "")).strip()
                sheet_index = int(body.get("sheetIndex", 0))
                sheet = excel_sheet_preview(Path(raw_file), sheet_index)
                self.send_json(HTTPStatus.OK, sheet)
            except Exception as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return

        if parsed.path == "/api/excel/render":
            try:
                body = self.read_json()
                raw_files = body.get("files", [])
                dpi = int(body.get("dpi") or DEFAULT_PDF_DPI)
                if dpi < 72 or dpi > 600:
                    raise ValueError("DPI должен быть в диапазоне 72-600")
                if not isinstance(raw_files, list) or not raw_files:
                    raise ValueError("Не выбраны Excel-файлы для отображения")
                if len(raw_files) > 10:
                    raise ValueError("За один раз пока можно отрендерить не больше 10 Excel-файлов")
                documents = [render_excel(Path(str(file_path)), dpi=dpi) for file_path in raw_files]
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
            except Exception as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return

        if parsed.path == "/api/excel/page":
            try:
                body = self.read_json()
                raw_file = str(body.get("file", "")).strip()
                page = int(body.get("page") or 1)
                dpi = int(body.get("dpi") or DEFAULT_PDF_DPI)
                if dpi < 72 or dpi > 600:
                    raise ValueError("DPI должен быть в диапазоне 72-600")
                if not raw_file:
                    raise ValueError("Не выбран Excel-файл для отображения")
                pdf_path, convert_cache_hit = excel_to_pdf(Path(raw_file))
                payload = render_pdf_page(pdf_path, page=page, dpi=dpi)
                payload["sourcePath"] = raw_file
                payload["sourceType"] = file_extension(Path(raw_file))
                payload["convertedPdfPath"] = str(pdf_path)
                payload["convertCacheHit"] = convert_cache_hit
                self.send_json(HTTPStatus.OK, payload)
            except Exception as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return

        if parsed.path == "/api/open-file":
            started = time.perf_counter()
            raw_file = ""
            target: Path | None = None
            try:
                body = self.read_json()
                raw_file = str(body.get("path", "")).strip()
                if not raw_file:
                    raise ValueError("Не выбран файл для открытия")
                target = Path(raw_file).expanduser()
                if not target.exists():
                    raise FileNotFoundError(f"Файл не найден: {target}")
                opened_path = str(target)
                suffix = target.suffix.casefold() if target.is_file() else ""
                # Google Drive shortcuts (.gsheet / .gdoc / .gslides) are virtual
                # reparse points, not real Office documents.  Launching them
                # through a local EXE is unpredictable, so give a clear hint.
                if suffix in {".gsheet", ".gdoc", ".gslides"}:
                    raise ValueError("Это облачный документ Google. Откройте его через браузер (Google Docs / Sheets).")
                mode = launch_native_file(target)
                append_native_open_log(
                    {
                        "at": datetime.now().isoformat(timespec="seconds"),
                        "status": "requested",
                        "extension": suffix,
                        "sourcePath": str(target),
                        "openedPath": opened_path,
                        "mode": mode,
                        "elapsedMs": round((time.perf_counter() - started) * 1000),
                    }
                )
                self.send_json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "path": str(target),
                        "openedPath": opened_path,
                        "mode": mode,
                        "longPathWarning": (
                            "Путь длиннее 240 символов — Windows может не открыть файл."
                            if len(opened_path) > 240
                            else None
                        ),
                    },
                )
            except Exception as error:
                append_native_open_log(
                    {
                        "at": datetime.now().isoformat(timespec="seconds"),
                        "status": "error",
                        "extension": target.suffix.casefold() if target else Path(raw_file).suffix.casefold(),
                        "sourcePath": str(target) if target else raw_file,
                        "error": str(error),
                        "elapsedMs": round((time.perf_counter() - started) * 1000),
                    }
                )
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return

        if parsed.path == "/api/clipboard":
            try:
                body = self.read_json()
                raw_text = str(body.get("text", "")).strip()
                if not raw_text:
                    raise ValueError("Текст для копирования не передан")
                ok = set_windows_clipboard(raw_text)
                if not ok:
                    raise RuntimeError("Не удалось записать текст в буфер обмена Windows")
                self.send_json(HTTPStatus.OK, {"ok": True, "text": raw_text})
            except Exception as error:
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
        # HTML/JS/CSS must never be served stale: a cached app.js silently
        # reverts the native-open logic to the broken WPS associations.
        # no-store (not no-cache) also wins without a manual ?v= bump.
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
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
    try:
        print(f"F-Engineering Launcher v3: http://{args.host}:{args.port}/", flush=True)
    except (ValueError, OSError, AttributeError):
        pass
    server.serve_forever()


if __name__ == "__main__":
    main()
