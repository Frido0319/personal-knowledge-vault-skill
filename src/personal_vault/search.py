from __future__ import annotations

from pathlib import Path
import re
from typing import Any


EXCLUDED_NAMESPACES = {".obsidian", "_raw", "_staging"}
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024


def _title(text: str, fallback: str) -> str:
    match = re.search(r"^#\s+(.+?)\s*$", text, re.MULTILINE)
    return match.group(1).strip() if match else fallback


def _readable_text(text: str) -> str:
    if text.startswith("---\n"):
        closing = text.find("\n---\n", 4)
        if closing >= 0:
            text = text[closing + 5 :]
    text = re.sub(r"\[\[(?:[^\]|]+\|)?([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = text.replace("`", "").replace("**", "").replace("__", "")
    return text


def _snippet(text: str, terms: list[str], *, maximum: int = 320) -> str:
    folded = text.casefold()
    positions = [folded.find(term) for term in terms if folded.find(term) >= 0]
    start = max(0, min(positions, default=0) - 80)
    end = min(len(text), start + maximum)
    snippet = re.sub(r"\s+", " ", text[start:end]).strip()
    if start:
        snippet = "..." + snippet
    if end < len(text):
        snippet += "..."
    return snippet[:maximum]


def search_vault(vault: str | Path, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
    root = Path(vault).expanduser()
    terms = [term.casefold() for term in query.split() if term.strip()]
    if not terms or limit <= 0 or not root.is_dir():
        return []
    results: list[dict[str, Any]] = []
    for path in root.rglob("*.md"):
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if relative.parts and relative.parts[0] in EXCLUDED_NAMESPACES:
            continue
        try:
            if path.stat().st_size > MAX_DOCUMENT_BYTES:
                continue
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        folded = text.casefold()
        if not all(term in folded for term in terms):
            continue
        title = _title(text, path.stem)
        title_folded = title.casefold()
        score = sum(folded.count(term) + title_folded.count(term) * 5 for term in terms)
        readable = _readable_text(text)
        results.append(
            {
                "path": relative.as_posix(),
                "title": title,
                "snippet": _snippet(readable, terms),
                "score": score,
            }
        )
    results.sort(key=lambda item: (-int(item["score"]), str(item["path"]).casefold()))
    return results[: min(limit, 100)]
