"""Local SQLite persistence and retention-policy management."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import aiosqlite

from src.agent.schemas import ChatMessage


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

    async def purge_expired_data(self, retention_days: int) -> dict[str, int]:
        """Remove records older than `retention_days` to enforce data governance."""
        cutoff_iso = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat()
        deleted_counts: dict[str, int] = {}

        async with aiosqlite.connect(self._db_path) as db:
            for table, ts_column in (
                ("chat_messages", "created_at"),
                ("action_history", "created_at"),
                ("sent_notifications", "sent_at"),
            ):
                cursor = await db.execute(
                    f"DELETE FROM {table} WHERE {ts_column} < ?",
                    (cutoff_iso,),
                )
                deleted_counts[table] = cursor.rowcount or 0
            await db.commit()

        return deleted_counts
