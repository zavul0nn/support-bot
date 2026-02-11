from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from typing import Any, Iterable
from uuid import uuid4

from app.bot.utils.sqlite import SQLiteDatabase


@dataclass
class QuickReplyAttachment:
    """Attachment associated with a quick reply item."""

    type: str
    file_id: str
    caption: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "QuickReplyAttachment":
        return cls(
            type=payload.get("type", ""),
            file_id=payload.get("file_id", ""),
            caption=payload.get("caption"),
        )


@dataclass
class QuickReplyItem:
    """Quick reply entry available to operators."""

    id: str
    title: str
    text: str | None = None
    attachments: list[QuickReplyAttachment] = field(default_factory=list)

    def to_json(self) -> str:
        data = asdict(self)
        data["attachments"] = [asdict(attachment) for attachment in self.attachments]
        return json.dumps(data, ensure_ascii=False)

    @classmethod
    def from_json(cls, payload: str) -> "QuickReplyItem":
        data = json.loads(payload)
        attachments_data: Iterable[dict[str, Any]] = data.get("attachments", [])
        attachments = [QuickReplyAttachment.from_dict(item) for item in attachments_data]
        return cls(
            id=data["id"],
            title=data["title"],
            text=data.get("text"),
            attachments=attachments,
        )


class QuickReplyStorage:
    """SQLite-backed storage for operator quick replies."""

    def __init__(self, db: SQLiteDatabase) -> None:
        self.db = db

    async def list_items(self) -> list[QuickReplyItem]:
        async with self.db.conn.execute(
            "SELECT payload FROM quick_reply_items ORDER BY sort_order",
        ) as cursor:
            rows = await cursor.fetchall()

        return [QuickReplyItem.from_json(row["payload"]) for row in rows]

    async def has_items(self) -> bool:
        async with self.db.conn.execute("SELECT 1 FROM quick_reply_items LIMIT 1") as cursor:
            row = await cursor.fetchone()
        return row is not None

    async def get_item(self, item_id: str) -> QuickReplyItem | None:
        async with self.db.conn.execute(
            "SELECT payload FROM quick_reply_items WHERE id = ?",
            (item_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return QuickReplyItem.from_json(row["payload"])

    async def add_item(
        self,
        title: str,
        text: str | None,
        attachments: list[QuickReplyAttachment] | None = None,
    ) -> QuickReplyItem:
        item = QuickReplyItem(
            id=str(uuid4()),
            title=title,
            text=text,
            attachments=attachments or [],
        )
        async with self.db.conn.execute("SELECT MAX(sort_order) AS max_order FROM quick_reply_items") as cursor:
            row = await cursor.fetchone()
        next_order = 1 if row is None or row["max_order"] is None else int(row["max_order"]) + 1
        await self.db.conn.execute(
            "INSERT INTO quick_reply_items (id, payload, sort_order) VALUES (?, ?, ?)",
            (item.id, item.to_json(), next_order),
        )
        await self.db.conn.commit()
        return item

    async def update_item(self, item: QuickReplyItem) -> None:
        await self.db.conn.execute(
            "UPDATE quick_reply_items SET payload = ? WHERE id = ?",
            (item.to_json(), item.id),
        )
        await self.db.conn.commit()

    async def rename_item(self, item_id: str, title: str) -> QuickReplyItem | None:
        item = await self.get_item(item_id)
        if item is None:
            return None
        item.title = title
        await self.update_item(item)
        return item

    async def update_content(
        self,
        item_id: str,
        *,
        text: str | None,
        attachments: list[QuickReplyAttachment],
    ) -> QuickReplyItem | None:
        item = await self.get_item(item_id)
        if item is None:
            return None
        item.text = text
        item.attachments = attachments
        await self.update_item(item)
        return item

    async def delete_item(self, item_id: str) -> None:
        await self.db.conn.execute(
            "DELETE FROM quick_reply_items WHERE id = ?",
            (item_id,),
        )
        await self.db.conn.commit()
