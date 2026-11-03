from pathlib import Path

from personal_vault.config import load_config, write_config_atomic
from personal_vault.paths import VaultPaths
from personal_vault.setup import initialize
from personal_vault.status import collect_status, format_status_text


def test_status_distinguishes_formal_pending_and_raw_pages(tmp_path: Path) -> None:
    paths = VaultPaths.from_roots(tmp_path / "vault", tmp_path / "data")
    initialize(paths=paths, language="zh-CN")
    vault = Path(paths.vault)
    (vault / "knowledge").mkdir()
    (vault / "_staging").mkdir()
    (vault / "_raw").mkdir()
    (vault / "knowledge" / "approved.md").write_text("---\nmap_level: 4\n---\n# Approved\n", encoding="utf-8")
    (vault / "_staging" / "pending.md").write_text("# Pending\n", encoding="utf-8")
    (vault / "_raw" / "chat.md").write_text("# Raw\n", encoding="utf-8")

    status = collect_status(Path(paths.config))

    assert status["vault"]["pages"] == 3
    assert status["vault"]["formal_pages"] == 1
    assert status["vault"]["pending_pages"] == 1
    assert status["vault"]["raw_pages"] == 1
    assert status["knowledge_map"]["l4"] == 1
    assert "正式知识 1 页" in format_status_text(status, language="zh-CN")


def test_status_reports_sources_and_optional_integrations_without_running_them(tmp_path: Path) -> None:
    paths = VaultPaths.from_roots(tmp_path / "vault", tmp_path / "data")
    initialize(paths=paths, language="en")
    config = load_config(Path(paths.config))
    config["sources"] = [{"id": "docs", "kind": "documents", "path": str(tmp_path), "enabled": True}]
    config["integrations"]["qmd"]["enabled"] = True
    write_config_atomic(Path(paths.config), config)

    status = collect_status(Path(paths.config))

    assert status["sources"] == {"total": 1, "enabled": 1, "missing": 0}
    assert status["integrations"]["qmd"]["enabled"] is True
    assert status["integrations"]["qmd"]["last_run"] is None

