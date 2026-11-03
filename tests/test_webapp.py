from __future__ import annotations

import http.client
import json
from pathlib import Path
import threading

import pytest

import personal_vault.cli as cli_module
from personal_vault.paths import VaultPaths
from personal_vault.setup import initialize
from personal_vault.web_actions import WebActionService
from personal_vault.webapp import MAX_BODY, create_server


@pytest.fixture
def live_server(tmp_path: Path):
    paths = VaultPaths.from_roots(tmp_path / "vault", tmp_path / "data")
    initialize(paths=paths, language="zh-CN")
    server = create_server("127.0.0.1", 0, service=WebActionService(Path(paths.config)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield paths, server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def _request(server, method: str, path: str, *, body: bytes | None = None, headers: dict[str, str] | None = None):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=3)
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    payload = response.read()
    response_headers = dict(response.getheaders())
    connection.close()
    return response.status, response_headers, payload


def test_server_refuses_non_loopback_binding(tmp_path: Path) -> None:
    paths = VaultPaths.from_roots(tmp_path / "vault", tmp_path / "data")
    initialize(paths=paths, language="zh-CN")

    with pytest.raises(ValueError, match="LOCALHOST_ONLY"):
        create_server("0.0.0.0", 8766, service=WebActionService(Path(paths.config)))


def test_static_ui_and_security_headers(live_server) -> None:
    _, server = live_server

    status, headers, body = _request(server, "GET", "/")

    text = body.decode("utf-8")
    assert status == 200
    assert "个人知识库" in text
    assert "来源" in text and "审核" in text and "维护" in text
    assert headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in headers["Content-Security-Policy"]
    assert "TODO" not in text


def test_status_returns_csrf_and_post_requires_it(live_server) -> None:
    paths, server = live_server
    status, _, body = _request(server, "GET", "/api/status")
    payload = json.loads(body)
    assert status == 200
    token = payload["_csrf"]

    request_body = json.dumps({"mode": "preview"}).encode("utf-8")
    denied, _, _ = _request(
        server,
        "POST",
        "/api/actions/update",
        body=request_body,
        headers={"Content-Type": "application/json"},
    )
    accepted, _, accepted_body = _request(
        server,
        "POST",
        "/api/actions/update",
        body=request_body,
        headers={"Content-Type": "application/json", "X-Personal-Vault-CSRF": token},
    )

    assert denied == 403
    assert accepted == 200
    assert json.loads(accepted_body)["applied"] is False
    assert not (Path(paths.vault) / "00-首页.md").exists()


def test_apply_requires_confirm_and_unknown_routes_are_closed(live_server) -> None:
    _, server = live_server
    _, _, status_body = _request(server, "GET", "/api/status")
    token = json.loads(status_body)["_csrf"]
    headers = {"Content-Type": "application/json", "X-Personal-Vault-CSRF": token}

    denied, _, body = _request(
        server,
        "POST",
        "/api/actions/update",
        body=json.dumps({"mode": "apply", "confirm": False}).encode(),
        headers=headers,
    )
    missing, _, _ = _request(server, "GET", "/api/shell")

    assert denied == 400
    assert json.loads(body)["error"] == "APPLY_CONFIRMATION_REQUIRED"
    assert missing == 404


def test_untrusted_host_and_oversized_body_are_rejected(live_server) -> None:
    _, server = live_server
    untrusted, _, _ = _request(server, "GET", "/api/status", headers={"Host": "evil.example"})
    _, _, status_body = _request(server, "GET", "/api/status")
    token = json.loads(status_body)["_csrf"]
    oversized, _, body = _request(
        server,
        "POST",
        "/api/actions/update",
        body=b"x" * (MAX_BODY + 1),
        headers={
            "Content-Type": "application/json",
            "X-Personal-Vault-CSRF": token,
        },
    )

    assert untrusted == 403
    assert oversized == 400
    assert json.loads(body)["error"] == "REQUEST_TOO_LARGE"


def test_search_api_returns_only_formal_knowledge(live_server) -> None:
    paths, server = live_server
    formal = Path(paths.vault) / "knowledge"
    staged = Path(paths.vault) / "_staging"
    formal.mkdir()
    staged.mkdir()
    (formal / "formal.md").write_text("# Evidence\nsearchable phrase", encoding="utf-8")
    (staged / "pending.md").write_text("# Pending\nsearchable phrase", encoding="utf-8")

    status, _, body = _request(server, "GET", "/api/search?q=searchable%20phrase")

    assert status == 200
    assert [item["path"] for item in json.loads(body)] == ["knowledge/formal.md"]


def test_cli_serve_passes_only_configured_localhost(tmp_path: Path, monkeypatch) -> None:
    paths = VaultPaths.from_roots(tmp_path / "vault", tmp_path / "data")
    initialize(paths=paths, language="zh-CN")
    captured: dict[str, object] = {}

    def fake_run_server(host: str, port: int, *, service: WebActionService) -> None:
        captured.update({"host": host, "port": port, "service": service})

    monkeypatch.setattr(cli_module, "run_server", fake_run_server)

    assert cli_module.main(["serve", "--config", str(paths.config), "--host", "127.0.0.1", "--port", "9988"]) == 0
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 9988
    assert isinstance(captured["service"], WebActionService)


def test_static_ui_avoids_csp_blocked_inline_styles_and_labels_mobile_tables() -> None:
    static = Path(__file__).parents[1] / "src" / "personal_vault" / "web" / "static"
    script = (static / "app.js").read_text(encoding="utf-8")

    assert "style=" not in script
    assert "<progress" in script
    assert 'data-label="路径"' in script
    assert 'data-label="操作"' in script
    stylesheet = (static / "app.css").read_text(encoding="utf-8")
    assert "grid-template-rows: auto 1fr" in stylesheet
