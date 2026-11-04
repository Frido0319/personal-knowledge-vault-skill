#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
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


def _zip_timestamp(epoch: int) -> tuple[int, int, int, int, int, int]:
    minimum = int(datetime(1980, 1, 1, tzinfo=timezone.utc).timestamp())
    return time.gmtime(max(epoch, minimum))[:6]


def _write_zip(target: Path, records: list[tuple[str, bytes, int]], *, epoch: int) -> None:
    timestamp = _zip_timestamp(epoch)
    names = [name for name, _, _ in records]
    if len(names) != len(set(names)):
        raise BuildError("DUPLICATE_ARCHIVE_PATH")
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content, mode in sorted(records, key=lambda item: item[0]):
            path = Path(name)
            if path.is_absolute() or ".." in path.parts:
                raise BuildError(f"ARCHIVE_PATH_INVALID:{name}")
            info = zipfile.ZipInfo(name, timestamp)
            info.create_system = 3
            info.external_attr = (mode & 0xFFFF) << 16
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, content)


def _project_metadata() -> dict[str, object]:
    payload = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = payload.get("project")
    if not isinstance(project, dict):
        raise BuildError("PROJECT_METADATA_REQUIRED")
    return project


def _metadata_document(project: dict[str, object]) -> bytes:
    name = str(project["name"])
    version = str(project["version"])
    lines = [
        "Metadata-Version: 2.1",
        f"Name: {name}",
        f"Version: {version}",
        f"Summary: {project['description']}",
    ]
    authors = project.get("authors", [])
    if isinstance(authors, list):
        for author in authors:
            if isinstance(author, dict) and author.get("name"):
                lines.append(f"Author: {author['name']}")
    license_value = project.get("license")
    if isinstance(license_value, dict) and license_value.get("text"):
        lines.append(f"License: {license_value['text']}")
    urls = project.get("urls", {})
    if isinstance(urls, dict):
        for label, url in urls.items():
            lines.append(f"Project-URL: {label}, {url}")
    keywords = project.get("keywords", [])
    if isinstance(keywords, list) and keywords:
        lines.append("Keywords: " + ",".join(str(item) for item in keywords))
    classifiers = project.get("classifiers", [])
    if isinstance(classifiers, list):
        lines.extend(f"Classifier: {item}" for item in classifiers)
    lines.append(f"Requires-Python: {project['requires-python']}")
    lines.append("Description-Content-Type: text/markdown")
    if (ROOT / "LICENSE").is_file():
        lines.append("License-File: LICENSE")
    dependencies = project.get("dependencies", [])
    if isinstance(dependencies, list):
        lines.extend(f"Requires-Dist: {dependency}" for dependency in dependencies)
    extras = project.get("optional-dependencies", {})
    if isinstance(extras, dict):
        for extra in sorted(extras):
            lines.append(f"Provides-Extra: {extra}")
            requirements = extras[extra]
            if isinstance(requirements, list):
                lines.extend(
                    f"Requires-Dist: {requirement}; extra == '{extra}'"
                    for requirement in requirements
                )
    readme = project.get("readme")
    if not isinstance(readme, str):
        raise BuildError("STRING_README_REQUIRED")
    description = (ROOT / readme).read_text(encoding="utf-8").rstrip("\n")
    return ("\n".join(lines) + "\n\n" + description + "\n").encode("utf-8")


def _record_hash(content: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=")
    return digest.decode("ascii")


def _build_wheel(destination: Path, epoch: int, version: str) -> Path:
    project = _project_metadata()
    if str(project.get("version")) != version:
        raise BuildError("PROJECT_VERSION_MISMATCH")
    distribution = str(project["name"]).replace("-", "_")
    package_root = ROOT / "src" / "personal_vault"
    records: list[tuple[str, bytes, int]] = []
    for path in sorted(package_root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_dir():
            continue
        relative = path.relative_to(ROOT / "src")
        if "__pycache__" in relative.parts or relative.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_symlink():
            raise BuildError(f"WHEEL_SYMLINK_NOT_ALLOWED:{relative.as_posix()}")
        records.append((relative.as_posix(), path.read_bytes(), 0o644))
    if not records:
        raise BuildError("RUNTIME_PACKAGE_REQUIRED")

    dist_info = f"{distribution}-{version}.dist-info"
    records.extend(
        (
            (f"{dist_info}/METADATA", _metadata_document(project), 0o644),
            (
                f"{dist_info}/WHEEL",
                (
                    "Wheel-Version: 1.0\n"
                    "Generator: personal-knowledge-vault deterministic builder\n"
                    "Root-Is-Purelib: true\n"
                    "Tag: py3-none-any\n"
                ).encode("utf-8"),
                0o644,
            ),
            (
                f"{dist_info}/entry_points.txt",
                (
                    "[console_scripts]\n"
                    + "".join(
                        f"{command} = {target}\n"
                        for command, target in sorted(dict(project.get("scripts", {})).items())
                    )
                ).encode("utf-8"),
                0o644,
            ),
            (f"{dist_info}/top_level.txt", b"personal_vault\n", 0o644),
        )
    )
    license_file = ROOT / "LICENSE"
    if license_file.is_file():
        records.append((f"{dist_info}/LICENSE", license_file.read_bytes(), 0o644))
    record_path = f"{dist_info}/RECORD"
    record_content = "".join(
        f"{name},sha256={_record_hash(content)},{len(content)}\n"
        for name, content, _ in sorted(records, key=lambda item: item[0])
    )
    record_content += f"{record_path},,\n"
    records.append((record_path, record_content.encode("utf-8"), 0o644))

    target = destination / f"{distribution}-{version}-py3-none-any.whl"
    _write_zip(target, records, epoch=epoch)
    return target


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
    _write_zip(target, records, epoch=epoch)


def build_release(output: Path, *, allow_dirty: bool) -> dict[str, object]:
    commit, epoch = _source_identity(allow_dirty=allow_dirty)
    version = _version()
    output = output.expanduser().resolve(strict=False)
    output.mkdir(parents=True, exist_ok=True)
    for stale in (*output.glob("personal_knowledge_vault-*.whl"), *output.glob(f"{SKILL_NAME}-*.skill")):
        stale.unlink()
    (output / "SHA256SUMS").unlink(missing_ok=True)
    wheel = _build_wheel(output, epoch, version)
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
