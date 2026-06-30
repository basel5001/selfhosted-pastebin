"""SQLite database helper for paste storage."""

import sqlite3
import os
from datetime import datetime, timezone

DB_PATH = os.getenv("DATABASE_PATH", "data/pastebin.db")

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS pastes (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'plain',
    created_at TEXT NOT NULL,
    expires_at TEXT,
    password_hash TEXT,
    views INTEGER NOT NULL DEFAULT 0,
    burn_after_read BOOLEAN NOT NULL DEFAULT 0
)
"""


def get_connection() -> sqlite3.Connection:
    """Return a new SQLite connection with WAL mode enabled."""
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create tables if they do not exist."""
    with get_connection() as conn:
        conn.execute(CREATE_TABLE)
        conn.commit()


def insert_paste(
    paste_id: str,
    content: str,
    language: str,
    expires_at: str | None,
    password_hash: str | None,
    burn_after_read: bool,
) -> None:
    """Insert a new paste."""
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO pastes (id, content, language, created_at, expires_at, password_hash, views, burn_after_read)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (paste_id, content, language, now, expires_at, password_hash, burn_after_read),
        )
        conn.commit()


def get_paste(paste_id: str) -> dict | None:
    """Fetch a paste by ID. Returns None if not found or expired."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM pastes WHERE id = ?", (paste_id,)).fetchone()
        if row is None:
            return None

        paste = dict(row)

        # Check expiry
        if paste["expires_at"]:
            expires = datetime.fromisoformat(paste["expires_at"])
            if datetime.now(timezone.utc) > expires:
                conn.execute("DELETE FROM pastes WHERE id = ?", (paste_id,))
                conn.commit()
                return None

        return paste


def increment_views(paste_id: str) -> int:
    """Increment the view counter and return the new count."""
    with get_connection() as conn:
        conn.execute("UPDATE pastes SET views = views + 1 WHERE id = ?", (paste_id,))
        conn.commit()
        row = conn.execute("SELECT views FROM pastes WHERE id = ?", (paste_id,)).fetchone()
        return row["views"] if row else 0


def delete_paste(paste_id: str) -> bool:
    """Delete a paste. Returns True if a row was deleted."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM pastes WHERE id = ?", (paste_id,))
        conn.commit()
        return cursor.rowcount > 0


def cleanup_expired() -> int:
    """Remove all expired pastes. Returns count of deleted rows."""
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM pastes WHERE expires_at IS NOT NULL AND expires_at < ?",
            (now,),
        )
        conn.commit()
        return cursor.rowcount


def count_pastes() -> int:
    """Return total paste count."""
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) as cnt FROM pastes").fetchone()
        return row["cnt"]
