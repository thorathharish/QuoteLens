"""Firestore-backed DocumentStore (native mode, `(default)` database: the free-tier one).

Free-tier notes: writes are batched (max 500 per batch) and pagination uses
`limit + 1` to detect further pages without an extra count query.

Firestore rejects arrays nested directly inside arrays (e.g. a spreadsheet preview grid),
so inner arrays are wrapped in a one-key map on write and unwrapped on read. Callers see
plain nested lists either way.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from google.cloud import firestore

from app.infra.repositories.base import (
    CollectionPath,
    Document,
    Filter,
    OrderBy,
    QueryResult,
)

_BATCH_LIMIT = 500
# Not "__array__": Firestore reserves field names that start and end with "__".
_ARRAY_KEY = "_array"


def encode_nested_arrays(value: Any, inside_array: bool = False) -> Any:
    """Wrap each array that sits directly inside an array: [[1]] becomes [{"_array": [1]}]."""
    if isinstance(value, dict):
        return {k: encode_nested_arrays(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        items = [encode_nested_arrays(v, inside_array=True) for v in value]
        return {_ARRAY_KEY: items} if inside_array else items
    return value


def decode_nested_arrays(value: Any) -> Any:
    """Inverse of encode_nested_arrays."""
    if isinstance(value, dict):
        if set(value) == {_ARRAY_KEY}:
            return [decode_nested_arrays(v) for v in value[_ARRAY_KEY]]
        return {k: decode_nested_arrays(v) for k, v in value.items()}
    if isinstance(value, list):
        return [decode_nested_arrays(v) for v in value]
    return value


class FirestoreDocumentStore:
    def __init__(self, client: firestore.AsyncClient) -> None:
        self._client = client

    @classmethod
    def from_project(cls, project: str | None) -> "FirestoreDocumentStore":
        return cls(firestore.AsyncClient(project=project))

    def _collection(self, path: CollectionPath) -> Any:
        if len(path) % 2 != 1:
            raise ValueError(f"Collection path must have odd length, got {path}")
        return self._client.collection(*path)

    async def get(self, collection: CollectionPath, doc_id: str) -> Document | None:
        snapshot = await self._collection(collection).document(doc_id).get()
        return decode_nested_arrays(snapshot.to_dict()) if snapshot.exists else None

    async def set(self, collection: CollectionPath, doc_id: str, data: Document) -> None:
        await self._collection(collection).document(doc_id).set(encode_nested_arrays(data))

    async def set_many(self, collection: CollectionPath, docs: Mapping[str, Document]) -> None:
        coll = self._collection(collection)
        items = list(docs.items())
        for start in range(0, len(items), _BATCH_LIMIT):
            batch = self._client.batch()
            for doc_id, data in items[start : start + _BATCH_LIMIT]:
                batch.set(coll.document(doc_id), encode_nested_arrays(data))
            await batch.commit()

    async def delete(self, collection: CollectionPath, doc_id: str) -> None:
        await self._client.recursive_delete(self._collection(collection).document(doc_id))

    async def query(
        self,
        collection: CollectionPath,
        filters: Sequence[Filter] = (),
        order_by: OrderBy | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> QueryResult:
        coll = self._collection(collection)
        query: Any = coll
        for f in filters:
            query = query.where(filter=firestore.FieldFilter(f.field, f.op, f.value))
        direction = (
            firestore.Query.DESCENDING
            if order_by is not None and order_by.descending
            else firestore.Query.ASCENDING
        )
        if order_by is not None:
            query = query.order_by(order_by.field, direction=direction)
        # The id tie-break runs in the same direction as the sort: Firestore then serves the
        # query from its automatic single-field index. Mixed directions (field DESC, id ASC)
        # would need a composite index for every descending listing.
        query = query.order_by("__name__", direction=direction)
        if cursor is not None:
            cursor_snapshot = await coll.document(cursor).get()
            if cursor_snapshot.exists:
                query = query.start_after(cursor_snapshot)

        snapshots = [s async for s in query.limit(limit + 1).stream()]
        has_more = len(snapshots) > limit
        page = snapshots[:limit]
        return QueryResult(
            docs=[(s.id, decode_nested_arrays(s.to_dict())) for s in page],
            next_cursor=page[-1].id if has_more and page else None,
        )

    async def ping(self) -> None:
        # A single-document read: cheap (1 read) and proves connectivity + permissions.
        await self._client.collection("_health").document("ping").get()
