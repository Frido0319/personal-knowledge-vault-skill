from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from .security import is_forbidden_relative_path, redact_text


EXCLUDED_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    ".venv",
    "__pycache__",
    "backups",
    "build",
    "cache",
    "caches",
    "dist",
    "node_modules",
    "target",
    "tmp",
}
TEXT_SUFFIXES = {".md", ".txt", ".rst", ".adoc"}
SUMMARY_NAMES = ("README.md", "README.MD", "README", "SKILL.md", "notes.md")
MAX_FILES = 20_000
MAX_SUMMARY_BYTES = 1_000_000


@dataclass(frozen=True, slots=True)
class FileRecord:
    relative_path: str
    sha256: str
    size: int


@dataclass(frozen=True, slots=True)
class ItemRecord:
    item_id: str
    title: str
    relative_path: str
    summary: str
    file_count: int
    total_bytes: int
    content_hash: str
    files: tuple[FileRecord, ...]


@dataclass(frozen=True, slots=True)
class SourceInventory:
    source_id: str
    kind: str
    root: str
    items: tuple[ItemRecord, ...]
    excluded: int
    errors: tuple[str, ...]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_id(title: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", title).strip(".-_")
    if cleaned:
        return cleaned[:96]
    return hashlib.sha256(title.encode("utf-8")).hexdigest()[:16]


def _is_excluded(relative: Path) -> bool:
    return any(part.casefold() in EXCLUDED_NAMES for part in relative.parts) or is_forbidden_relative_path(relative)


def _walk_item(item_root: Path) -> tuple[list[FileRecord], int, list[str]]:
    records: list[FileRecord] = []
    excluded = 0
    errors: list[str] = []
    if item_root.is_file():
        try:
            return [FileRecord(item_root.name, _sha256(item_root), item_root.stat().st_size)], 0, []
        except OSError as exc:
            return [], 0, [f"{item_root.name}:{type(exc).__name__}"]

    for current, directory_names, file_names in os.walk(item_root, followlinks=False):
        current_path = Path(current)
        kept_directories: list[str] = []
        for name in sorted(directory_names):
            candidate = current_path / name
            relative = candidate.relative_to(item_root)
            if candidate.is_symlink() or _is_excluded(relative):
                excluded += 1
            else:
                kept_directories.append(name)
        directory_names[:] = kept_directories
        for name in sorted(file_names):
            path = current_path / name
            relative = path.relative_to(item_root)
            if path.is_symlink() or _is_excluded(relative):
                excluded += 1
                continue
            if len(records) >= MAX_FILES:
                errors.append("MAX_FILES_EXCEEDED")
                return records, excluded, errors
            try:
                records.append(
                    FileRecord(
                        relative_path=relative.as_posix(),
                        sha256=_sha256(path),
                        size=path.stat().st_size,
                    )
                )
            except OSError as exc:
                errors.append(f"{relative.as_posix()}:{type(exc).__name__}")
    return sorted(records, key=lambda item: item.relative_path.casefold()), excluded, errors


def _summary_candidates(item_root: Path, records: Iterable[FileRecord]) -> Iterable[Path]:
    by_name = {record.relative_path.casefold(): record.relative_path for record in records}
    for preferred in SUMMARY_NAMES:
        match = by_name.get(preferred.casefold())
        if match:
            yield item_root / match if item_root.is_dir() else item_root
    for record in records:
        if Path(record.relative_path).suffix.casefold() in TEXT_SUFFIXES:
            yield item_root / record.relative_path if item_root.is_dir() else item_root


def _extract_summary(item_root: Path, records: Iterable[FileRecord]) -> str:
    seen: set[Path] = set()
    for candidate in _summary_candidates(item_root, records):
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            if candidate.stat().st_size > MAX_SUMMARY_BYTES:
                continue
            text = candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        lines: list[str] = []
        in_frontmatter = text.startswith("---\n")
        for raw in text.splitlines():
            stripped = raw.strip()
            if in_frontmatter:
                if stripped == "---" and lines:
                    in_frontmatter = False
                elif stripped == "---" and not lines:
                    lines.append("__frontmatter_start__")
                continue
            if not stripped or stripped.startswith(("#", "```", "<!--")):
                continue
            lines.append(stripped)
            if len(lines) >= 3:
                break
        lines = [line for line in lines if line != "__frontmatter_start__"]
        if lines:
            return redact_text(" ".join(lines))[:800]
    return ""


def _item(item_root: Path, *, title: str, relative_path: str) -> tuple[ItemRecord, int, list[str]]:
    records, excluded, errors = _walk_item(item_root)
    digest = hashlib.sha256()
    for record in records:
        digest.update(record.relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(record.sha256.encode("ascii"))
        digest.update(b"\0")
    return (
        ItemRecord(
            item_id=_safe_id(title),
            title=title,
            relative_path=relative_path,
            summary=_extract_summary(item_root, records),
            file_count=len(records),
            total_bytes=sum(record.size for record in records),
            content_hash=digest.hexdigest(),
            files=tuple(records),
        ),
        excluded,
        errors,
    )


def scan_source(source: Mapping[str, Any]) -> SourceInventory:
    source_id = str(source.get("id", "")).strip()
    kind = str(source.get("kind", "")).strip()
    root = Path(str(source.get("path", ""))).expanduser().resolve(strict=False)
    if not source_id or not kind or not root.exists():
        raise ValueError("INVALID_SOURCE")

    if root.is_file():
        candidates = [(root.name, root, root.name)]
    elif kind == "skill" and (root / "SKILL.md").is_file():
        candidates = [(root.name, root, ".")]
    else:
        candidates = []
        for child in sorted(root.iterdir(), key=lambda path: path.name.casefold()):
            if child.is_symlink() or _is_excluded(Path(child.name)):
                continue
            candidates.append((child.name, child, child.name))

    items: list[ItemRecord] = []
    excluded = 0
    errors: list[str] = []
    for title, item_root, relative in candidates:
        record, item_excluded, item_errors = _item(item_root, title=title, relative_path=relative)
        items.append(record)
        excluded += item_excluded
        errors.extend(f"{title}/{error}" for error in item_errors)
    return SourceInventory(
        source_id=source_id,
        kind=kind,
        root=str(root),
        items=tuple(items),
        excluded=excluded,
        errors=tuple(errors),
    )

