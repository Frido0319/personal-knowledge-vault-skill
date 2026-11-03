#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = "build-personal-knowledge-vault"
SKILL_ROOT = ROOT / "skills" / SKILL_NAME


class BuildError(RuntimeError):
    pass


def _run(argv: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise BuildError(f"COMMAND_FAILED:{Path(argv[0]).name}:{result.stderr[-1000:]}")
    return result.stdout.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_identity(*, allow_dirty: bool) -> tuple[str, int]:
    commit = _run(["git", "rev-parse", "HEAD"])
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit.casefold()):
        raise BuildError("SOURCE_COMMIT_INVALID")
    dirty = _run(["git", "status", "--porcelain", "--untracked-files=all"])
    if dirty and not allow_dirty:
        raise BuildError("CLEAN_WORKTREE_REQUIRED")
    epoch_raw = _run(["git", "show", "-s", "--format=%ct", commit])
    try:
        epoch = int(epoch_raw)
    except ValueError as exc:
        raise BuildError("SOURCE_DATE_EPOCH_INVALID") from exc
    return commit.casefold(), epoch


def _version() -> str:
    payload = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    value = str(payload["project"]["version"])
    if not value or any(character not in "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.-" for character in value):
        raise BuildError("VERSION_INVALID")
    return value


def _build_wheel(destination: Path, epoch: int) -> Path:
    environment = os.environ.copy()
    environment.update({"SOURCE_DATE_EPOCH": str(epoch), "PYTHONHASHSEED": "0"})
    with tempfile.TemporaryDirectory(prefix="personal-vault-wheel-") as temporary:
        wheel_dir = Path(temporary)
        _run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                "--no-build-isolation",
                "--disable-pip-version-check",
                "--wheel-dir",
                str(wheel_dir),
                str(ROOT),
            ],
            env=environment,
        )
        wheels = sorted(wheel_dir.glob("personal_knowledge_vault-*.whl"))
        if len(wheels) != 1:
            raise BuildError("ONE_RUNTIME_WHEEL_REQUIRED")
        target = destination / wheels[0].name
        shutil.copyfile(wheels[0], target)
    return target


def _zip_timestamp(epoch: int) -> tuple[int, int, int, int, int, int]:
    minimum = int(datetime(1980, 1, 1, tzinfo=timezone.utc).timestamp())
    return time.gmtime(max(epoch, minimum))[:6]


def _skill_files() -> list[tuple[str, bytes, int]]:
    records: list[tuple[str, bytes, int]] = []
    for path in sorted(SKILL_ROOT.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_dir():
            continue
        relative = path.relative_to(SKILL_ROOT)
        if "__pycache__" in relative.parts or relative.suffix in {".pyc", ".pyo"}:
            continue
        if relative.parts[:2] == ("assets", "runtime"):
            continue
        if path.is_symlink():
            raise BuildError(f"SKILL_SYMLINK_NOT_ALLOWED:{relative.as_posix()}")
        mode = 0o755 if relative.parts and relative.parts[0] == "scripts" else 0o644
        records.append((f"{SKILL_NAME}/{relative.as_posix()}", path.read_bytes(), mode))
    return records


def _write_skill(
    target: Path,
    *,
    wheel: Path,
    commit: str,
    epoch: int,
    version: str,
) -> None:
    wheel_hash = _sha256(wheel)
    prefix = f"{SKILL_NAME}/assets/runtime"
    metadata = {
        "schema_version": 1,
        "source_commit": commit,
        "source_date_epoch": epoch,
        "version": version,
        "wheel": wheel.name,
        "wheel_sha256": wheel_hash,
    }
    records = _skill_files()
    records.extend(
        (
            (f"{prefix}/{wheel.name}", wheel.read_bytes(), 0o644),
            (f"{prefix}/SHA256SUMS", f"{wheel_hash}  {wheel.name}\n".encode("utf-8"), 0o644),
            (
                f"{prefix}/BUILD-METADATA.json",
                (json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"),
                0o644,
            ),
        )
    )
    timestamp = _zip_timestamp(epoch)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, content, mode in sorted(records, key=lambda item: item[0]):
            info = zipfile.ZipInfo(name, timestamp)
            info.create_system = 3
            info.external_attr = (mode & 0xFFFF) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def build_release(output: Path, *, allow_dirty: bool) -> dict[str, object]:
    commit, epoch = _source_identity(allow_dirty=allow_dirty)
    version = _version()
    output = output.expanduser().resolve(strict=False)
    output.mkdir(parents=True, exist_ok=True)
    for stale in (*output.glob("personal_knowledge_vault-*.whl"), *output.glob(f"{SKILL_NAME}-*.skill")):
        stale.unlink()
    (output / "SHA256SUMS").unlink(missing_ok=True)
    wheel = _build_wheel(output, epoch)
    skill = output / f"{SKILL_NAME}-{version}.skill"
    _write_skill(skill, wheel=wheel, commit=commit, epoch=epoch, version=version)
    artifacts = sorted((wheel, skill), key=lambda path: path.name)
    sums = "".join(f"{_sha256(path)}  {path.name}\n" for path in artifacts)
    (output / "SHA256SUMS").write_text(sums, encoding="utf-8", newline="\n")
    return {
        "source_commit": commit,
        "source_date_epoch": epoch,
        "version": version,
        "artifacts": [path.name for path in artifacts],
        "output": str(output),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build deterministic wheel and Skill release artifacts.")
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    parser.add_argument("--allow-dirty", action="store_true", help="Development only; releases require a clean tree.")
    arguments = parser.parse_args(argv)
    try:
        report = build_release(arguments.output, allow_dirty=arguments.allow_dirty)
    except (BuildError, OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
