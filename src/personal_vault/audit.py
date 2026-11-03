from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Mapping

from .security import redact_text


_OMITTED_KEYS = {
    "body",
    "content",
    "cookie",
    "message",
    "message_body",
    "password",
    "private_key",
    "secret",
    "text",
    "token",
}


def _safe_value(key: str, value: Any) -> Any:
    key_folded = key.casefold()
    if key_folded in _OMITTED_KEYS or any(marker in key_folded for marker in ("password", "secret", "token", "cookie")):
        return "[OMITTED]"
    if isinstance(value, Mapping):
        return {str(child): _safe_value(str(child), child_value) for child, child_value in value.items()}
    if isinstance(value, list):
        return [_safe_value(key, item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


class AuditLogger:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()

    def append(
        self,
        event: str,
        *,
        source_id: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        payload = {
            "at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "event": event,
            "source_id": source_id,
            "details": _safe_value("details", dict(details or {})),
        }
        line = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ": ")) + "\n"
        descriptor = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            os.write(descriptor, line.encode("utf-8"))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        if os.name == "posix":
            self.path.chmod(0o600)

