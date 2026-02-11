from __future__ import annotations

from typing import Any

from app.bot.utils.sqlite import SQLiteDatabase
from .models import UserData


class RedisStorage:
    """Class for managing user data storage using SQLite."""

    def __init__(self, db: SQLiteDatabase) -> None:
        """
        Initializes the RedisStorage instance.

        :param db: The SQLite database instance to be used for data storage.
        """
        self.db = db

    async def get_by_message_thread_id(self, message_thread_id: int) -> UserData | None:
        """
        Retrieves user data based on message thread ID.

        :param message_thread_id: The ID of the message thread.
        :return: The user data or None if not found.
        """
        async with self.db.conn.execute(
            "SELECT * FROM users WHERE message_thread_id = ? LIMIT 1",
            (message_thread_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return None if row is None else _row_to_user(row)

    async def get_user(self, id_: int) -> UserData | None:
        """
        Retrieves user data based on user ID.

        :param id_: The ID of the user.
        :return: The user data or None if not found.
        """
        async with self.db.conn.execute(
            "SELECT * FROM users WHERE id = ?",
            (id_,),
        ) as cursor:
            row = await cursor.fetchone()
        return None if row is None else _row_to_user(row)

    async def update_user(self, id_: int, data: UserData) -> None:
        """
        Updates user data in SQLite.

        :param id_: The ID of the user to be updated.
        :param data: The updated user data.
        """
        await self.db.conn.execute(
            """
            INSERT INTO users (
                id,
                message_thread_id,
                message_silent_id,
                message_silent_mode,
                full_name,
                username,
                state,
                is_banned,
                language_code,
                ticket_status,
                awaiting_reply,
                last_user_message_at,
                created_at,
                panel_message_id,
                operator_replied
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                message_thread_id = excluded.message_thread_id,
                message_silent_id = excluded.message_silent_id,
                message_silent_mode = excluded.message_silent_mode,
                full_name = excluded.full_name,
                username = excluded.username,
                state = excluded.state,
                is_banned = excluded.is_banned,
                language_code = excluded.language_code,
                ticket_status = excluded.ticket_status,
                awaiting_reply = excluded.awaiting_reply,
                last_user_message_at = excluded.last_user_message_at,
                created_at = excluded.created_at,
                panel_message_id = excluded.panel_message_id,
                operator_replied = excluded.operator_replied
            """,
            (
                data.id,
                data.message_thread_id,
                data.message_silent_id,
                int(bool(data.message_silent_mode)),
                data.full_name,
                data.username,
                data.state,
                int(bool(data.is_banned)),
                data.language_code,
                data.ticket_status,
                int(bool(data.awaiting_reply)),
                data.last_user_message_at,
                data.created_at,
                data.panel_message_id,
                int(bool(data.operator_replied)),
            ),
        )
        await self.db.conn.commit()

    async def get_all_users_ids(self) -> list[int]:
        """
        Retrieves all user IDs stored in the database.

        :return: A list of all user IDs.
        """
        async with self.db.conn.execute("SELECT id FROM users") as cursor:
            rows = await cursor.fetchall()
        return [int(row["id"]) for row in rows]
    
    async def get_banned_users(self) -> list[UserData]:
        """
        Retrieves all banned users.
        
        :return: A list of banned UserData objects.
        """
        async with self.db.conn.execute("SELECT * FROM users WHERE is_banned = 1") as cursor:
            rows = await cursor.fetchall()
        return [_row_to_user(row) for row in rows]

    async def add_message_link(self, thread_message_id: int, user_id: int, user_message_id: int) -> None:
        await self.db.conn.execute(
            """
            INSERT INTO message_links (thread_message_id, user_id, user_message_id)
            VALUES (?, ?, ?)
            ON CONFLICT(thread_message_id, user_message_id) DO NOTHING
            """,
            (thread_message_id, user_id, user_message_id),
        )
        await self.db.conn.commit()

    async def get_message_links(self, thread_message_id: int) -> list[int]:
        async with self.db.conn.execute(
            "SELECT user_message_id FROM message_links WHERE thread_message_id = ?",
            (thread_message_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [int(row["user_message_id"]) for row in rows]

    async def delete_message_links(self, thread_message_id: int) -> None:
        await self.db.conn.execute(
            "DELETE FROM message_links WHERE thread_message_id = ?",
            (thread_message_id,),
        )
        await self.db.conn.commit()


def _row_to_user(row: Any) -> UserData:
    return UserData(
        message_thread_id=row["message_thread_id"],
        message_silent_id=row["message_silent_id"],
        message_silent_mode=bool(row["message_silent_mode"]),
        id=int(row["id"]),
        full_name=row["full_name"],
        username=row["username"],
        state=row["state"],
        is_banned=bool(row["is_banned"]),
        language_code=row["language_code"],
        ticket_status=row["ticket_status"],
        awaiting_reply=bool(row["awaiting_reply"]),
        last_user_message_at=row["last_user_message_at"],
        created_at=row["created_at"],
        panel_message_id=row["panel_message_id"],
        operator_replied=bool(row["operator_replied"]),
    )
