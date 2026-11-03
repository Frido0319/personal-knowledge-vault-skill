from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from .audit import AuditLogger
from .config import load_config
from .inventory import SourceInventory, scan_source
from .manifest import ManifestStore
from .render import GENERATED_BY, render_vault


DETERMINISTIC_SOURCE_KINDS = {"project", "learning", "documents", "skill"}


def _owned(text: str) -> bool:
    return bool(
        re.search(
            rf"^generated_by:\s*{re.escape(GENERATED_BY)}\s*$",
            text[:1000],
            re.MULTILINE,
        )
    )


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _existing_owned(vault: Path) -> set[str]:
    if not vault.is_dir():
        return set()
    result: set[str] = set()
    for path in vault.rglob("*.md"):
        try:
            prefix = path.read_text(encoding="utf-8")[:1000]
        except (OSError, UnicodeError):
            continue
        if _owned(prefix):
            result.add(path.relative_to(vault).as_posix())
    return result


def _plan(vault: Path, pages: dict[str, str]) -> dict[str, Any]:
    changes: list[dict[str, str]] = []
    counts = {"created": 0, "updated": 0, "removed": 0, "protected": 0, "unchanged": 0}
    for relative, expected in pages.items():
        target = vault / Path(relative)
        if not target.exists():
            counts["created"] += 1
            changes.append({"action": "create", "path": relative})
            continue
        try:
            current = target.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            counts["protected"] += 1
            changes.append({"action": "protect", "path": relative})
            continue
        if current == expected:
            counts["unchanged"] += 1
        elif _owned(current):
            counts["updated"] += 1
            changes.append({"action": "update", "path": relative})
        else:
            counts["protected"] += 1
            changes.append({"action": "protect", "path": relative})
    for relative in sorted(_existing_owned(vault) - set(pages)):
        counts["removed"] += 1
        changes.append({"action": "remove", "path": relative})
    return {**counts, "changes": sorted(changes, key=lambda item: (item["path"], item["action"]))}


def _source_id_for(relative: str, inventories: list[SourceInventory]) -> str:
    for inventory in inventories:
        if f"/{inventory.source_id}/" in f"/{relative}":
            return inventory.source_id
    return "system"


def run_update(config_path: str | Path, *, apply: bool = False) -> dict[str, Any]:
    config_file = Path(config_path).expanduser()
    config = load_config(config_file)
    vault = Path(str(config.get("vault", ""))).expanduser()
    data = Path(str(config.get("data", ""))).expanduser()
    inventories: list[SourceInventory] = []
    for source in config["sources"]:
        if (
            isinstance(source, dict)
            and source.get("enabled") is True
            and source.get("kind") in DETERMINISTIC_SOURCE_KINDS
        ):
            inventories.append(scan_source(source))
    pages = render_vault(language=str(config["language"]), inventories=inventories)
    result = _plan(vault, pages)
    result.update(
        {
            "applied": False,
            "sources": len(inventories),
            "items": sum(len(inventory.items) for inventory in inventories),
            "excluded": sum(inventory.excluded for inventory in inventories),
            "errors": sum(len(inventory.errors) for inventory in inventories),
        }
    )
    if not apply:
        return result

    vault.mkdir(parents=True, exist_ok=True, mode=0o700)
    manifest_path = data / "state" / "manifest.sqlite"
    with ManifestStore(manifest_path) as manifest:
        for change in result["changes"]:
            relative = change["path"]
            action = change["action"]
            target = vault / Path(relative)
            if action in {"create", "update"}:
                content = pages[relative]
                _atomic_write(target, content)
                manifest.upsert_page(
                    relative,
                    source_id=_source_id_for(relative, inventories),
                    content_hash=_hash(content),
                )
            elif action == "remove" and target.is_file():
                try:
                    current = target.read_text(encoding="utf-8")
                except (OSError, UnicodeError):
                    continue
                if _owned(current):
                    target.unlink()
                    manifest.delete_page(relative)
        for relative, content in pages.items():
            target = vault / Path(relative)
            if not target.is_file():
                continue
            try:
                actual = target.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            if actual == content and _owned(actual):
                manifest.upsert_page(
                    relative,
                    source_id=_source_id_for(relative, inventories),
                    content_hash=_hash(actual),
                )
    result["applied"] = True
    AuditLogger(data / "audit" / "events.jsonl").append(
        "deterministic_update",
        details={key: result[key] for key in ("created", "updated", "removed", "protected", "unchanged", "sources", "items", "errors")},
    )
    return result
