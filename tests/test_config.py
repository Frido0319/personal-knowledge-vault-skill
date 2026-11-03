from pathlib import Path
import os

import pytest
import yaml

from personal_vault.config import (
    ConfigError,
    default_config,
    load_config,
    write_config_atomic,
)
from personal_vault.paths import VaultPaths


def test_default_config_is_portable_and_has_no_private_source(tmp_path: Path) -> None:
    paths = VaultPaths.from_roots(tmp_path / "vault", tmp_path / "data")
    payload = default_config(paths=paths, language="zh-CN")

    assert payload["schema_version"] == 1
    assert payload["language"] == "zh-CN"
    assert payload["sources"] == []
    assert payload["skills"] == []
    assert payload["integrations"]["qmd"]["enabled"] is False
    assert payload["integrations"]["restic"]["enabled"] is False
    assert "password" not in yaml.safe_dump(payload).casefold()


def test_config_round_trip_is_atomic_and_owner_only_on_posix(tmp_path: Path) -> None:
    path = tmp_path / "private" / "config.yaml"
    payload = {"schema_version": 1, "language": "en", "sources": []}

    write_config_atomic(path, payload)

    assert load_config(path)["language"] == "en"
    assert not list(path.parent.glob("*.tmp"))
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("language", ["fr", "", None])
def test_config_rejects_unsupported_language(tmp_path: Path, language: object) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.safe_dump({"schema_version": 1, "language": language, "sources": []}),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="LANGUAGE"):
        load_config(path)


def test_config_rejects_unknown_schema(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("schema_version: 99\nlanguage: zh-CN\nsources: []\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="SCHEMA_VERSION"):
        load_config(path)
