"""Persistent, user-scoped chat history stored in SQLite."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DB_PATH = Path(os.getenv("PUBMED_DB_PATH", Path(__file__).resolve().parents[1] / "pubmed.db"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init_chat_db() -> None:
    with _connect() as connection:
        connection.execute(_SCHEMA)
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation
            ON chat_messages(user_id, conversation_id, id)
            """
        )


def append_message(user_id: str, conversation_id: str, role: str, content: str) -> None:
    user_id = _normalize_required(user_id, "user_id").casefold()
    conversation_id = _normalize_required(conversation_id, "conversation_id")
    content = _normalize_required(content, "content")
    if role not in {"user", "assistant"}:
        raise ValueError("role must be 'user' or 'assistant'")

    init_chat_db()
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO chat_messages (user_id, conversation_id, role, content)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, conversation_id, role, content),
        )


def get_messages(
    user_id: str,
    conversation_id: str,
    limit: int = 200,
) -> list[dict]:
    user_id = _normalize_required(user_id, "user_id").casefold()
    conversation_id = _normalize_required(conversation_id, "conversation_id")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")

    init_chat_db()
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT role, content, created_at
            FROM (
                SELECT id, role, content, created_at
                FROM chat_messages
                WHERE user_id = ? AND conversation_id = ?
                ORDER BY id DESC
                LIMIT ?
            )
            ORDER BY id ASC
            """,
            (user_id, conversation_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def _normalize_required(value: str, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field} must not be empty")
    return normalized
