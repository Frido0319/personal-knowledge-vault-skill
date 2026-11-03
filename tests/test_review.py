from pathlib import Path

import pytest

from personal_vault.paths import VaultPaths
from personal_vault.proposals import list_proposals, stage_proposals
from personal_vault.review import ReviewError, promote_proposal, reject_proposal
from personal_vault.setup import initialize
from personal_vault.sources import add_source, enable_source


FIXTURE = Path(__file__).parent / "fixtures" / "synthetic-proposals.json"


def _staged(tmp_path: Path) -> VaultPaths:
    paths = VaultPaths.from_roots(tmp_path / "vault", tmp_path / "data")
    initialize(paths=paths, language="zh-CN")
    export = tmp_path / "history"
    export.mkdir()
    add_source(Path(paths.config), source_id="agent-history", kind="agent_history", path=export)
    enable_source(Path(paths.config), "agent-history", confirmation="AUTHORIZE:agent-history:agent_history")
    stage_proposals(Path(paths.config), FIXTURE)
    return paths


def test_promote_requires_exact_confirmation(tmp_path: Path) -> None:
    paths = _staged(tmp_path)

    with pytest.raises(ReviewError, match="CONFIRMATION"):
        promote_proposal(Path(paths.config), "local-first-rule", confirmation="yes")


def test_promote_moves_reviewed_knowledge_and_writes_body_free_ledger(tmp_path: Path) -> None:
    paths = _staged(tmp_path)

    result = promote_proposal(
        Path(paths.config),
        "local-first-rule",
        confirmation="PROMOTE:local-first-rule",
    )

    target = Path(paths.vault) / "knowledge" / "local-first-rule.md"
    assert result["changed"] is True
    assert target.is_file()
    content = target.read_text(encoding="utf-8")
    assert "review_status: approved" in content
    assert "map_level: 4" in content
    assert "agent-history:session-001#message-8" in content
    assert not (Path(paths.vault) / "_staging" / "local-first-rule.md").exists()
    assert list_proposals(Path(paths.config))[0]["status"] == "approved"
    ledger = (Path(paths.data) / "audit" / "approvals.jsonl").read_text(encoding="utf-8")
    assert "local-first-rule" in ledger
    assert "先执行 preview" not in ledger


def test_promote_is_idempotent(tmp_path: Path) -> None:
    paths = _staged(tmp_path)
    promote_proposal(Path(paths.config), "local-first-rule", confirmation="PROMOTE:local-first-rule")

    second = promote_proposal(Path(paths.config), "local-first-rule", confirmation="PROMOTE:local-first-rule")

    assert second["changed"] is False
    assert second["status"] == "approved"


def test_promote_never_overwrites_manual_target(tmp_path: Path) -> None:
    paths = _staged(tmp_path)
    target = Path(paths.vault) / "knowledge" / "local-first-rule.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Manual canonical note\n", encoding="utf-8")

    with pytest.raises(ReviewError, match="MANUAL_TARGET_PROTECTED"):
        promote_proposal(Path(paths.config), "local-first-rule", confirmation="PROMOTE:local-first-rule")

    assert target.read_text(encoding="utf-8") == "# Manual canonical note\n"


def test_reject_removes_only_staging_and_is_idempotent(tmp_path: Path) -> None:
    paths = _staged(tmp_path)

    first = reject_proposal(Path(paths.config), "local-first-rule", confirmation="REJECT:local-first-rule")
    second = reject_proposal(Path(paths.config), "local-first-rule", confirmation="REJECT:local-first-rule")

    assert first["changed"] is True
    assert second["changed"] is False
    assert not (Path(paths.vault) / "_staging" / "local-first-rule.md").exists()
    assert not (Path(paths.vault) / "knowledge" / "local-first-rule.md").exists()

