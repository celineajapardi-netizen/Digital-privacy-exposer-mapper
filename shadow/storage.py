"""
Saved scenarios in a small SQLite database.

A scenario is just a name plus the list of information keys that were public,
so the user can save "before" and "after" and compare them later. Nothing
personal is stored: only which *kinds* of information were shared.

SQLite is part of Python's standard library, so there is nothing to install.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "shadow.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS scenarios (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    items      TEXT NOT NULL,        -- JSON list of catalogue keys
    score      INTEGER NOT NULL,
    level      TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class ScenarioStore:
    def __init__(self, path: Path | str = DEFAULT_DB) -> None:
        self.path = str(path)
        try:
            with self._connect() as conn:
                conn.executescript(SCHEMA)
        except sqlite3.OperationalError:
            # Some hosts (e.g. Vercel) make the project folder read-only.
            # Fall back to the system temp folder so the app still runs;
            # saved scenarios simply will not survive a restart there.
            self.path = str(Path(tempfile.gettempdir()) / "shadow.db")
            with self._connect() as conn:
                conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row   # rows behave like dicts
        return conn

    def save(self, name: str, items: list[str], score: int, level: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO scenarios (name, items, score, level, created_at) VALUES (?, ?, ?, ?, ?)",
                (name.strip() or "Untitled", json.dumps(sorted(items)), score, level,
                 datetime.now(timezone.utc).isoformat(timespec="seconds")),
            )
            return int(cur.lastrowid)

    def list(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM scenarios ORDER BY id DESC").fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get(self, scenario_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM scenarios WHERE id = ?", (scenario_id,)).fetchone()
        return None if row is None else self._row_to_dict(row)

    def delete(self, scenario_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM scenarios WHERE id = ?", (scenario_id,))
            return cur.rowcount > 0

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "items": json.loads(row["items"]),
            "score": row["score"],
            "level": row["level"],
            "created_at": row["created_at"],
        }
