from pathlib import Path

from personal_vault.cli import main
from personal_vault.integrations import doctor
from personal_vault.paths import VaultPaths
from personal_vault.setup import initialize


def test_cli_search_status_and_doctor_are_available_without_optional_tools(tmp_path: Path, capsys) -> None:
    paths = VaultPaths.from_roots(tmp_path / "vault", tmp_path / "data")
    initialize(paths=paths, language="zh-CN")
    knowledge = Path(paths.vault) / "knowledge"
    knowledge.mkdir()
    (knowledge / "note.md").write_text("# 本地知识\n\n可审计的检索证据。\n", encoding="utf-8")

    assert main(["search", "--config", str(paths.config), "--query", "检索"]) == 0
    assert main(["status", "--config", str(paths.config), "--format", "json"]) == 0
    assert main(["doctor", "--config", str(paths.config)]) == 0

    output = capsys.readouterr().out
    assert "knowledge/note.md" in output
    assert '"formal_pages": 1' in output
    assert '"ok": true' in output


def test_doctor_reports_core_ready_and_optional_tools_separately(tmp_path: Path) -> None:
    paths = VaultPaths.from_roots(tmp_path / "vault", tmp_path / "data")
    initialize(paths=paths, language="en")

    report = doctor(Path(paths.config))

    assert report["ok"] is True
    assert report["checks"]["python"] is True
    assert report["checks"]["vault"] is True
    assert "qmd" in report["optional"]
    assert "restic" in report["optional"]


def test_cli_status_text_uses_configured_language(tmp_path: Path, capsys) -> None:
    paths = VaultPaths.from_roots(tmp_path / "vault", tmp_path / "data")
    initialize(paths=paths, language="en")

    assert main(["status", "--config", str(paths.config), "--format", "text"]) == 0

    assert "Personal Knowledge Vault status" in capsys.readouterr().out

