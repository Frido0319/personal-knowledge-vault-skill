from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .audit import AuditLogger
from .config import load_config
from .proposals import (
    APPROVED_GENERATOR,
    STAGING_GENERATOR,
    _atomic_text,
    load_proposal_state,
    write_proposal_state,
    write_staging_index,
)


class ReviewError(ValueError):
    """Raised when a proposal review cannot be applied safely."""


def _find(state: Mapping[str, Any], proposal_id: str) -> dict[str, Any]:
    proposal = state["proposals"].get(proposal_id)
    if not isinstance(proposal, dict):
        raise ReviewError("PROPOSAL_NOT_FOUND")
    return proposal


def _render_approved(proposal: Mapping[str, Any]) -> str:
    references = "\n".join(
        f"- `{reference['source_id']}:{reference['record_id']}`" for reference in proposal["source_refs"]
    )
    return (
        "---\n"
        f'title: "{str(proposal["title"]).replace(chr(34), chr(39))}"\n'
        f"generated_by: {APPROVED_GENERATOR}\n"
        "review_status: approved\n"
        f"proposal_id: {proposal['id']}\n"
        f"knowledge_type: {proposal['knowledge_type']}\n"
        f"confidence: {proposal['confidence']:.3f}\n"
        f"sensitivity: {proposal['sensitivity']}\n"
        "map_level: 4\n"
        "---\n\n"
        f"# {proposal['title']}\n\n"
        f"> {proposal['summary']}\n\n"
        f"{proposal['body']}\n\n"
        "## 来源证据 / Source evidence\n\n"
        f"{references}\n"
    )


def _remove_staging(vault: Path, proposal_id: str) -> None:
    path = vault / "_staging" / f"{proposal_id}.md"
    if not path.is_file():
        return
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return
    if f"generated_by: {STAGING_GENERATOR}" in content[:1000]:
        path.unlink()


def promote_proposal(config_path: str | Path, proposal_id: str, *, confirmation: str) -> dict[str, Any]:
    if confirmation != f"PROMOTE:{proposal_id}":
        raise ReviewError("PROMOTE_CONFIRMATION_REQUIRED")
    config = load_config(config_path)
    state = load_proposal_state(config)
    proposal = _find(state, proposal_id)
    if proposal.get("status") == "approved":
        return {"id": proposal_id, "status": "approved", "changed": False, "target_path": proposal.get("target_path")}
    if proposal.get("status") != "pending":
        raise ReviewError("PROPOSAL_NOT_PENDING")
    vault = Path(str(config["vault"])).expanduser()
    relative = f"{proposal['target']}/{proposal_id}.md"
    target = vault / relative
    expected = _render_approved(proposal)
    if target.exists():
        try:
            current = target.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ReviewError("TARGET_UNREADABLE") from exc
        if f"generated_by: {APPROVED_GENERATOR}" not in current[:1000]:
            raise ReviewError("MANUAL_TARGET_PROTECTED")
    _atomic_text(target, expected)
    proposal["status"] = "approved"
    proposal["target_path"] = relative
    write_proposal_state(config, state)
    _remove_staging(vault, proposal_id)
    write_staging_index(config, state)
    AuditLogger(Path(str(config["data"])) / "audit" / "approvals.jsonl").append(
        "proposal_promoted",
        source_id=proposal_id,
        details={
            "target_path": relative,
            "content_hash": proposal["content_hash"],
            "source_refs": proposal["source_refs"],
        },
    )
    return {"id": proposal_id, "status": "approved", "changed": True, "target_path": relative}


def reject_proposal(config_path: str | Path, proposal_id: str, *, confirmation: str) -> dict[str, Any]:
    if confirmation != f"REJECT:{proposal_id}":
        raise ReviewError("REJECT_CONFIRMATION_REQUIRED")
    config = load_config(config_path)
    state = load_proposal_state(config)
    proposal = _find(state, proposal_id)
    if proposal.get("status") == "rejected":
        return {"id": proposal_id, "status": "rejected", "changed": False}
    if proposal.get("status") != "pending":
        raise ReviewError("PROPOSAL_NOT_PENDING")
    proposal["status"] = "rejected"
    write_proposal_state(config, state)
    vault = Path(str(config["vault"])).expanduser()
    _remove_staging(vault, proposal_id)
    write_staging_index(config, state)
    AuditLogger(Path(str(config["data"])) / "audit" / "approvals.jsonl").append(
        "proposal_rejected",
        source_id=proposal_id,
        details={"content_hash": proposal["content_hash"], "source_refs": proposal["source_refs"]},
    )
    return {"id": proposal_id, "status": "rejected", "changed": True}

