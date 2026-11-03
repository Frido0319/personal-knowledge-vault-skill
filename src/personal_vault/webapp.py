from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

from .web_actions import ActionError, WebActionService


STATIC_ROOT = Path(__file__).parent / "web" / "static"
MAX_BODY = 65_536


class PersonalVaultServer(ThreadingHTTPServer):
    service: WebActionService
    csrf_token: str
    daemon_threads = True


class PersonalVaultHandler(BaseHTTPRequestHandler):
    server_version = "PersonalVault/0.1"

    @property
    def app(self) -> PersonalVaultServer:
        return cast(PersonalVaultServer, self.server)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _valid_host(self) -> bool:
        value = self.headers.get("Host", "")
        if value.startswith("["):
            hostname = value[1:].split("]", 1)[0]
        else:
            hostname = value.split(":", 1)[0]
        return hostname.casefold() in {"127.0.0.1", "localhost", "::1"}

    def _headers(self, content_type: str, length: int, *, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        )
        self.end_headers()

    def _send_bytes(self, content: bytes, content_type: str, *, status: int = 200) -> None:
        self._headers(content_type, len(content), status=status)
        self.wfile.write(content)

    def _send_json(self, payload: Any, *, status: int = 200) -> None:
        self._send_bytes(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"),
            "application/json; charset=utf-8",
            status=status,
        )

    def _error(self, status: int, code: str) -> None:
        self._send_json({"error": code}, status=status)

    def _static(self, filename: str, content_type: str) -> None:
        try:
            content = (STATIC_ROOT / filename).read_bytes()
        except OSError:
            self._error(404, "NOT_FOUND")
            return
        self._send_bytes(content, content_type)

    def do_GET(self) -> None:
        if not self._valid_host():
            self._error(403, "UNTRUSTED_HOST")
            return
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._static("index.html", "text/html; charset=utf-8")
        elif parsed.path == "/app.css":
            self._static("app.css", "text/css; charset=utf-8")
        elif parsed.path == "/app.js":
            self._static("app.js", "text/javascript; charset=utf-8")
        elif parsed.path == "/api/status":
            payload = self.app.service.status()
            payload["_csrf"] = self.app.csrf_token
            self._send_json(payload)
        elif parsed.path == "/api/sources":
            self._send_json(self.app.service.sources())
        elif parsed.path == "/api/proposals":
            self._send_json(self.app.service.proposals())
        elif parsed.path == "/api/search":
            query = parse_qs(parsed.query).get("q", [""])[0]
            try:
                self._send_json(self.app.service.search(query))
            except ActionError as exc:
                self._error(400, str(exc).split(":", 1)[0])
        else:
            self._error(404, "NOT_FOUND")

    def _body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ActionError("INVALID_CONTENT_LENGTH") from exc
        if length < 0 or length > MAX_BODY:
            raise ActionError("REQUEST_TOO_LARGE")
        if "application/json" not in self.headers.get("Content-Type", ""):
            raise ActionError("JSON_REQUIRED")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ActionError("INVALID_JSON") from exc
        if not isinstance(payload, dict):
            raise ActionError("INVALID_JSON")
        return payload

    def do_POST(self) -> None:
        if not self._valid_host():
            self._error(403, "UNTRUSTED_HOST")
            return
        if self.headers.get("X-Personal-Vault-CSRF") != self.app.csrf_token:
            self._error(403, "CSRF_REQUIRED")
            return
        try:
            payload = self._body()
            parsed = urlparse(self.path)
            mode = str(payload.get("mode", "preview"))
            confirm = payload.get("confirm") is True
            if parsed.path == "/api/actions/update":
                result = self.app.service.update(mode=mode, confirm=confirm)
            elif parsed.path == "/api/actions/skill-catalog":
                result = self.app.service.skill_catalog(mode=mode, confirm=confirm)
            elif parsed.path == "/api/actions/qmd":
                result = self.app.service.qmd(mode=mode, confirm=confirm)
            elif parsed.path == "/api/actions/backup":
                result = self.app.service.backup(mode=mode, confirm=confirm)
            elif parsed.path == "/api/actions/github":
                result = self.app.service.github(
                    mode=mode,
                    confirm=confirm,
                    confirmation=str(payload.get("confirmation", "")),
                )
            elif parsed.path == "/api/actions/source":
                result = self.app.service.source(action=str(payload.get("action", "")), payload=payload)
            elif parsed.path == "/api/actions/review":
                result = self.app.service.review(
                    action=str(payload.get("action", "")),
                    proposal_id=str(payload.get("id", "")),
                    confirmation=str(payload.get("confirmation", "")),
                )
            else:
                self._error(404, "NOT_FOUND")
                return
            self._send_json(result)
        except (ActionError, ValueError, RuntimeError) as exc:
            self._error(400, str(exc).split(":", 1)[0])
        except OSError as exc:
            self._error(500, type(exc).__name__.upper())


def create_server(host: str, port: int, *, service: WebActionService) -> PersonalVaultServer:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("LOCALHOST_ONLY")
    server = PersonalVaultServer((host, port), PersonalVaultHandler)
    server.service = service
    server.csrf_token = secrets.token_urlsafe(32)
    return server


def run_server(host: str, port: int, *, service: WebActionService) -> None:
    server = create_server(host, port, service=service)
    try:
        print(f"Personal Knowledge Vault: http://{host}:{server.server_address[1]}")
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

