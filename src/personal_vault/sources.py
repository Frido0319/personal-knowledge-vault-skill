from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .audit import AuditLogger
from .config import load_config, write_config_atomic
from .security import SecurityBoundaryError, is_forbidden_relative_path, validate_authorized_root


SOURCE_KINDS = {
    "project",
    "learning",
    "documents",
    "skill",
    "agent_history",
    "weflow",
    "qq",
}
SECONDARY_AUTHORIZATION_KINDS = {"agent_history", "weflow", "qq"}
_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")


class SourceConfigError(ValueError):
    """Raised for invalid explicit source configuration."""


class ConsentError(ValueError):
    """Raised when an exact enable or secondary consent phrase is missing."""


def _audit_for(config_path: Path) -> AuditLogger:
    try:
        data_root = config_path.parent.parent
    except IndexError as exc:
        raise SourceConfigError("CONFIG_PATH_INVALID") from exc
    return AuditLogger(data_root / "audit" / "events.jsonl")


def _validate_source_path(value: str | Path) -> Path:
    source = Path(value).expanduser()
    if source.is_symlink():
        raise SourceConfigError("SOURCE_SYMLINK_ROOT_NOT_ALLOWED")
    resolved = source.resolve(strict=False)
    if is_forbidden_relative_path(resolved):
        raise SourceConfigError("SOURCE_PATH_FORBIDDEN")
    if resolved.is_dir():
        try:
            return validate_authorized_root(resolved, home=Path.home())
        except SecurityBoundaryError as exc:
            raise SourceConfigError(str(exc)) from exc
    if resolved.is_file():
        return resolved
    raise SourceConfigError("SOURCE_PATH_NOT_FOUND")


def list_sources(config_path: str | Path) -> list[dict[str, Any]]:
    payload = load_config(config_path)
    return [dict(entry) for entry in payload["sources"] if isinstance(entry, dict)]


def add_source(
    config_path: str | Path,
    *,
    source_id: str,
    kind: str,
    path: str | Path,
) -> dict[str, Any]:
    if not _ID_PATTERN.fullmatch(source_id):
        raise SourceConfigError("SOURCE_ID_INVALID")
    if kind not in SOURCE_KINDS:
        raise SourceConfigError("SOURCE_KIND_INVALID")
    source_path = _validate_source_path(path)
    config = Path(config_path).expanduser()
    payload = load_config(config)
    if any(entry.get("id") == source_id for entry in payload["sources"] if isinstance(entry, dict)):
        raise SourceConfigError("DUPLICATE_SOURCE_ID")
    entry: dict[str, Any] = {
        "id": source_id,
        "kind": kind,
        "path": str(source_path),
        "enabled": False,
        "secondary_authorization": False,
    }
    payload["sources"].append(entry)
    write_config_atomic(config, payload)
    _audit_for(config).append("source_added", source_id=source_id, details={"kind": kind, "path": str(source_path)})
    return dict(entry)


def _find(payload: dict[str, Any], source_id: str) -> dict[str, Any]:
    for entry in payload["sources"]:
        if isinstance(entry, dict) and entry.get("id") == source_id:
            return entry
    raise SourceConfigError("SOURCE_NOT_FOUND")


def enable_source(config_path: str | Path, source_id: str, *, confirmation: str) -> dict[str, Any]:
    config = Path(config_path).expanduser()
    payload = load_config(config)
    entry = _find(payload, source_id)
    kind = str(entry.get("kind", ""))
    if kind in SECONDARY_AUTHORIZATION_KINDS:
        expected = f"AUTHORIZE:{source_id}:{kind}"
        if confirmation != expected:
            raise ConsentError("SECONDARY_AUTHORIZATION_REQUIRED")
        entry["secondary_authorization"] = True
    elif confirmation != f"ENABLE:{source_id}":
        raise ConsentError("ENABLE_CONFIRMATION_REQUIRED")
    changed = not bool(entry.get("enabled"))
    entry["enabled"] = True
    write_config_atomic(config, payload)
    if changed:
        _audit_for(config).append("source_enabled", source_id=source_id, details={"kind": kind})
    result = dict(entry)
    result["changed"] = changed
    return result


def disable_source(config_path: str | Path, source_id: str) -> dict[str, Any]:
    config = Path(config_path).expanduser()
    payload = load_config(config)
    entry = _find(payload, source_id)
    changed = bool(entry.get("enabled"))
    entry["enabled"] = False
    if changed:
        write_config_atomic(config, payload)
        _audit_for(config).append("source_disabled", source_id=source_id, details={"kind": entry.get("kind")})
    result = dict(entry)
    result["changed"] = changed
    return result
