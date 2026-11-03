from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Callable, Mapping

from .config import load_config
from .proposals import _atomic_text
from .search import EXCLUDED_NAMESPACES


class IntegrationError(RuntimeError):
    """Raised when an optional integration is disabled or fails closed."""


Runner = Callable[..., Any]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _settings(config: Mapping[str, Any], name: str) -> dict[str, Any]:
    integrations = config.get("integrations")
    if not isinstance(integrations, dict) or not isinstance(integrations.get(name), dict):
        raise IntegrationError(f"{name.upper()}_DISABLED")
    settings = dict(integrations[name])
    if settings.get("enabled") is not True:
        raise IntegrationError(f"{name.upper()}_DISABLED")
    return settings


def _resolve_executable(settings: Mapping[str, Any], expected: str) -> str:
    configured = str(settings.get("executable") or expected)
    candidate = Path(configured).expanduser()
    name = candidate.name.casefold()
    if name not in {expected.casefold(), f"{expected.casefold()}.exe"}:
        raise IntegrationError(f"{expected.upper()}_EXECUTABLE_NOT_ALLOWED")
    if candidate.parent != Path(".") or candidate.is_absolute():
        if not candidate.is_file():
            raise IntegrationError(f"{expected.upper()}_EXECUTABLE_NOT_FOUND")
        return str(candidate.resolve(strict=True))
    resolved = shutil.which(configured)
    if not resolved:
        raise IntegrationError(f"{expected.upper()}_EXECUTABLE_NOT_FOUND")
    return resolved


def _formal_documents(vault: Path) -> list[Path]:
    if not vault.is_dir():
        return []
    documents: list[Path] = []
    for path in vault.rglob("*.md"):
        try:
            relative = path.relative_to(vault)
        except ValueError:
            continue
        if relative.parts and relative.parts[0] in EXCLUDED_NAMESPACES:
            continue
        if path.is_file() and not path.is_symlink():
            documents.append(path)
    return sorted(documents, key=lambda item: item.relative_to(vault).as_posix())


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    _atomic_text(path, json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def _run_checked(runner: Runner, argv: list[str], *, env: Mapping[str, str]) -> Any:
    result = runner(argv, check=False, capture_output=True, text=True, env=dict(env))
    if int(getattr(result, "returncode", 1)) != 0:
        raise IntegrationError("QMD_COMMAND_FAILED")
    return result


def run_qmd_update(
    config_path: str | Path,
    *,
    apply: bool = False,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    config = load_config(config_path)
    settings = _settings(config, "qmd")
    executable = _resolve_executable(settings, "qmd")
    collection = str(settings.get("collection", "personal-knowledge-vault"))
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,62}", collection):
        raise IntegrationError("QMD_COLLECTION_INVALID")
    vault = Path(str(config["vault"])).expanduser()
    data = Path(str(config["data"])).expanduser()
    documents = _formal_documents(vault)
    root = data / "qmd"
    publish = root / "publish"
    qmd_config = root / "config"
    index_path = root / "index.sqlite"
    first_command = [
        executable,
        "--index",
        collection,
        "collection",
        "add",
        str(publish),
        "--name",
        collection,
        "--mask",
        "**/*.md",
    ]
    result: dict[str, Any] = {
        "applied": False,
        "documents": len(documents),
        "collection": collection,
        "publish_path": str(publish),
        "commands": [first_command, [executable, "--index", collection, "update"]],
    }
    if not apply:
        return result

    next_publish = root / "publish.next"
    previous = root / "publish.previous"
    shutil.rmtree(next_publish, ignore_errors=True)
    shutil.rmtree(previous, ignore_errors=True)
    next_publish.mkdir(parents=True, mode=0o700)
    for source in documents:
        relative = source.relative_to(vault)
        target = next_publish / relative
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copy2(source, target)
    if publish.exists():
        publish.replace(previous)
    next_publish.replace(publish)
    qmd_config.mkdir(parents=True, exist_ok=True, mode=0o700)
    environment = os.environ.copy()
    environment.update({"QMD_CONFIG_DIR": str(qmd_config), "INDEX_PATH": str(index_path), "NO_COLOR": "1"})
    try:
        if not (qmd_config / f"{collection}.yml").is_file():
            _run_checked(runner, first_command, env=environment)
        _run_checked(
            runner,
            [executable, "--index", collection, "context", "add", f"qmd://{collection}", "Reviewed personal knowledge only; cite retrieved Markdown."],
            env=environment,
        )
        _run_checked(runner, [executable, "--index", collection, "update"], env=environment)
        if settings.get("embed", True) is True:
            _run_checked(
                runner,
                [executable, "--index", collection, "embed", "-f", "-c", collection, "--timeout", "30"],
                env=environment,
            )
    except Exception:
        shutil.rmtree(publish, ignore_errors=True)
        if previous.exists():
            previous.replace(publish)
        raise
    shutil.rmtree(previous, ignore_errors=True)
    status = {"at": _now(), "status": "ok", "documents": len(documents), "collection": collection, "embedded": settings.get("embed", True) is True}
    _write_json(data / "state" / "qmd-status.json", status)
    result.update({"applied": True, **status})
    return result


def run_restic_backup(
    config_path: str | Path,
    *,
    apply: bool = False,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    config = load_config(config_path)
    settings = _settings(config, "restic")
    executable = _resolve_executable(settings, "restic")
    repository = str(settings.get("repository", "")).strip()
    if not repository:
        raise IntegrationError("RESTIC_REPOSITORY_REQUIRED")
    if any(key in settings for key in ("password", "password_file", "password_command")):
        raise IntegrationError("RESTIC_PASSWORD_MUST_NOT_BE_IN_CONFIG")
    vault = Path(str(config["vault"])).expanduser()
    data = Path(str(config["data"])).expanduser()
    argv = [
        executable,
        "-r",
        repository,
        "backup",
        str(vault),
        str(data / "config"),
        str(data / "state"),
        str(data / "audit"),
        "--exclude",
        str(data / "qmd"),
        "--exclude",
        str(data / "github"),
        "--exclude",
        str(data / "backups"),
        "--json",
    ]
    result: dict[str, Any] = {"applied": False, "repository": repository, "command": argv}
    if not apply:
        return result
    if not any(os.environ.get(name) for name in ("RESTIC_PASSWORD", "RESTIC_PASSWORD_FILE", "RESTIC_PASSWORD_COMMAND")):
        raise IntegrationError("RESTIC_PASSWORD_ENV_REQUIRED")
    completed = runner(argv, check=False, capture_output=True, text=True, env=os.environ.copy())
    if int(getattr(completed, "returncode", 1)) != 0:
        raise IntegrationError("RESTIC_COMMAND_FAILED")
    snapshot_id: str | None = None
    for line in str(getattr(completed, "stdout", "")).splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("snapshot_id"):
            snapshot_id = str(payload["snapshot_id"])
    status = {"at": _now(), "status": "ok", "repository": repository, "snapshot_id": snapshot_id}
    _write_json(data / "state" / "backup-status.json", status)
    result.update({"applied": True, **status})
    return result


def doctor(config_path: str | Path) -> dict[str, Any]:
    """Run read-only core checks and report optional integrations separately."""

    path = Path(config_path).expanduser()
    config = load_config(path)
    vault = Path(str(config["vault"])).expanduser()
    data = Path(str(config["data"])).expanduser()
    owner_only = True
    if os.name == "posix" and path.is_file():
        owner_only = path.stat().st_mode & 0o077 == 0
    checks = {
        "python": sys.version_info >= (3, 11),
        "config": path.is_file(),
        "config_owner_only": owner_only,
        "vault": vault.is_dir(),
        "data": data.is_dir(),
        "separate_roots": vault.resolve(strict=False) != data.resolve(strict=False)
        and data.resolve(strict=False) not in vault.resolve(strict=False).parents
        and vault.resolve(strict=False) not in data.resolve(strict=False).parents,
    }
    optional: dict[str, dict[str, Any]] = {}
    for name in ("qmd", "restic"):
        settings = config.get("integrations", {}).get(name, {})
        executable = str(settings.get("executable") or name) if isinstance(settings, dict) else name
        optional[name] = {
            "enabled": bool(isinstance(settings, dict) and settings.get("enabled") is True),
            "available": bool(Path(executable).expanduser().is_file() or shutil.which(executable)),
        }
    optional["github"] = {
        "enabled": bool(config.get("integrations", {}).get("github", {}).get("enabled", False)),
        "available": shutil.which("gh") is not None,
    }
    return {"ok": all(checks.values()), "checks": checks, "optional": optional}
