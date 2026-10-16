from decimal import Decimal

from app.container import Container
from app.domain.enums import IssueCode, JobStatus, JobType, ProjectStatus
from app.domain.facts import actual, unavailable
from app.domain.models import BomLine, BomUpload, ColumnMapping, Project
from app.infra.jobbus import InlineJobBus
from app.ingestion.consolidate import consolidate
from app.jobs.dispatcher import enqueue_job


def _line(
    row: int, mpn: str, qty: Decimal | None = Decimal(1), uom: str = "EA", mfr: str | None = "Yageo"
) -> BomLine:
    return BomLine(
        id=f"ln_{row}",
        line_no=row,
        mpn=mpn,
        manufacturer=mfr,
        uom=uom,
        source_rows=[row],
        qty_per=actual(qty, f"ev_{row}") if qty is not None else unavailable("bad", f"ev_{row}"),
    )


def _codes(line: BomLine) -> set[IssueCode]:
    return {issue.code for issue in line.validation}


def test_uom_conflict_is_flagged_not_merged() -> None:
    lines = consolidate([_line(2, "W1"), _line(3, "W1", uom="M")])
    assert len(lines) == 2
    assert all(IssueCode.UOM_CONFLICT in _codes(line) for line in lines)


def test_manufacturer_conflict_is_flagged_not_merged() -> None:
    lines = consolidate([_line(2, "X1", mfr="Yageo"), _line(3, "X1", mfr="Vishay")])
    assert len(lines) == 2
    assert all(IssueCode.DUPLICATE_MPN_CONFLICT in _codes(line) for line in lines)


def test_duplicates_with_invalid_quantity_stay_separate() -> None:
    lines = consolidate([_line(2, "Y1"), _line(3, "Y1", qty=None)])
    assert len(lines) == 2


def test_merge_fills_missing_manufacturer_from_another_row() -> None:
    (merged,) = consolidate([_line(2, "Z1", mfr=None), _line(3, "Z1", mfr="Murata")])
    assert merged.manufacturer == "Murata"
    assert merged.qty_per.value == 2
    assert merged.source_rows == [2, 3]


async def test_failed_analysis_marks_project_failed_and_allows_retry(container: Container) -> None:
    project = Project(
        id="prj_1", name="P", currency="USD", build_quantities=[10], status=ProjectStatus.ANALYZING
    )
    await container.repos.projects.put(project)
    await container.blobs.put("uploads/prj_1/upl_1/bom.csv", b"MPN,Qty\n", "text/csv")
    await container.repos.uploads("prj_1").put(
        BomUpload(
            id="upl_1",
            filename="bom.csv",
            sha256="0",
            blob_key="uploads/prj_1/upl_1/bom.csv",
            size_bytes=8,
            sheets=["CSV"],
            selected_sheet="CSV",
            header_row=1,
            data_rows=0,
            mapping=[
                ColumnMapping(column_index=0, header="MPN"),
                ColumnMapping(column_index=1, header="Qty"),
            ],
        )
    )

    job = await enqueue_job(
        container.repos,
        container.job_bus,
        "prj_1",
        JobType.ANALYSIS,
        payload={"upload_id": "upl_1"},
    )
    assert isinstance(container.job_bus, InlineJobBus)
    await container.job_bus.drain()

    finished = await container.repos.jobs.get(job.id)
    assert finished.status is JobStatus.FAILED
    assert finished.error is not None
    assert finished.error.code == "VALIDATION_ERROR"
    assert (await container.repos.projects.get("prj_1")).status is ProjectStatus.FAILED
