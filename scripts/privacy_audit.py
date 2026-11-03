#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re


SKIP_DIRECTORIES = {".git", ".pytest_cache", ".ruff_cache", ".venv", "__pycache__", "build", "dist"}
CREDENTIAL_NAMES = {".env", "id_rsa", "id_ed25519", "credentials", "credentials.json"}
PRIVATE_PATH_PATTERNS = (
    re.compile("/" + r"home/[A-Za-z0-9._-]+/"),
    re.compile("/" + r"Users/[A-Za-z0-9._ -]+/"),
    re.compile(r"[A-Za-z]:\\" + r"Users\\[^\\\r\n]+\\", re.IGNORECASE),
)
SECRET_PATTERNS = (
    re.compile("gh" + r"p_[A-Za-z0-9]{30,}"),
    re.compile("github" + r"_pat_[A-Za-z0-9_]{20,}"),
    re.compile("sk" + r"-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    re.compile("-----BEGIN " + r"(?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)
def _files(root: Path):
    for current, directories, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        kept: list[str] = []
        for name in sorted(directories):
            candidate = current_path / name
            if name in SKIP_DIRECTORIES:
                continue
            if candidate.is_symlink():
                yield candidate
            else:
                kept.append(name)
        directories[:] = kept
        for name in sorted(filenames):
            yield current_path / name


def _credential_filename(path: Path) -> bool:
    folded = path.name.casefold()
    return (
        folded in CREDENTIAL_NAMES
        or (folded.startswith(".env.") and folded != ".env.example")
        or folded.endswith((".pem", ".p12", ".pfx"))
    )


def audit(root: Path) -> dict[str, object]:
    root = root.expanduser().resolve(strict=True)
    findings: list[dict[str, str]] = []
    scanned = 0
    for path in _files(root):
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            findings.append({"code": "PATH_ESCAPE", "path": path.name})
            continue
        if path.is_symlink():
            findings.append({"code": "SYMLINK_NOT_ALLOWED", "path": relative})
            continue
        if not path.is_file():
            continue
        scanned += 1
        if _credential_filename(path):
            findings.append({"code": "CREDENTIAL_FILENAME", "path": relative})
        try:
            raw = path.read_bytes()
        except OSError:
            findings.append({"code": "UNREADABLE_FILE", "path": relative})
            continue
        if len(raw) > 25 * 1024 * 1024:
            findings.append({"code": "FILE_TOO_LARGE", "path": relative})
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            markers = (b"/home/", b"\\Users\\", b"-----BEGIN " + b"PRIVATE KEY-----")
            if any(marker in raw for marker in markers):
                findings.append({"code": "PRIVATE_DATA_IN_BINARY", "path": relative})
            continue
        if any(pattern.search(text) for pattern in PRIVATE_PATH_PATTERNS):
            findings.append({"code": "PRIVATE_ABSOLUTE_PATH", "path": relative})
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            findings.append({"code": "SECRET_PATTERN", "path": relative})
    findings.sort(key=lambda item: (item["path"], item["code"]))
    return {"ok": not findings, "root": str(root), "scanned": scanned, "findings": findings}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail closed on private paths, credentials, secrets, and symlinks.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    arguments = parser.parse_args(argv)
    try:
        report = audit(arguments.root)
    except OSError as exc:
        report = {"ok": False, "root": str(arguments.root), "scanned": 0, "findings": [{"code": type(exc).__name__.upper(), "path": "."}]}
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
