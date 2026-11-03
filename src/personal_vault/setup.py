from __future__ import annotations

import os
from pathlib import Path, PurePath
from typing import Any

from .config import default_config, load_config, write_config_atomic
from .paths import VaultPaths


def _as_path(value: PurePath) -> Path:
    if not isinstance(value, Path):
        raise ValueError("NATIVE_PATH_REQUIRED")
    return value


def initialize(
    *,
    paths: VaultPaths,
    language: str = "zh-CN",
    repo_root: str | Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Initialize empty private roots without reading or discovering sources."""

    paths.validate(repo_root=Path(repo_root) if repo_root is not None else None)
    vault = _as_path(paths.vault)
    data = _as_path(paths.data)
    config_path = _as_path(paths.config)
    directories = (
        vault,
        vault / ".obsidian",
        data,
        data / "config",
        data / "state",
        data / "audit",
        data / "runtime",
        data / "backups",
    )
    would_create = [str(path) for path in directories if not path.exists()]
    if not config_path.exists():
        would_create.append(str(config_path))
    if dry_run:
        return {"dry_run": True, "created": 0, "would_create": would_create}

    created = 0
    for directory in directories:
        if not directory.exists():
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            created += 1
        if os.name == "posix":
            directory.chmod(0o700)
    if config_path.exists():
        existing = load_config(config_path)
        if existing["language"] != language:
            raise ValueError("EXISTING_CONFIG_LANGUAGE_MISMATCH")
    else:
        write_config_atomic(config_path, default_config(paths=paths, language=language))
        created += 1
    return {"dry_run": False, "created": created, "would_create": []}

