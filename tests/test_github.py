from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess

import pytest

from personal_vault.config import load_config, write_config_atomic
from personal_vault.github import (
    GitHubPublishError,
    prepare_private_mirror,
    publish_private_mirror,
)
from personal_vault.paths import VaultPaths
from personal_vault.setup import initialize


@dataclass
class Result:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


class GitRunner:
    def __init__(self, *, visibility: str = "PRIVATE", dirty: bool = True):
        self.visibility = visibility
        self.dirty = dirty
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str], **_: object) -> Result:
        self.calls.append(argv)
        if argv[:3] == ["gh", "repo", "view"]:
            return Result(stdout=self.visibility + "\n")
        if "status" in argv and "--porcelain" in argv:
            return Result(stdout=" M catalog/preflight-manifest.json\n" if self.dirty else "")
        if "rev-parse" in argv:
            return Result(stdout="b" * 40 + "\n")
        return Result()


def _configured(tmp_path: Path) -> VaultPaths:
    paths = VaultPaths.from_roots(tmp_path / "vault", tmp_path / "data")
    initialize(paths=paths, language="zh-CN")
    vault = Path(paths.vault)
    (vault / "knowledge").mkdir()
    (vault / "_staging").mkdir()
    (vault / "_raw").mkdir()
    (vault / "knowledge" / "approved.md").write_text("# Approved\n\nReviewed fact.\n", encoding="utf-8")
    (vault / "_staging" / "pending.md").write_text("# Pending secret\n", encoding="utf-8")
    (vault / "_raw" / "chat.md").write_text("# Raw chat\n", encoding="utf-8")
    config = load_config(Path(paths.config))
    config["integrations"]["github"] = {
        "enabled": True,
        "repository": "example/private-vault",
        "mirror_path": str(Path(paths.data) / "github" / "private-vault"),
        "max_file_bytes": 1_000_000,
    }
    write_config_atomic(Path(paths.config), config)
    return paths


def test_prepare_requires_verified_private_repo_and_excludes_raw_staging(tmp_path: Path) -> None:
    paths = _configured(tmp_path)
    runner = GitRunner()

    result = prepare_private_mirror(Path(paths.config), apply=True, runner=runner)

    mirror = Path(paths.data) / "github" / "private-vault"
    assert result["visibility"] == "PRIVATE"
    assert (mirror / "knowledge" / "approved.md").is_file()
    assert not (mirror / "_staging").exists()
    assert not (mirror / "_raw").exists()
    manifest = json.loads((mirror / "catalog" / "preflight-manifest.json").read_text(encoding="utf-8"))
    assert manifest["repository"] == "example/private-vault"
    assert manifest["files"][0]["sha256"]


@pytest.mark.parametrize("visibility", ["PUBLIC", "INTERNAL", "", "UNKNOWN"])
def test_prepare_fails_closed_for_non_private_or_unknown_visibility(tmp_path: Path, visibility: str) -> None:
    paths = _configured(tmp_path)

    with pytest.raises(GitHubPublishError, match="PRIVATE"):
        prepare_private_mirror(Path(paths.config), apply=True, runner=GitRunner(visibility=visibility))


def test_prepare_dry_run_writes_nothing(tmp_path: Path) -> None:
    paths = _configured(tmp_path)

    result = prepare_private_mirror(Path(paths.config), apply=False, runner=GitRunner())

    assert result["would_copy"] == 1
    assert not (Path(paths.data) / "github").exists()


def test_prepare_rejects_secret_symlink_and_large_file(tmp_path: Path) -> None:
    paths = _configured(tmp_path)
    vault = Path(paths.vault)
    secret = vault / "knowledge" / "secret.md"
    secret.write_text("token " + "gh" + "p_abcdefghijklmnopqrstuvwxyz1234567890AB", encoding="utf-8")
    with pytest.raises(GitHubPublishError, match="SECRET"):
        prepare_private_mirror(Path(paths.config), apply=True, runner=GitRunner())
    secret.unlink()

    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    link = vault / "knowledge" / "outside.md"
    link.symlink_to(outside)
    with pytest.raises(GitHubPublishError, match="SYMLINK"):
        prepare_private_mirror(Path(paths.config), apply=True, runner=GitRunner())
    link.unlink()

    large = vault / "knowledge" / "large.md"
    large.write_text("x" * 1_000_001, encoding="utf-8")
    with pytest.raises(GitHubPublishError, match="TOO_LARGE"):
        prepare_private_mirror(Path(paths.config), apply=True, runner=GitRunner())


def test_publish_requires_exact_confirmation_and_checks_private_after_push(tmp_path: Path) -> None:
    paths = _configured(tmp_path)
    with pytest.raises(GitHubPublishError, match="CONFIRMATION"):
        publish_private_mirror(Path(paths.config), confirmation="yes", runner=GitRunner())

    runner = GitRunner()
    result = publish_private_mirror(
        Path(paths.config),
        confirmation="PUBLISH:example/private-vault",
        runner=runner,
    )

    assert result["visibility"] == "PRIVATE"
    assert result["content_commit"] == "b" * 40
    assert any(call[:2] == ["git", "push"] or "push" in call for call in runner.calls)
    status = json.loads((Path(paths.data) / "state" / "github-status.json").read_text(encoding="utf-8"))
    assert status["visibility"] == "PRIVATE"
    links = json.loads((Path(paths.data) / "state" / "github-canonical-links.json").read_text(encoding="utf-8"))
    assert f"blob/{'b' * 40}/knowledge/approved.md" in links["files"][0]["url"]


def test_publish_fails_when_post_push_visibility_changes(tmp_path: Path) -> None:
    paths = _configured(tmp_path)

    class FlippingRunner(GitRunner):
        def __init__(self):
            super().__init__()
            self.views = 0

        def __call__(self, argv: list[str], **kwargs: object) -> Result:
            if argv[:3] == ["gh", "repo", "view"]:
                self.views += 1
                self.visibility = "PRIVATE" if self.views < 3 else "PUBLIC"
            return super().__call__(argv, **kwargs)

    with pytest.raises(GitHubPublishError, match="POST_PUSH_PRIVATE"):
        publish_private_mirror(
            Path(paths.config),
            confirmation="PUBLISH:example/private-vault",
            runner=FlippingRunner(),
        )


def test_publish_preserves_real_local_git_and_second_run_is_idempotent(tmp_path: Path) -> None:
    paths = _configured(tmp_path)

    class LocalGitRunner:
        def __call__(self, argv: list[str], **kwargs: object) -> Result | subprocess.CompletedProcess[str]:
            if argv[:3] == ["gh", "repo", "view"]:
                return Result(stdout="PRIVATE\n")
            if argv and argv[0] == "git" and "push" in argv:
                return Result()
            return subprocess.run(argv, **kwargs)

    runner = LocalGitRunner()
    first = publish_private_mirror(
        Path(paths.config),
        confirmation="PUBLISH:example/private-vault",
        runner=runner,
    )
    second = publish_private_mirror(
        Path(paths.config),
        confirmation="PUBLISH:example/private-vault",
        runner=runner,
    )

    mirror = Path(paths.data) / "github" / "private-vault"
    assert (mirror / ".git").is_dir()
    assert first["changed"] is True
    assert second["changed"] is False
    assert first["content_commit"] == second["content_commit"]
