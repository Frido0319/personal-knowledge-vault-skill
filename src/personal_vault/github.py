from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Callable, Mapping

from .config import load_config
from .proposals import _atomic_text
from .search import EXCLUDED_NAMESPACES
from .security import find_secret_matches, is_forbidden_relative_path


class GitHubPublishError(RuntimeError):
    """Raised when a private mirror cannot be proven safe."""


Runner = Callable[..., Any]
_REPOSITORY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_OBSIDIAN_ALLOWED = {"app.json", "appearance.json", "core-plugins.json", "graph.json"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _settings(config: Mapping[str, Any]) -> dict[str, Any]:
    integration = config.get("integrations", {}).get("github", {})
    if not isinstance(integration, dict) or integration.get("enabled") is not True:
        raise GitHubPublishError("GITHUB_DISABLED")
    repository = str(integration.get("repository", ""))
    if not _REPOSITORY.fullmatch(repository) or ".." in repository:
        raise GitHubPublishError("GITHUB_REPOSITORY_INVALID")
    return dict(integration)


def _run(runner: Runner, argv: list[str], *, cwd: Path | None = None, check: bool = True) -> Any:
    result = runner(argv, cwd=str(cwd) if cwd else None, check=False, capture_output=True, text=True)
    if check and int(getattr(result, "returncode", 1)) != 0:
        raise GitHubPublishError("COMMAND_FAILED")
    return result


def _verify_private(repository: str, runner: Runner, *, post_push: bool = False) -> str:
    result = _run(
        runner,
        ["gh", "repo", "view", repository, "--json", "visibility", "--jq", ".visibility"],
    )
    visibility = str(getattr(result, "stdout", "")).strip().upper()
    if visibility != "PRIVATE":
        code = "POST_PUSH_PRIVATE_VERIFICATION_FAILED" if post_push else "PRIVATE_REPOSITORY_REQUIRED"
        raise GitHubPublishError(code)
    return visibility


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _allowed_files(vault: Path, *, max_bytes: int) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    if not vault.is_dir():
        return files
    for path in sorted(vault.rglob("*"), key=lambda item: item.as_posix().casefold()):
        try:
            relative = path.relative_to(vault)
        except ValueError:
            continue
        if relative.parts and relative.parts[0] in {"_raw", "_staging"}:
            continue
        if path.is_symlink():
            raise GitHubPublishError(f"SYMLINK_NOT_ALLOWED:{relative.as_posix()}")
        if not path.is_file():
            continue
        allowed = path.suffix.casefold() in {".md", ".canvas", ".base"}
        if relative.parts and relative.parts[0] == ".obsidian":
            allowed = len(relative.parts) == 2 and relative.name in _OBSIDIAN_ALLOWED
        if not allowed:
            continue
        if is_forbidden_relative_path(relative):
            raise GitHubPublishError(f"FORBIDDEN_PATH:{relative.as_posix()}")
        size = path.stat().st_size
        if size > max_bytes:
            raise GitHubPublishError(f"FILE_TOO_LARGE:{relative.as_posix()}")
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeError as exc:
            raise GitHubPublishError(f"NON_UTF8_TEXT:{relative.as_posix()}") from exc
        if find_secret_matches(text):
            raise GitHubPublishError(f"SECRET_DETECTED:{relative.as_posix()}")
        files.append({"path": relative.as_posix(), "sha256": _sha256(path), "size": size, "source": path})
    return files


def _mirror_path(config: Mapping[str, Any], settings: Mapping[str, Any]) -> Path:
    configured = str(settings.get("mirror_path", "")).strip()
    if configured:
        return Path(configured).expanduser()
    repository = str(settings["repository"]).split("/", 1)[1]
    return Path(str(config["data"])).expanduser() / "github" / repository


def _manifest(repository: str, files: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "repository": repository,
        "visibility_required": "PRIVATE",
        "files": [{key: record[key] for key in ("path", "sha256", "size")} for record in files],
    }


def _swap_mirror(mirror: Path, staging: Path) -> None:
    backup = mirror.with_name(mirror.name + ".previous")
    shutil.rmtree(backup, ignore_errors=True)
    had_mirror = mirror.exists()
    if had_mirror:
        mirror.replace(backup)
    try:
        if (backup / ".git").is_dir():
            (backup / ".git").replace(staging / ".git")
        staging.replace(mirror)
    except Exception:
        if (staging / ".git").is_dir() and backup.is_dir():
            (staging / ".git").replace(backup / ".git")
        if had_mirror and backup.exists() and not mirror.exists():
            backup.replace(mirror)
        raise
    shutil.rmtree(backup, ignore_errors=True)


def prepare_private_mirror(
    config_path: str | Path,
    *,
    apply: bool = False,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    config = load_config(config_path)
    settings = _settings(config)
    repository = str(settings["repository"])
    visibility = _verify_private(repository, runner)
    max_bytes = int(settings.get("max_file_bytes", 10 * 1024 * 1024))
    if max_bytes < 1:
        raise GitHubPublishError("MAX_FILE_BYTES_INVALID")
    vault = Path(str(config["vault"])).expanduser()
    files = _allowed_files(vault, max_bytes=max_bytes)
    mirror = _mirror_path(config, settings)
    result = {
        "applied": False,
        "repository": repository,
        "visibility": visibility,
        "mirror_path": str(mirror),
        "would_copy": len(files),
        "files": len(files),
    }
    if not apply:
        return result
    staging = mirror.with_name(mirror.name + ".prepare")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, mode=0o700)
    for record in files:
        target = staging / str(record["path"])
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copy2(record["source"], target)
    manifest_path = staging / "catalog" / "preflight-manifest.json"
    _atomic_text(manifest_path, json.dumps(_manifest(repository, files), ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    _swap_mirror(mirror, staging)
    result["applied"] = True
    return result


def publish_private_mirror(
    config_path: str | Path,
    *,
    confirmation: str,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    config = load_config(config_path)
    settings = _settings(config)
    repository = str(settings["repository"])
    if confirmation != f"PUBLISH:{repository}":
        raise GitHubPublishError("PUBLISH_CONFIRMATION_REQUIRED")
    prepared = prepare_private_mirror(config_path, apply=True, runner=runner)
    _verify_private(repository, runner)
    mirror = Path(str(prepared["mirror_path"]))
    if not (mirror / ".git").is_dir():
        _run(runner, ["git", "init", "-b", "main"], cwd=mirror)
    _run(runner, ["git", "remote", "remove", "origin"], cwd=mirror, check=False)
    _run(runner, ["git", "remote", "add", "origin", f"https://github.com/{repository}.git"], cwd=mirror)
    _run(runner, ["git", "add", "--all"], cwd=mirror)
    status = _run(runner, ["git", "status", "--porcelain"], cwd=mirror)
    changed = bool(str(getattr(status, "stdout", "")).strip())
    if changed:
        _run(
            runner,
            [
                "git",
                "-c",
                "user.name=Personal Knowledge Vault",
                "-c",
                "user.email=personal-vault@users.noreply.github.com",
                "commit",
                "-m",
                "chore: update private knowledge vault",
            ],
            cwd=mirror,
        )
    commit_result = _run(runner, ["git", "rev-parse", "HEAD"], cwd=mirror)
    content_commit = str(getattr(commit_result, "stdout", "")).strip().casefold()
    if not _COMMIT.fullmatch(content_commit):
        raise GitHubPublishError("CONTENT_COMMIT_INVALID")
    if changed:
        _run(runner, ["git", "push", "--set-upstream", "origin", "main"], cwd=mirror)
    visibility = _verify_private(repository, runner, post_push=True)
    data = Path(str(config["data"])).expanduser()
    manifest = json.loads((mirror / "catalog" / "preflight-manifest.json").read_text(encoding="utf-8"))
    links = {
        "schema_version": 1,
        "repository": repository,
        "content_commit": content_commit,
        "files": [
            {
                "path": record["path"],
                "sha256": record["sha256"],
                "url": f"https://github.com/{repository}/blob/{content_commit}/{record['path']}",
            }
            for record in manifest["files"]
        ],
    }
    _atomic_text(data / "state" / "github-canonical-links.json", json.dumps(links, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    result = {
        "at": _now(),
        "status": "ok",
        "repository": repository,
        "visibility": visibility,
        "content_commit": content_commit,
        "changed": changed,
        "files": len(manifest["files"]),
    }
    _atomic_text(data / "state" / "github-status.json", json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    return result

