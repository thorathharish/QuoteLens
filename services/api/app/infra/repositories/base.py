"""Storage abstraction.

A minimal document-store interface (`DocumentStore`) is implemented by an in-memory
store (tests, offline dev) and a Firestore store (deployed). Typed access goes through
`TypedCollection`, so services never touch raw dicts or Firestore APIs.
"""

import builtins
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Generic, Literal, Protocol, TypeVar

from pydantic import BaseModel

from app.domain.errors import NotFoundError

CollectionPath = tuple[str, ...]
"""Path to a collection, e.g. ("projects",) or ("projects", "<pid>", "lines")."""

Document = dict[str, Any]

M = TypeVar("M", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class Filter:
    field: str
    op: Literal["==", "in"]
    value: Any


@dataclass(frozen=True, slots=True)
class OrderBy:
    field: str
    descending: bool = False


@dataclass(frozen=True, slots=True)
class QueryResult:
    docs: list[tuple[str, Document]]
    next_cursor: str | None


class DocumentStore(Protocol):
    async def get(self, collection: CollectionPath, doc_id: str) -> Document | None: ...

    async def set(self, collection: CollectionPath, doc_id: str, data: Document) -> None: ...

    async def set_many(self, collection: CollectionPath, docs: Mapping[str, Document]) -> None: ...

    async def delete(self, collection: CollectionPath, doc_id: str) -> None:
        """Delete a document and everything nested under it."""
        ...

    async def query(
        self,
        collection: CollectionPath,
        filters: Sequence[Filter] = (),
        order_by: OrderBy | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> QueryResult:
        """`cursor` is the id of the last document of the previous page."""
        ...

    async def ping(self) -> None:
        """Raise if the backend is unreachable."""
        ...


class Page(BaseModel, Generic[M]):
    items: list[M]
    next_cursor: str | None = None


class TypedCollection(Generic[M]):
    """Typed CRUD over one collection. Models must have an `id: str` field."""

    def __init__(self, store: DocumentStore, path: CollectionPath, model: type[M]) -> None:
        self._store = store
        self._path = path
        self._model = model

    @property
    def path(self) -> CollectionPath:
        return self._path

    async def find(self, doc_id: str) -> M | None:
        data = await self._store.get(self._path, doc_id)
        return None if data is None else self._model.model_validate(data)

    async def get(self, doc_id: str) -> M:
        item = await self.find(doc_id)
        if item is None:
            raise NotFoundError(
                f"{self._model.__name__} '{doc_id}' not found",
                {"resource": self._model.__name__, "id": doc_id},
            )
        return item

    async def put(self, item: M) -> M:
        await self._store.set(self._path, _id_of(item), _dump(item))
        return item

    async def put_many(self, items: Iterable[M]) -> None:
        docs = {_id_of(item): _dump(item) for item in items}
        if docs:
            await self._store.set_many(self._path, docs)

    async def delete(self, doc_id: str) -> None:
        await self._store.delete(self._path, doc_id)

    async def list(
        self,
        filters: Sequence[Filter] = (),
        order_by: OrderBy | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> Page[M]:
        result = await self._store.query(self._path, filters, order_by, limit, cursor)
        items = [self._model.model_validate(data) for _, data in result.docs]
        return Page[M](items=items, next_cursor=result.next_cursor)

    async def all(
        self, filters: Sequence[Filter] = (), order_by: OrderBy | None = None
    ) -> builtins.list[M]:
        """Read every matching document, following cursors. For bounded collections only."""
        items: builtins.list[M] = []
        cursor: str | None = None
        while True:
            page = await self.list(filters, order_by, limit=500, cursor=cursor)
            items.extend(page.items)
            if page.next_cursor is None:
                return items
            cursor = page.next_cursor


def _id_of(item: BaseModel) -> str:
    doc_id = getattr(item, "id", None)
    if not isinstance(doc_id, str) or not doc_id:
        raise ValueError(f"{type(item).__name__} has no string `id`")
    return doc_id


def _dump(item: BaseModel) -> Document:
    # JSON mode keeps Decimals exact (as strings) and datetimes ISO-8601, identically
    # in every backend.
    return item.model_dump(mode="json")
