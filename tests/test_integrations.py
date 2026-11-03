from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path

import pytest

from personal_vault.config import load_config, write_config_atomic
from personal_vault.integrations import IntegrationError, run_qmd_update, run_restic_backup
from personal_vault.paths import VaultPaths
from personal_vault.setup import initialize


@dataclass
class Result:
    returncode: int = 0
    stdout: str = "{}"
    stderr: str = ""


class Runner:
    def __init__(self, results: list[Result] | None = None):
        self.calls: list[tuple[list[str], dict[str, object]]] = []
        self.results = list(results or [])

    def __call__(self, argv: list[str], **kwargs: object) -> Result:
        self.calls.append((argv, kwargs))
        return self.results.pop(0) if self.results else Result()


def _executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def _configured(tmp_path: Path) -> tuple[VaultPaths, dict[str, object]]:
    paths = VaultPaths.from_roots(tmp_path / "vault", tmp_path / "data")
    initialize(paths=paths, language="zh-CN")
    vault = Path(paths.vault)
    (vault / "knowledge").mkdir()
    (vault / "_staging").mkdir()
    (vault / "_raw").mkdir()
    (vault / "knowledge" / "formal.md").write_text("# Formal\n", encoding="utf-8")
    (vault / "_staging" / "pending.md").write_text("# Pending\n", encoding="utf-8")
    (vault / "_raw" / "chat.md").write_text("# Raw\n", encoding="utf-8")
    return paths, load_config(Path(paths.config))


def test_qmd_preview_runs_nothing_and_apply_indexes_only_formal_publish_tree(tmp_path: Path) -> None:
    paths, config = _configured(tmp_path)
    qmd = _executable(tmp_path / "bin" / "qmd")
    config["integrations"]["qmd"].update({"enabled": True, "executable": str(qmd), "embed": False})
    write_config_atomic(Path(paths.config), config)
    runner = Runner()

    preview = run_qmd_update(Path(paths.config), apply=False, runner=runner)
    applied = run_qmd_update(Path(paths.config), apply=True, runner=runner)

    publish = Path(paths.data) / "qmd" / "publish"
    assert preview["applied"] is False
    assert len(runner.calls) >= 2
    assert (publish / "knowledge" / "formal.md").is_file()
    assert not (publish / "_staging").exists()
    assert not (publish / "_raw").exists()
    assert all(isinstance(call[0], list) for call in runner.calls)
    assert str(Path(paths.vault)) not in " ".join(" ".join(call[0]) for call in runner.calls)
    assert applied["documents"] == 1


def test_qmd_rejects_arbitrary_executable_even_when_enabled(tmp_path: Path) -> None:
    paths, config = _configured(tmp_path)
    evil = _executable(tmp_path / "bin" / "bash")
    config["integrations"]["qmd"].update({"enabled": True, "executable": str(evil)})
    write_config_atomic(Path(paths.config), config)

    with pytest.raises(IntegrationError, match="EXECUTABLE"):
        run_qmd_update(Path(paths.config), apply=True, runner=Runner())


def test_qmd_failure_restores_previous_publish_tree(tmp_path: Path) -> None:
    paths, config = _configured(tmp_path)
    qmd = _executable(tmp_path / "bin" / "qmd")
    config["integrations"]["qmd"].update({"enabled": True, "executable": str(qmd), "embed": False})
    write_config_atomic(Path(paths.config), config)
    publish = Path(paths.data) / "qmd" / "publish"
    publish.mkdir(parents=True)
    (publish / "old.md").write_text("old stable index input", encoding="utf-8")

    with pytest.raises(IntegrationError, match="QMD_COMMAND_FAILED"):
        run_qmd_update(Path(paths.config), apply=True, runner=Runner([Result(returncode=2, stderr="failed")]))

    assert (publish / "old.md").is_file()
    assert not (publish / "knowledge" / "formal.md").exists()


def test_restic_password_never_comes_from_config_or_status(tmp_path: Path, monkeypatch) -> None:
    paths, config = _configured(tmp_path)
    restic = _executable(tmp_path / "bin" / "restic")
    config["integrations"]["restic"].update(
        {"enabled": True, "executable": str(restic), "repository": str(tmp_path / "repo")}
    )
    write_config_atomic(Path(paths.config), config)
    monkeypatch.setenv("RESTIC_PASSWORD", "test-only-password")
    runner = Runner([Result(stdout=json.dumps({"snapshot_id": "abc123"}))])

    result = run_restic_backup(Path(paths.config), apply=True, runner=runner)

    serialized = json.dumps(result)
    state = (Path(paths.data) / "state" / "backup-status.json").read_text(encoding="utf-8")
    assert "test-only-password" not in serialized
    assert "test-only-password" not in state
    assert runner.calls[0][0][0] == str(restic)
    assert "--json" in runner.calls[0][0]


def test_restic_apply_requires_password_environment(tmp_path: Path, monkeypatch) -> None:
    paths, config = _configured(tmp_path)
    restic = _executable(tmp_path / "bin" / "restic")
    config["integrations"]["restic"].update(
        {"enabled": True, "executable": str(restic), "repository": str(tmp_path / "repo")}
    )
    write_config_atomic(Path(paths.config), config)
    monkeypatch.delenv("RESTIC_PASSWORD", raising=False)
    monkeypatch.delenv("RESTIC_PASSWORD_FILE", raising=False)
    monkeypatch.delenv("RESTIC_PASSWORD_COMMAND", raising=False)

    with pytest.raises(IntegrationError, match="PASSWORD_ENV_REQUIRED"):
        run_restic_backup(Path(paths.config), apply=True, runner=Runner())


def test_disabled_integrations_fail_closed(tmp_path: Path) -> None:
    paths, _ = _configured(tmp_path)

    with pytest.raises(IntegrationError, match="QMD_DISABLED"):
        run_qmd_update(Path(paths.config), apply=True, runner=Runner())
    with pytest.raises(IntegrationError, match="RESTIC_DISABLED"):
        run_restic_backup(Path(paths.config), apply=True, runner=Runner())

