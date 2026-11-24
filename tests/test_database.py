"""Unit tests for SQLite persistence and retention governance."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import aiosqlite

from src.storage.database import Database
from src.storage.media_governance import ephemeral_memory_buffer


async def test_database_chat_history_and_clear(tmp_path: Path) -> None:
    """Verify chat messages are stored chronologically and cleared per user."""
    db = Database(tmp_path / "test.db")
    await db.init()

    await db.add_chat_message(100, "user", "Oi")
    await db.add_chat_message(100, "assistant", "Olá!")
    await db.add_chat_message(200, "user", "Outro usuário")

    history = await db.get_recent_messages(100, limit=10)
    assert [(m.role, m.content) for m in history] == [
        ("user", "Oi"),
        ("assistant", "Olá!"),
    ]

    deleted = await db.clear_chat_history(100)
    assert deleted == 2
    assert await db.get_recent_messages(100) == []
    assert len(await db.get_recent_messages(200)) == 1


async def test_database_purge_expired_data(tmp_path: Path) -> None:
    """Verify records older than DATA_RETENTION_DAYS are purged."""
    db_path = tmp_path / "retention.db"
    db = Database(db_path)
    await db.init()

    await db.add_chat_message(100, "user", "Mensagem recente")

    old_ts = (datetime.now(UTC) - timedelta(days=45)).isoformat()
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            "INSERT INTO chat_messages (user_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (100, "user", "Mensagem antiga", old_ts),
        )
        await conn.commit()

    purged = await db.purge_expired_data(retention_days=30)
    assert purged["chat_messages"] == 1

    remaining = await db.get_recent_messages(100)
    assert [m.content for m in remaining] == ["Mensagem recente"]


def test_ephemeral_memory_buffer_disposes_bytes() -> None:
    """Verify BytesIO buffer is closed immediately upon exiting context."""
    with ephemeral_memory_buffer() as buf:
        buf.write(b"audio-bytes")
        assert buf.getvalue() == b"audio-bytes"

    assert buf.closed is True
