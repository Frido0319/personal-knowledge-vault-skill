from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re


class SecurityBoundaryError(ValueError):
    """Raised when a requested source violates a privacy boundary."""


@dataclass(frozen=True, slots=True)
class SecretMatch:
    kind: str
    start: int
    end: int


_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("openai_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("bearer_token", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{20,}")),
    ("email", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)),
    ("phone", re.compile(r"(?<!\d)(?:\+?86[ -]?)?1[3-9]\d{9}(?!\d)")),
)

_FORBIDDEN_COMPONENTS = {
    ".ssh",
    ".gnupg",
    ".aws",
    ".azure",
    ".kube",
    "wallet",
    "wallets",
    "cookies",
    "login data",
    "credential store",
    "credentials",
    "passwords",
}


def _portable_parts(value: str | Path) -> tuple[str, ...]:
    normalized = str(value).replace("\\", "/").strip("/")
    return tuple(part.casefold() for part in PurePosixPath(normalized).parts)


def is_forbidden_relative_path(value: str | Path) -> bool:
    parts = _portable_parts(value)
    return any(
        part == ".env"
        or part.startswith(".env.")
        or part in _FORBIDDEN_COMPONENTS
        for part in parts
    )


def find_secret_matches(text: str) -> list[SecretMatch]:
    found: list[SecretMatch] = []
    for kind, pattern in _PATTERNS:
        found.extend(SecretMatch(kind=kind, start=match.start(), end=match.end()) for match in pattern.finditer(text))
    return sorted(found, key=lambda item: (item.start, item.end, item.kind))


def redact_text(text: str) -> str:
    matches = find_secret_matches(text)
    if not matches:
        return text
    output: list[str] = []
    cursor = 0
    for match in matches:
        if match.start < cursor:
            continue
        output.append(text[cursor : match.start])
        output.append(f"[REDACTED:{match.kind}]")
        cursor = match.end
    output.append(text[cursor:])
    return "".join(output)


def validate_authorized_root(root: str | Path, *, home: str | Path | None = None) -> Path:
    source = Path(root).expanduser()
    if source.is_symlink():
        raise SecurityBoundaryError("SYMLINK_ROOT_NOT_ALLOWED")
    resolved = source.resolve(strict=False)
    filesystem_root = Path(resolved.anchor)
    if resolved == filesystem_root:
        raise SecurityBoundaryError("ROOT_TOO_BROAD")
    if home is not None and resolved == Path(home).expanduser().resolve(strict=False):
        raise SecurityBoundaryError("ROOT_TOO_BROAD")
    if not resolved.is_dir():
        raise SecurityBoundaryError("SOURCE_ROOT_NOT_DIRECTORY")
    return resolved

