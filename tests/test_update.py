from pathlib import Path
import shutil

from personal_vault.config import load_config, write_config_atomic
from personal_vault.manifest import load_page_records
from personal_vault.paths import VaultPaths
from personal_vault.setup import initialize
from personal_vault.sources import add_source, enable_source
from personal_vault.update import run_update


FIXTURES = Path(__file__).parent / "fixtures"


def _configured(tmp_path: Path) -> VaultPaths:
    paths = VaultPaths.from_roots(tmp_path / "vault", tmp_path / "data")
    initialize(paths=paths, language="zh-CN")
    project_root = tmp_path / "projects"
    shutil.copytree(FIXTURES / "synthetic-project", project_root)
    add_source(Path(paths.config), source_id="projects", kind="project", path=project_root)
    enable_source(Path(paths.config), "projects", confirmation="ENABLE:projects")
    return paths


def test_preview_is_strict_zero_write_then_apply_is_idempotent(tmp_path: Path) -> None:
    paths = _configured(tmp_path)

    preview = run_update(Path(paths.config), apply=False)

    assert preview["created"] >= 4
    assert not (Path(paths.vault) / "00-首页.md").exists()
    assert not Path(paths.manifest).exists()

    applied = run_update(Path(paths.config), apply=True)
    second = run_update(Path(paths.config), apply=False)

    assert applied["applied"] is True
    assert (Path(paths.vault) / "projects" / "projects" / "ProjectAlpha.md").is_file()
    assert second["created"] == 0
    assert second["updated"] == 0
    assert second["removed"] == 0
    assert second["changes"] == []


def test_manual_page_is_never_overwritten(tmp_path: Path) -> None:
    paths = _configured(tmp_path)
    target = Path(paths.vault) / "projects" / "projects" / "ProjectAlpha.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# My manual project note\n", encoding="utf-8")

    result = run_update(Path(paths.config), apply=True)

    assert result["protected"] == 1
    assert target.read_text(encoding="utf-8") == "# My manual project note\n"
    assert "projects/projects/ProjectAlpha.md" not in load_page_records(Path(paths.manifest))


def test_source_change_updates_only_owned_project_pages(tmp_path: Path) -> None:
    paths = _configured(tmp_path)
    run_update(Path(paths.config), apply=True)
    source = tmp_path / "projects" / "ProjectAlpha" / "README.md"
    source.write_text(source.read_text(encoding="utf-8") + "\nNew verified capability.\n", encoding="utf-8")

    preview = run_update(Path(paths.config), apply=False)

    assert preview["updated"] == 2
    assert all("ProjectAlpha" in change["path"] for change in preview["changes"])


def test_disabled_source_disappears_only_from_generated_surface(tmp_path: Path) -> None:
    paths = _configured(tmp_path)
    run_update(Path(paths.config), apply=True)
    config = load_config(Path(paths.config))
    config["sources"][0]["enabled"] = False
    write_config_atomic(Path(paths.config), config)

    preview = run_update(Path(paths.config), apply=False)

    assert preview["removed"] >= 3
    assert all(change["action"] == "remove" for change in preview["changes"] if change["path"].startswith("projects/"))


def test_sensitive_exports_are_evidence_only_not_deterministic_catalogs(tmp_path: Path) -> None:
    paths = VaultPaths.from_roots(tmp_path / "vault", tmp_path / "data")
    initialize(paths=paths, language="zh-CN")
    export = tmp_path / "history"
    export.mkdir()
    (export / "session.json").write_text('{"private": "conversation"}', encoding="utf-8")
    add_source(Path(paths.config), source_id="history", kind="agent_history", path=export)
    enable_source(Path(paths.config), "history", confirmation="AUTHORIZE:history:agent_history")

    result = run_update(Path(paths.config), apply=True)

    assert result["sources"] == 0
    assert not (Path(paths.vault) / "knowledge" / "history").exists()
    assert "conversation" not in "\n".join(
        path.read_text(encoding="utf-8") for path in Path(paths.vault).rglob("*.md")
    )
