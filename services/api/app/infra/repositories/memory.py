"""In-memory DocumentStore for tests and offline development.

Operations contain no awaits between read and write, so they are atomic under asyncio.
Documents are deep-copied in and out so callers can never mutate stored state.
"""

import copy
from collections.abc import Mapping, Sequence
from typing import Any

from app.infra.repositories.base import (
    CollectionPath,
    Document,
    Filter,
    OrderBy,
    QueryResult,
)


class InMemoryDocumentStore:
    def __init__(self) -> None:
        self._collections: dict[CollectionPath, dict[str, Document]] = {}

    async def get(self, collection: CollectionPath, doc_id: str) -> Document | None:
        doc = self._collections.get(collection, {}).get(doc_id)
        return copy.deepcopy(doc) if doc is not None else None

    async def set(self, collection: CollectionPath, doc_id: str, data: Document) -> None:
        self._collections.setdefault(collection, {})[doc_id] = copy.deepcopy(data)

    async def set_many(self, collection: CollectionPath, docs: Mapping[str, Document]) -> None:
        target = self._collections.setdefault(collection, {})
        for doc_id, data in docs.items():
            target[doc_id] = copy.deepcopy(data)

    async def delete(self, collection: CollectionPath, doc_id: str) -> None:
        self._collections.get(collection, {}).pop(doc_id, None)
        prefix = (*collection, doc_id)
        for path in [p for p in self._collections if p[: len(prefix)] == prefix]:
            del self._collections[path]

    async def query(
        self,
        collection: CollectionPath,
        filters: Sequence[Filter] = (),
        order_by: OrderBy | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> QueryResult:
        rows = [
            (doc_id, doc)
            for doc_id, doc in self._collections.get(collection, {}).items()
            if all(_matches(doc, f) for f in filters)
        ]
        if order_by is not None:
            rows.sort(key=lambda r: (_sort_key(r[1].get(order_by.field)), r[0]))
            if order_by.descending:
                rows.reverse()
        else:
            rows.sort(key=lambda r: r[0])

        start = 0
        if cursor is not None:
            ids = [doc_id for doc_id, _ in rows]
            start = ids.index(cursor) + 1 if cursor in ids else len(rows)

        page = rows[start : start + limit]
        has_more = start + limit < len(rows)
        next_cursor = page[-1][0] if page and has_more else None
        return QueryResult(
            docs=[(doc_id, copy.deepcopy(doc)) for doc_id, doc in page],
            next_cursor=next_cursor,
        )

    async def ping(self) -> None:
        return None


def _matches(doc: Document, f: Filter) -> bool:
    value = doc.get(f.field)
    if f.op == "==":
        return bool(value == f.value)
    return value in f.value


def _sort_key(value: Any) -> tuple[int, Any]:
    # None sorts first, mirroring Firestore's null ordering.
    return (0, "") if value is None else (1, value)
