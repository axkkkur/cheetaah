from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

from app.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS meetings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    audio_path TEXT,
    transcript TEXT,
    summary TEXT,
    status TEXT NOT NULL,
    error TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id INTEGER NOT NULL,
    topic TEXT,
    decision TEXT,
    quote TEXT,
    speaker TEXT,
    decided_at TEXT NOT NULL,
    FOREIGN KEY (meeting_id) REFERENCES meetings(id)
);

CREATE TABLE IF NOT EXISTS action_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id INTEGER NOT NULL,
    title TEXT,
    owner TEXT,
    due TEXT,
    kind TEXT,
    instruction TEXT,
    target_paths TEXT,
    quote TEXT,
    status TEXT NOT NULL DEFAULT 'proposed',
    branch TEXT,
    commit_sha TEXT,
    diff TEXT,
    result TEXT,
    updated_at TEXT,
    FOREIGN KEY (meeting_id) REFERENCES meetings(id)
);

CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    decision TEXT NOT NULL,
    ts TEXT NOT NULL,
    FOREIGN KEY (item_id) REFERENCES action_items(id)
);

CREATE TABLE IF NOT EXISTS reversals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    new_decision_id INTEGER,
    prior_decision_id INTEGER,
    relation TEXT,
    confidence REAL,
    explanation TEXT,
    new_quote TEXT,
    prior_quote TEXT,
    FOREIGN KEY (new_decision_id) REFERENCES decisions(id),
    FOREIGN KEY (prior_decision_id) REFERENCES decisions(id)
);

CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    entity TEXT,
    entity_id INTEGER,
    event TEXT,
    detail TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db(path: Optional[Path] = None) -> Path:
    db_path = path or settings.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    settings.audio_dir.mkdir(parents=True, exist_ok=True)
    settings.worktrees_dir.mkdir(parents=True, exist_ok=True)
    with db(db_path) as conn:
        conn.executescript(SCHEMA)
    return db_path


@contextmanager
def db(path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    db_path = path or settings.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def audit(
    entity: str,
    entity_id: Optional[int],
    event: str,
    detail: Any = None,
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    detail_s = None
    if detail is not None:
        detail_s = detail if isinstance(detail, str) else json.dumps(detail)

    def _write(c: sqlite3.Connection) -> None:
        c.execute(
            "INSERT INTO audit (ts, entity, entity_id, event, detail) VALUES (?, ?, ?, ?, ?)",
            (_now(), entity, entity_id, event, detail_s),
        )

    if conn is not None:
        _write(conn)
    else:
        with db() as c:
            _write(c)


def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict]:
    if row is None:
        return None
    return dict(row)


def now() -> str:
    return _now()
