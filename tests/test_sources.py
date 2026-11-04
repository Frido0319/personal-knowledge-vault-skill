import os
from pathlib import Path

import pytest

from personal_vault.audit import AuditLogger
from personal_vault.config import load_config
from personal_vault.paths import VaultPaths
from personal_vault.setup import initialize
from personal_vault.sources import (
    ConsentError,
    SourceConfigError,
    add_source,
    disable_source,
    enable_source,
    list_sources,
)


@pytest.fixture
def initialized(tmp_path: Path) -> tuple[VaultPaths, Path]:
    paths = VaultPaths.from_roots(tmp_path / "vault", tmp_path / "data")
    initialize(paths=paths, language="zh-CN")
    source = tmp_path / "chosen-projects"
    source.mkdir()
    return paths, source


def test_add_source_is_explicit_disabled_and_does_not_discover_siblings(
    initialized: tuple[VaultPaths, Path],
) -> None:
    paths, source = initialized
    sibling = source.parent / "not-authorized"
    sibling.mkdir()

    result = add_source(Path(paths.config), source_id="projects", kind="project", path=source)

    assert result["enabled"] is False
    entries = list_sources(Path(paths.config))
    assert [entry["id"] for entry in entries] == ["projects"]
    assert str(sibling) not in Path(paths.config).read_text(encoding="utf-8")


def test_primary_source_requires_exact_enable_confirmation(
    initialized: tuple[VaultPaths, Path],
) -> None:
    paths, source = initialized
    add_source(Path(paths.config), source_id="projects", kind="project", path=source)

    with pytest.raises(ConsentError, match="CONFIRMATION"):
        enable_source(Path(paths.config), "projects", confirmation="yes")

    enabled = enable_source(Path(paths.config), "projects", confirmation="ENABLE:projects")
    assert enabled["enabled"] is True


@pytest.mark.parametrize("kind", ["agent_history", "weflow", "qq"])
def test_sensitive_sources_require_second_authorization(
    initialized: tuple[VaultPaths, Path], kind: str
) -> None:
    paths, source = initialized
    source_id = f"private-{kind}"
    add_source(Path(paths.config), source_id=source_id, kind=kind, path=source)

    with pytest.raises(ConsentError, match="SECONDARY_AUTHORIZATION"):
        enable_source(Path(paths.config), source_id, confirmation=f"ENABLE:{source_id}")

    entry = enable_source(
        Path(paths.config),
        source_id,
        confirmation=f"AUTHORIZE:{source_id}:{kind}",
    )
    assert entry["enabled"] is True
    assert entry["secondary_authorization"] is True


def test_disable_is_idempotent(initialized: tuple[VaultPaths, Path]) -> None:
    paths, source = initialized
    add_source(Path(paths.config), source_id="docs", kind="documents", path=source)
    enable_source(Path(paths.config), "docs", confirmation="ENABLE:docs")

    assert disable_source(Path(paths.config), "docs")["enabled"] is False
    assert disable_source(Path(paths.config), "docs")["changed"] is False


def test_source_id_kind_and_duplicate_are_validated(initialized: tuple[VaultPaths, Path]) -> None:
    paths, source = initialized
    with pytest.raises(SourceConfigError, match="SOURCE_ID"):
        add_source(Path(paths.config), source_id="../bad", kind="project", path=source)
    with pytest.raises(SourceConfigError, match="SOURCE_KIND"):
        add_source(Path(paths.config), source_id="ok", kind="browser", path=source)

    add_source(Path(paths.config), source_id="docs", kind="documents", path=source)
    with pytest.raises(SourceConfigError, match="DUPLICATE"):
        add_source(Path(paths.config), source_id="docs", kind="documents", path=source)


def test_audit_log_records_metadata_but_never_message_body(tmp_path: Path) -> None:
    audit = AuditLogger(tmp_path / "audit" / "events.jsonl")
    token_prefix = "gh" + "p_"

    audit.append(
        "source_preview",
        source_id="history",
        details={"count": 2, "message_body": "my private sentence", "token": token_prefix + "abcdefghijklmnopqrstuvwxyz1234567890AB"},
    )

    content = audit.path.read_text(encoding="utf-8")
    assert "source_preview" in content
    assert '"count": 2' in content
    assert "my private sentence" not in content
    assert token_prefix not in content
    assert "[OMITTED]" in content


def test_config_remains_owner_only_after_source_changes(initialized: tuple[VaultPaths, Path]) -> None:
    paths, source = initialized
    add_source(Path(paths.config), source_id="docs", kind="documents", path=source)

    assert load_config(Path(paths.config))["sources"][0]["id"] == "docs"
    if os.name != "nt":
        assert Path(paths.config).stat().st_mode & 0o777 == 0o600
