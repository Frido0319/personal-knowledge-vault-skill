from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS generated_pages (
    path TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


class ManifestStore:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute(SCHEMA)
        self.connection.commit()

    def __enter__(self) -> "ManifestStore":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if exc_type is None:
            self.connection.commit()
        else:
            self.connection.rollback()
        self.connection.close()

    def upsert_page(self, path: str, *, source_id: str, content_hash: str) -> None:
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self.connection.execute(
            """
            INSERT INTO generated_pages(path, source_id, content_hash, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                source_id = excluded.source_id,
                content_hash = excluded.content_hash,
                updated_at = excluded.updated_at
            """,
            (path, source_id, content_hash, now),
        )

    def delete_page(self, path: str) -> None:
        self.connection.execute("DELETE FROM generated_pages WHERE path = ?", (path,))


def load_page_records(path: str | Path) -> dict[str, dict[str, Any]]:
    manifest = Path(path).expanduser()
    if not manifest.is_file():
        return {}
    connection = sqlite3.connect(f"file:{manifest}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT path, source_id, content_hash, updated_at FROM generated_pages ORDER BY path"
        ).fetchall()
    except sqlite3.Error:
        return {}
    finally:
        connection.close()
    return {
        str(page): {
            "source_id": str(source_id),
            "content_hash": str(content_hash),
            "updated_at": str(updated_at),
        }
        for page, source_id, content_hash, updated_at in rows
    }

