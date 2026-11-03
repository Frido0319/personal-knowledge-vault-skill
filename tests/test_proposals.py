from pathlib import Path
import json

import pytest

from personal_vault.paths import VaultPaths
from personal_vault.proposals import ProposalError, list_proposals, stage_proposals
from personal_vault.setup import initialize
from personal_vault.sources import add_source, enable_source
from personal_vault.update import run_update


FIXTURE = Path(__file__).parent / "fixtures" / "synthetic-proposals.json"


def _configured(tmp_path: Path) -> VaultPaths:
    paths = VaultPaths.from_roots(tmp_path / "vault", tmp_path / "data")
    initialize(paths=paths, language="zh-CN")
    export = tmp_path / "explicit-agent-export"
    export.mkdir()
    add_source(Path(paths.config), source_id="agent-history", kind="agent_history", path=export)
    enable_source(
        Path(paths.config),
        "agent-history",
        confirmation="AUTHORIZE:agent-history:agent_history",
    )
    return paths


def test_stage_redacts_content_and_remains_outside_formal_knowledge(tmp_path: Path) -> None:
    paths = _configured(tmp_path)

    result = stage_proposals(Path(paths.config), FIXTURE)

    staged = Path(paths.vault) / "_staging" / "local-first-rule.md"
    assert result["created"] == 1
    assert staged.is_file()
    content = staged.read_text(encoding="utf-8")
    assert "owner@example.com" not in content
    assert "[REDACTED:email]" in content
    assert "review_status: pending" in content
    assert not (Path(paths.vault) / "knowledge" / "local-first-rule.md").exists()
    assert list_proposals(Path(paths.config))[0]["status"] == "pending"


def test_stage_dry_run_is_zero_write(tmp_path: Path) -> None:
    paths = _configured(tmp_path)

    result = stage_proposals(Path(paths.config), FIXTURE, dry_run=True)

    assert result["would_create"] == 1
    assert not (Path(paths.vault) / "_staging").exists()
    assert not (Path(paths.data) / "state" / "proposals.json").exists()


def test_unknown_or_disabled_source_reference_is_rejected(tmp_path: Path) -> None:
    paths = _configured(tmp_path)
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["proposals"][0]["source_refs"][0]["source_id"] = "not-authorized"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProposalError, match="SOURCE_NOT_AUTHORIZED"):
        stage_proposals(Path(paths.config), bad)

    assert not (Path(paths.vault) / "_staging").exists()


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("id", "../escape", "PROPOSAL_ID"),
        ("target", "projects", "TARGET"),
        ("confidence", 1.2, "CONFIDENCE"),
        ("knowledge_type", "chat", "KNOWLEDGE_TYPE"),
    ],
)
def test_invalid_proposal_fields_are_rejected(
    tmp_path: Path, field: str, value: object, code: str
) -> None:
    paths = _configured(tmp_path)
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["proposals"][0][field] = value
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProposalError, match=code):
        stage_proposals(Path(paths.config), bad)


def test_restage_pending_proposal_is_idempotent(tmp_path: Path) -> None:
    paths = _configured(tmp_path)
    stage_proposals(Path(paths.config), FIXTURE)

    second = stage_proposals(Path(paths.config), FIXTURE)

    assert second["created"] == 0
    assert second["updated"] == 0
    assert second["unchanged"] == 1


def test_deterministic_update_never_claims_or_removes_staging_pages(tmp_path: Path) -> None:
    paths = _configured(tmp_path)
    stage_proposals(Path(paths.config), FIXTURE)

    preview = run_update(Path(paths.config), apply=False)
    run_update(Path(paths.config), apply=True)

    assert all(not change["path"].startswith("_staging/") for change in preview["changes"])
    assert (Path(paths.vault) / "_staging" / "local-first-rule.md").is_file()
