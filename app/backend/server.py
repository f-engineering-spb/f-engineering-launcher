from __future__ import annotations

import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO_ROOT / "app" / "frontend"
RUNTIME_DIR = REPO_ROOT / "runtime"
VERSION = "0.1.0-v3-shell"


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

        self.serve_static(parsed.path)

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
    (RUNTIME_DIR / "manifests").mkdir(exist_ok=True)
    (RUNTIME_DIR / "logs").mkdir(exist_ok=True)

    server = ThreadingHTTPServer((args.host, args.port), LauncherHandler)
    print(f"F-Engineering Launcher v3: http://{args.host}:{args.port}/", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
