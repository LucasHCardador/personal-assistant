"""Local SQLite persistence and retention-policy management."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import aiosqlite

from src.agent.schemas import ChatMessage


@dataclass(frozen=True)
class ActionRecord:
    """Persisted reversible action record from `action_history`."""

    id: int
    user_id: int
    action_type: str
    target_system: str
    external_id: str
    payload: dict[str, Any]
    undone: bool
    created_at: str


@dataclass(frozen=True)
class PendingConfirmationRecord:
    """Persisted pending confirmation record from `pending_confirmations`."""

    id: int
    user_id: int
    tool_name: str
    args: dict[str, Any]
    summary_text: str
    status: str
    created_at: str


class Database:
    """Async SQLite repository for short-term context, reminders, and audit history."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    async def init(self) -> None:
        """Create parent directories and initialize database tables if missing."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_chat_messages_user_created
                    ON chat_messages (user_id, created_at);

                CREATE TABLE IF NOT EXISTS action_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    action_type TEXT NOT NULL,
                    target_system TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    undone INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    trigger_at TEXT NOT NULL,
                    recurrence TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sent_notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    notification_key TEXT NOT NULL UNIQUE,
                    sent_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS pending_confirmations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    tool_name TEXT NOT NULL,
                    args_json TEXT NOT NULL,
                    summary_text TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL
                );
                """
            )
            await db.commit()

    async def add_chat_message(self, user_id: int, role: str, content: str) -> None:
        """Persist a single conversation turn in short-term memory."""
        now_iso = datetime.now(UTC).isoformat()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO chat_messages (user_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, role, content, now_iso),
            )
            await db.commit()

    async def get_recent_messages(self, user_id: int, limit: int = 10) -> list[ChatMessage]:
        """Return the most recent conversation turns for a user in chronological order."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """
                SELECT role, content
                FROM chat_messages
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
            rows = await cursor.fetchall()

        return [ChatMessage(role=row[0], content=row[1]) for row in reversed(rows)]

    async def clear_chat_history(self, user_id: int) -> int:
        """Delete all short-term conversation messages for a specific user."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "DELETE FROM chat_messages WHERE user_id = ?",
                (user_id,),
            )
            await db.commit()
            return cursor.rowcount or 0

    async def record_action(
        self,
        *,
        user_id: int,
        action_type: str,
        target_system: str,
        external_id: str,
        payload: dict[str, Any],
    ) -> int:
        """Record a reversible external action in `action_history` and return its ID."""
        now_iso = datetime.now(UTC).isoformat()
        payload_json = json.dumps(payload, ensure_ascii=False)
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO action_history (
                    user_id, action_type, target_system, external_id,
                    payload_json, undone, created_at
                )
                VALUES (?, ?, ?, ?, ?, 0, ?)
                """,
                (user_id, action_type, target_system, external_id, payload_json, now_iso),
            )
            await db.commit()
            return int(cursor.lastrowid or 0)

    async def get_last_undoable_action(
        self,
        user_id: int,
        action_id: int | None = None,
    ) -> ActionRecord | None:
        """Return the specified or most recent non-undone action for a user."""
        async with aiosqlite.connect(self._db_path) as db:
            if action_id is not None:
                cursor = await db.execute(
                    """
                    SELECT id, user_id, action_type, target_system, external_id,
                           payload_json, undone, created_at
                    FROM action_history
                    WHERE id = ? AND user_id = ? AND undone = 0
                    """,
                    (action_id, user_id),
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT id, user_id, action_type, target_system, external_id,
                           payload_json, undone, created_at
                    FROM action_history
                    WHERE user_id = ? AND undone = 0
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (user_id,),
                )
            row = await cursor.fetchone()

        if row is None:
            return None

        return ActionRecord(
            id=int(row[0]),
            user_id=int(row[1]),
            action_type=str(row[2]),
            target_system=str(row[3]),
            external_id=str(row[4]),
            payload=json.loads(str(row[5])),
            undone=bool(row[6]),
            created_at=str(row[7]),
        )

    async def mark_action_undone(self, action_id: int, user_id: int) -> bool:
        """Mark an action as undone and return True if a row was updated."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """
                UPDATE action_history
                SET undone = 1
                WHERE id = ? AND user_id = ? AND undone = 0
                """,
                (action_id, user_id),
            )
            await db.commit()
            return (cursor.rowcount or 0) > 0

    async def create_pending_confirmation(
        self,
        *,
        user_id: int,
        tool_name: str,
        args: dict[str, Any],
        summary_text: str,
    ) -> int:
        """Create a pending confirmation record and return its ID."""
        now_iso = datetime.now(UTC).isoformat()
        args_json = json.dumps(args, ensure_ascii=False)
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO pending_confirmations (
                    user_id, tool_name, args_json, summary_text, status, created_at
                )
                VALUES (?, ?, ?, ?, 'pending', ?)
                """,
                (user_id, tool_name, args_json, summary_text, now_iso),
            )
            await db.commit()
            return int(cursor.lastrowid or 0)

    async def get_pending_confirmation(
        self,
        confirmation_id: int,
        user_id: int,
    ) -> PendingConfirmationRecord | None:
        """Return a pending confirmation record owned by `user_id`, if it exists."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """
                SELECT id, user_id, tool_name, args_json, summary_text, status, created_at
                FROM pending_confirmations
                WHERE id = ? AND user_id = ?
                """,
                (confirmation_id, user_id),
            )
            row = await cursor.fetchone()

        if row is None:
            return None

        return PendingConfirmationRecord(
            id=int(row[0]),
            user_id=int(row[1]),
            tool_name=str(row[2]),
            args=json.loads(str(row[3])),
            summary_text=str(row[4]),
            status=str(row[5]),
            created_at=str(row[6]),
        )

    async def resolve_pending_confirmation(
        self,
        confirmation_id: int,
        user_id: int,
        status: str,
    ) -> bool:
        """Transition a pending confirmation to `confirmed` or `cancelled`."""
        if status not in ("confirmed", "cancelled"):
            raise ValueError(f"Invalid confirmation status: {status}")

        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """
                UPDATE pending_confirmations
                SET status = ?
                WHERE id = ? AND user_id = ? AND status = 'pending'
                """,
                (status, confirmation_id, user_id),
            )
            await db.commit()
            return (cursor.rowcount or 0) > 0

    async def purge_expired_data(self, retention_days: int) -> dict[str, int]:
        """Remove records older than `retention_days` to enforce data governance."""
        cutoff_iso = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat()
        deleted_counts: dict[str, int] = {}

        async with aiosqlite.connect(self._db_path) as db:
            for table, ts_column in (
                ("chat_messages", "created_at"),
                ("action_history", "created_at"),
                ("sent_notifications", "sent_at"),
                ("pending_confirmations", "created_at"),
            ):
                cursor = await db.execute(
                    f"DELETE FROM {table} WHERE {ts_column} < ?",
                    (cutoff_iso,),
                )
                deleted_counts[table] = cursor.rowcount or 0
            await db.commit()

        return deleted_counts
