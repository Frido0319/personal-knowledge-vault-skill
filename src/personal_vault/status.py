from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
from typing import Any

from .config import load_config
from .proposals import load_proposal_state


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _vault_status(vault: Path) -> tuple[dict[str, Any], dict[str, int]]:
    result = {"path": str(vault), "exists": vault.is_dir(), "pages": 0, "formal_pages": 0, "pending_pages": 0, "raw_pages": 0}
    levels = {f"l{level}": 0 for level in range(6)}
    if not vault.is_dir():
        return result, levels
    for path in vault.rglob("*.md"):
        try:
            relative = path.relative_to(vault)
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError, ValueError):
            continue
        if relative.parts and relative.parts[0] == ".obsidian":
            continue
        result["pages"] += 1
        if relative.parts and relative.parts[0] == "_staging":
            result["pending_pages"] += 1
        elif relative.parts and relative.parts[0] == "_raw":
            result["raw_pages"] += 1
        else:
            result["formal_pages"] += 1
            match = re.search(r"^map_level:\s*([0-5])\s*$", text[:2000], re.MULTILINE)
            if match:
                levels[f"l{match.group(1)}"] += 1
    return result, levels


def _integration(config: dict[str, Any], name: str, state: dict[str, Any] | None) -> dict[str, Any]:
    integration = config.get("integrations", {}).get(name, {})
    if not isinstance(integration, dict):
        integration = {}
    executable = integration.get("executable") or name
    available = bool(Path(str(executable)).is_file() or shutil.which(str(executable)))
    return {
        "enabled": bool(integration.get("enabled", False)),
        "available": available,
        "last_run": state.get("at") if state else None,
        "status": state.get("status") if state else "never",
    }


def collect_status(config_path: str | Path) -> dict[str, Any]:
    config = load_config(config_path)
    vault = Path(str(config["vault"])).expanduser()
    data = Path(str(config["data"])).expanduser()
    vault_status, levels = _vault_status(vault)
    sources = [source for source in config["sources"] if isinstance(source, dict)]
    proposal_state = load_proposal_state(config)
    proposal_counts = {"pending": 0, "approved": 0, "rejected": 0}
    for proposal in proposal_state["proposals"].values():
        if isinstance(proposal, dict) and proposal.get("status") in proposal_counts:
            proposal_counts[str(proposal["status"])] += 1
    qmd_state = _read_json(data / "state" / "qmd-status.json")
    backup_state = _read_json(data / "state" / "backup-status.json")
    github_state = _read_json(data / "state" / "github-status.json")
    return {
        "language": config["language"],
        "vault": vault_status,
        "knowledge_map": levels,
        "sources": {
            "total": len(sources),
            "enabled": sum(source.get("enabled") is True for source in sources),
            "missing": sum(not Path(str(source.get("path", ""))).expanduser().exists() for source in sources),
        },
        "proposals": proposal_counts,
        "integrations": {
            "qmd": _integration(config, "qmd", qmd_state),
            "restic": _integration(config, "restic", backup_state),
            "github": {
                "enabled": bool(config.get("integrations", {}).get("github", {}).get("enabled", False)),
                "visibility": (github_state or {}).get("visibility", "UNVERIFIED"),
                "last_run": (github_state or {}).get("at"),
            },
        },
    }


def format_status_text(status: dict[str, Any], *, language: str | None = None) -> str:
    selected = language or str(status.get("language", "zh-CN"))
    vault = status["vault"]
    sources = status["sources"]
    proposals = status["proposals"]
    if selected == "en":
        return "\n".join(
            (
                "Personal Knowledge Vault status",
                f"- Formal knowledge: {vault['formal_pages']} pages; pending: {vault['pending_pages']}; raw evidence: {vault['raw_pages']}",
                f"- Authorized sources: {sources['enabled']}/{sources['total']} enabled; {sources['missing']} missing",
                f"- Review queue: {proposals['pending']} pending; {proposals['approved']} approved",
            )
        )
    return "\n".join(
        (
            "个人知识库状态",
            f"- 正式知识 {vault['formal_pages']} 页；待审核 {vault['pending_pages']} 页；原始证据 {vault['raw_pages']} 页",
            f"- 授权来源：{sources['enabled']}/{sources['total']} 已启用；{sources['missing']} 个缺失",
            f"- 审核队列：{proposals['pending']} 待审核；{proposals['approved']} 已批准",
        )
    )

