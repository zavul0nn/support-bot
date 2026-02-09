from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from typing import Any, Iterable
from uuid import uuid4

from app.bot.utils.sqlite import SQLiteDatabase


@dataclass
class FAQAttachment:
    """Attachment associated with an FAQ item."""

    type: str
    file_id: str
    caption: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FAQAttachment":
        return cls(
            type=payload.get("type", ""),
            file_id=payload.get("file_id", ""),
            caption=payload.get("caption"),
        )


@dataclass
class FAQItem:
    """FAQ entry that can be shown to users."""

    id: str
    title: str
    text: str | None = None
    attachments: list[FAQAttachment] = field(default_factory=list)

    def to_json(self) -> str:
        data = asdict(self)
        data["attachments"] = [asdict(attachment) for attachment in self.attachments]
        return json.dumps(data, ensure_ascii=False)

    @classmethod
    def from_json(cls, payload: str) -> "FAQItem":
        data = json.loads(payload)
        attachments_data: Iterable[dict[str, Any]] = data.get("attachments", [])
        attachments = [FAQAttachment.from_dict(item) for item in attachments_data]
        return cls(
            id=data["id"],
            title=data["title"],
            text=data.get("text"),
            attachments=attachments,
        )


class FAQStorage:
    """SQLite-backed storage for frequently asked questions."""

    def __init__(self, db: SQLiteDatabase) -> None:
        self.db = db

    async def list_items(self) -> list[FAQItem]:
        """Return FAQ items in stored order."""
        async with self.db.conn.execute(
            "SELECT payload FROM faq_items ORDER BY sort_order",
        ) as cursor:
            rows = await cursor.fetchall()

        return [FAQItem.from_json(row["payload"]) for row in rows]

    async def has_items(self) -> bool:
        """Check whether any FAQ entries exist."""
        async with self.db.conn.execute("SELECT 1 FROM faq_items LIMIT 1") as cursor:
            row = await cursor.fetchone()
        return row is not None

    async def get_item(self, item_id: str) -> FAQItem | None:
        """Fetch FAQ item by identifier."""
        async with self.db.conn.execute(
            "SELECT payload FROM faq_items WHERE id = ?",
            (item_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return FAQItem.from_json(row["payload"])

    async def add_item(
        self,
        title: str,
        text: str | None,
        attachments: list[FAQAttachment] | None = None,
    ) -> FAQItem:
        """Create a new FAQ entry."""
        item = FAQItem(
            id=str(uuid4()),
            title=title,
            text=text,
            attachments=attachments or [],
        )
        async with self.db.conn.execute("SELECT MAX(sort_order) AS max_order FROM faq_items") as cursor:
            row = await cursor.fetchone()
        next_order = 1 if row is None or row["max_order"] is None else int(row["max_order"]) + 1
        await self.db.conn.execute(
            "INSERT INTO faq_items (id, payload, sort_order) VALUES (?, ?, ?)",
            (item.id, item.to_json(), next_order),
        )
        await self.db.conn.commit()
        return item

    async def update_item(self, item: FAQItem) -> None:
        """Persist changes for an FAQ entry."""
        await self.db.conn.execute(
            "UPDATE faq_items SET payload = ? WHERE id = ?",
            (item.to_json(), item.id),
        )
        await self.db.conn.commit()

    async def rename_item(self, item_id: str, title: str) -> FAQItem | None:
        """Rename an existing FAQ entry."""
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
        attachments: list[FAQAttachment],
    ) -> FAQItem | None:
        """Replace textual content and attachments for an FAQ entry."""
        item = await self.get_item(item_id)
        if item is None:
            return None
        item.text = text
        item.attachments = attachments
        await self.update_item(item)
        return item

    async def delete_item(self, item_id: str) -> None:
        """Remove FAQ entry and its order record."""
        await self.db.conn.execute(
            "DELETE FROM faq_items WHERE id = ?",
            (item_id,),
        )
        await self.db.conn.commit()
