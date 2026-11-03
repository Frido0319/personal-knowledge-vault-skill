from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping

from .audit import AuditLogger
from .config import load_config
from .security import redact_text


PROPOSAL_SCHEMA_VERSION = 1
STAGING_GENERATOR = "personal-knowledge-vault-staging"
APPROVED_GENERATOR = "personal-knowledge-vault-reviewed"
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
_KNOWLEDGE_TYPES = {"concept", "decision", "procedure", "lesson", "synthesis"}
_TARGETS = {"knowledge", "synthesis"}
_SENSITIVITY = {"normal", "private", "restricted"}


class ProposalError(ValueError):
    """Raised when a semantic knowledge proposal violates the contract."""


def _atomic_text(path: Path, content: str, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name == "posix":
            temporary.chmod(mode)
        os.replace(temporary, path)
        if os.name == "posix":
            path.chmod(mode)
    finally:
        temporary.unlink(missing_ok=True)


def _state_path(config: Mapping[str, Any]) -> Path:
    return Path(str(config["data"])).expanduser() / "state" / "proposals.json"


def load_proposal_state(config: Mapping[str, Any]) -> dict[str, Any]:
    path = _state_path(config)
    if not path.is_file():
        return {"schema_version": PROPOSAL_SCHEMA_VERSION, "proposals": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProposalError("PROPOSAL_STATE_INVALID") from exc
    if payload.get("schema_version") != PROPOSAL_SCHEMA_VERSION or not isinstance(payload.get("proposals"), dict):
        raise ProposalError("PROPOSAL_STATE_INVALID")
    return payload


def write_proposal_state(config: Mapping[str, Any], state: Mapping[str, Any]) -> None:
    content = json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    _atomic_text(_state_path(config), content)


def _require_string(raw: Mapping[str, Any], field: str, *, maximum: int) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ProposalError(f"{field.upper()}_INVALID")
    return value.strip()


def _normalize(raw: object, authorized_sources: set[str]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ProposalError("PROPOSAL_MAPPING_REQUIRED")
    proposal_id = _require_string(raw, "id", maximum=63)
    if not _ID.fullmatch(proposal_id):
        raise ProposalError("PROPOSAL_ID_INVALID")
    target = raw.get("target")
    if target not in _TARGETS:
        raise ProposalError("TARGET_INVALID")
    knowledge_type = raw.get("knowledge_type")
    if knowledge_type not in _KNOWLEDGE_TYPES:
        raise ProposalError("KNOWLEDGE_TYPE_INVALID")
    sensitivity = raw.get("sensitivity")
    if sensitivity not in _SENSITIVITY:
        raise ProposalError("SENSITIVITY_INVALID")
    confidence = raw.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
        raise ProposalError("CONFIDENCE_INVALID")
    references = raw.get("source_refs")
    if not isinstance(references, list) or not references:
        raise ProposalError("SOURCE_REFS_REQUIRED")
    normalized_refs: list[dict[str, str]] = []
    for reference in references:
        if not isinstance(reference, dict):
            raise ProposalError("SOURCE_REF_INVALID")
        source_id = reference.get("source_id")
        record_id = reference.get("record_id")
        if not isinstance(source_id, str) or source_id not in authorized_sources:
            raise ProposalError("SOURCE_NOT_AUTHORIZED")
        if not isinstance(record_id, str) or not record_id.strip() or len(record_id) > 256:
            raise ProposalError("SOURCE_RECORD_ID_INVALID")
        normalized_refs.append({"source_id": source_id, "record_id": redact_text(record_id.strip())})
    proposal = {
        "id": proposal_id,
        "title": redact_text(_require_string(raw, "title", maximum=160)),
        "summary": redact_text(_require_string(raw, "summary", maximum=1000)),
        "body": redact_text(_require_string(raw, "body", maximum=50_000)),
        "knowledge_type": knowledge_type,
        "target": target,
        "source_refs": normalized_refs,
        "confidence": float(confidence),
        "sensitivity": sensitivity,
    }
    canonical = json.dumps(proposal, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    proposal["content_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return proposal


def _render_staging(proposal: Mapping[str, Any]) -> str:
    references = "\n".join(
        f"- `{reference['source_id']}:{reference['record_id']}`" for reference in proposal["source_refs"]
    )
    return (
        "---\n"
        f'title: "{str(proposal["title"]).replace(chr(34), chr(39))}"\n'
        f"generated_by: {STAGING_GENERATOR}\n"
        "review_status: pending\n"
        f"proposal_id: {proposal['id']}\n"
        f"knowledge_type: {proposal['knowledge_type']}\n"
        f"target: {proposal['target']}\n"
        f"confidence: {proposal['confidence']:.3f}\n"
        f"sensitivity: {proposal['sensitivity']}\n"
        "map_level: 5\n"
        "---\n\n"
        f"# {proposal['title']}\n\n"
        "## 摘要 / Summary\n\n"
        f"{proposal['summary']}\n\n"
        "## 待审核正文 / Proposed knowledge\n\n"
        f"{proposal['body']}\n\n"
        "## 来源证据 / Source evidence\n\n"
        f"{references}\n"
    )


def write_staging_index(config: Mapping[str, Any], state: Mapping[str, Any]) -> None:
    vault = Path(str(config["vault"])).expanduser()
    chinese = config.get("language") == "zh-CN"
    name = "00-待审核.md" if chinese else "00-Pending Review.md"
    pending = [
        value
        for value in state["proposals"].values()
        if isinstance(value, dict) and value.get("status") == "pending"
    ]
    pending.sort(key=lambda item: str(item.get("id", "")))
    links = [f"- [[{item['id']}|{item['title']}]] · {item['knowledge_type']} · {item['confidence']:.2f}" for item in pending]
    title = "待审核知识" if chinese else "Pending knowledge review"
    empty = "当前没有待审核提案。" if chinese else "There is no pending proposal."
    content = (
        "---\n"
        f'title: "{title}"\n'
        f"generated_by: {STAGING_GENERATOR}\n"
        "map_level: 5\n"
        "---\n\n"
        f"# {title}\n\n"
        + ("\n".join(links) if links else empty)
        + "\n"
    )
    _atomic_text(vault / "_staging" / name, content)


def list_proposals(config_path: str | Path) -> list[dict[str, Any]]:
    config = load_config(config_path)
    state = load_proposal_state(config)
    visible_fields = ("id", "title", "knowledge_type", "target", "confidence", "sensitivity", "status", "target_path")
    return [
        {field: proposal[field] for field in visible_fields if field in proposal}
        for proposal in sorted(state["proposals"].values(), key=lambda item: str(item.get("id", "")))
        if isinstance(proposal, dict)
    ]


def stage_proposals(config_path: str | Path, input_path: str | Path, *, dry_run: bool = False) -> dict[str, Any]:
    config_file = Path(config_path).expanduser()
    config = load_config(config_file)
    enabled = {
        str(source["id"])
        for source in config["sources"]
        if isinstance(source, dict) and source.get("enabled") is True and isinstance(source.get("id"), str)
    }
    try:
        batch = json.loads(Path(input_path).expanduser().read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProposalError("PROPOSAL_INPUT_INVALID") from exc
    if not isinstance(batch, dict) or batch.get("schema_version") != PROPOSAL_SCHEMA_VERSION or not isinstance(batch.get("proposals"), list):
        raise ProposalError("PROPOSAL_BATCH_INVALID")
    normalized = [_normalize(raw, enabled) for raw in batch["proposals"]]
    if len({proposal["id"] for proposal in normalized}) != len(normalized):
        raise ProposalError("DUPLICATE_PROPOSAL_ID")

    state = load_proposal_state(config)
    result = {"created": 0, "updated": 0, "unchanged": 0, "would_create": 0, "dry_run": dry_run}
    actions: list[tuple[str, dict[str, Any], str]] = []
    for proposal in normalized:
        existing = state["proposals"].get(proposal["id"])
        if existing is None:
            action = "create"
            result["would_create"] += 1
        elif existing.get("status") != "pending":
            if existing.get("content_hash") == proposal["content_hash"]:
                action = "unchanged"
            else:
                raise ProposalError("PROPOSAL_FINALIZED")
        elif existing.get("content_hash") == proposal["content_hash"]:
            action = "unchanged"
        else:
            action = "update"
        actions.append((action, proposal, _render_staging(proposal)))
    if dry_run:
        result["unchanged"] = sum(1 for action, _, _ in actions if action == "unchanged")
        return result

    vault = Path(str(config["vault"])).expanduser()
    changed = False
    for action, proposal, content in actions:
        if action == "unchanged":
            result["unchanged"] += 1
            continue
        target = vault / "_staging" / f"{proposal['id']}.md"
        if target.exists():
            try:
                current = target.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise ProposalError("STAGING_TARGET_UNREADABLE") from exc
            if f"generated_by: {STAGING_GENERATOR}" not in current[:1000]:
                raise ProposalError("MANUAL_STAGING_TARGET_PROTECTED")
        _atomic_text(target, content)
        state["proposals"][proposal["id"]] = {**proposal, "status": "pending"}
        result["created" if action == "create" else "updated"] += 1
        changed = True
    if changed:
        write_proposal_state(config, state)
        write_staging_index(config, state)
        AuditLogger(Path(str(config["data"])) / "audit" / "events.jsonl").append(
            "proposals_staged",
            details={"created": result["created"], "updated": result["updated"], "ids": [item[1]["id"] for item in actions]},
        )
    return result

