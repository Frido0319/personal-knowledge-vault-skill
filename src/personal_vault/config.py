from __future__ import annotations

import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

import yaml

from .paths import VaultPaths


SCHEMA_VERSION = 1
SUPPORTED_LANGUAGES = {"zh-CN", "en"}


class ConfigError(ValueError):
    """Raised for malformed or unsupported private configuration."""


def default_config(*, paths: VaultPaths, language: str = "zh-CN") -> dict[str, Any]:
    if language not in SUPPORTED_LANGUAGES:
        raise ConfigError("UNSUPPORTED_LANGUAGE")
    return {
        "schema_version": SCHEMA_VERSION,
        "language": language,
        "vault": str(paths.vault),
        "data": str(paths.data),
        "sources": [],
        "skills": [],
        "integrations": {
            "qmd": {"enabled": False, "collection": "personal-knowledge-vault"},
            "restic": {"enabled": False, "repository": ""},
            "github": {"enabled": False, "repository": ""},
        },
        "schedule": {"enabled": False, "hour": 3, "minute": 15},
    }


def _validate(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ConfigError("CONFIG_MAPPING_REQUIRED")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ConfigError("UNSUPPORTED_SCHEMA_VERSION")
    if payload.get("language") not in SUPPORTED_LANGUAGES:
        raise ConfigError("UNSUPPORTED_LANGUAGE")
    if not isinstance(payload.get("sources"), list):
        raise ConfigError("SOURCES_LIST_REQUIRED")
    return dict(payload)


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).expanduser()
    try:
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ConfigError("CONFIG_READ_FAILED") from exc
    return _validate(payload)


def write_config_atomic(path: str | Path, payload: Mapping[str, Any]) -> None:
    config_path = Path(path).expanduser()
    validated = _validate(dict(payload))
    config_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        config_path.parent.chmod(0o700)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{config_path.name}.",
        suffix=".tmp",
        dir=config_path.parent,
        text=True,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            yaml.safe_dump(
                validated,
                handle,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            )
            handle.flush()
            os.fsync(handle.fileno())
        if os.name == "posix":
            temp_path.chmod(0o600)
        os.replace(temp_path, config_path)
        if os.name == "posix":
            config_path.chmod(0o600)
    finally:
        temp_path.unlink(missing_ok=True)
