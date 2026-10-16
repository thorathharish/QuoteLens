from decimal import Decimal

import pytest

from app.domain.enums import Provenance
from app.domain.errors import NotFoundError
from app.domain.facts import actual
from app.domain.models import BomLine, Project
from app.infra.repositories import Filter, OrderBy, Repositories
from app.infra.repositories.memory import InMemoryDocumentStore


def _project(pid: str = "prj_1") -> Project:
    return Project(id=pid, name="Motor controller", currency="USD", build_quantities=[100, 1000])


def _line(n: int, mpn: str | None = None) -> BomLine:
    return BomLine(
        id=f"ln_{n:03d}",
        line_no=n,
        mpn=mpn or f"MPN-{n}",
        qty_per=actual(Decimal(n), f"ev_{n}"),
    )


@pytest.fixture
def repos() -> Repositories:
    return Repositories(InMemoryDocumentStore())


async def test_put_get_round_trip_preserves_facts(repos: Repositories) -> None:
    await repos.projects.put(_project())
    await repos.lines("prj_1").put(_line(3))

    line = await repos.lines("prj_1").get("ln_003")
    assert line.qty_per.value == Decimal(3)
    assert line.qty_per.provenance is Provenance.ACTUAL


async def test_get_missing_raises_not_found(repos: Repositories) -> None:
    with pytest.raises(NotFoundError):
        await repos.projects.get("nope")
    assert await repos.projects.find("nope") is None


async def test_stored_documents_are_isolated_from_caller_mutation(repos: Repositories) -> None:
    project = _project()
    await repos.projects.put(project)
    project.name = "changed after save"
    assert (await repos.projects.get("prj_1")).name == "Motor controller"


async def test_list_filters_orders_and_paginates(repos: Repositories) -> None:
    lines = repos.lines("prj_1")
    await lines.put_many([_line(n, mpn="DUP" if n % 2 else None) for n in range(1, 8)])

    dup = await lines.list(filters=[Filter("mpn", "==", "DUP")])
    assert [line.line_no for line in dup.items] == [1, 3, 5, 7]

    first = await lines.list(order_by=OrderBy("line_no", descending=True), limit=3)
    assert [line.line_no for line in first.items] == [7, 6, 5]
    assert first.next_cursor == "ln_005"

    second = await lines.list(
        order_by=OrderBy("line_no", descending=True), limit=3, cursor=first.next_cursor
    )
    assert [line.line_no for line in second.items] == [4, 3, 2]

    everything = await lines.all()
    assert len(everything) == 7


async def test_deleting_project_removes_nested_collections(repos: Repositories) -> None:
    await repos.projects.put(_project())
    await repos.lines("prj_1").put(_line(1))
    await repos.projects.delete("prj_1")

    assert await repos.projects.find("prj_1") is None
    assert await repos.lines("prj_1").all() == []
