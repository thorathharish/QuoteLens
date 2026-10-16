"""Runs the same contract as the in-memory store against the Firestore emulator.

Start it with `gcloud emulators firestore start --host-port=localhost:8681` and set
FIRESTORE_EMULATOR_HOST=localhost:8681. Skipped otherwise.
"""

import os
from decimal import Decimal

import pytest

from app.domain.facts import actual
from app.domain.ids import new_id
from app.domain.models import BomLine, Project
from app.infra.repositories import Filter, OrderBy, Repositories

pytestmark = [
    pytest.mark.firestore,
    pytest.mark.skipif(
        not os.environ.get("FIRESTORE_EMULATOR_HOST"), reason="Firestore emulator not running"
    ),
]


@pytest.fixture
def repos() -> Repositories:
    from app.infra.repositories.firestore import FirestoreDocumentStore

    return Repositories(FirestoreDocumentStore.from_project("quotelens-test"))


async def test_crud_pagination_and_recursive_delete(repos: Repositories) -> None:
    pid = new_id("prj")
    await repos.projects.put(
        Project(id=pid, name="Emulator", currency="USD", build_quantities=[100])
    )
    lines = repos.lines(pid)
    await lines.put_many(
        BomLine(
            id=f"ln_{n:03d}",
            line_no=n,
            mpn="DUP" if n % 2 else f"M{n}",
            qty_per=actual(Decimal(n), "ev"),
        )
        for n in range(1, 8)
    )

    assert (await lines.get("ln_003")).qty_per.value == Decimal(3)
    dup = await lines.list(filters=[Filter("mpn", "==", "DUP")])
    assert sorted(line.line_no for line in dup.items) == [1, 3, 5, 7]

    first = await lines.list(order_by=OrderBy("line_no", descending=True), limit=3)
    second = await lines.list(
        order_by=OrderBy("line_no", descending=True), limit=3, cursor=first.next_cursor
    )
    assert [line.line_no for line in first.items + second.items] == [7, 6, 5, 4, 3, 2]

    await repos.projects.delete(pid)
    assert await repos.projects.find(pid) is None
    assert await lines.all() == []
    await repos.store.ping()
