"""BOM ingestion use cases: upload → proposed mapping (preview), and mapping confirmation
(human gate 1), which queues the analysis job."""

import hashlib
import logging
import re
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from pathlib import PurePath

from app.config import Settings
from app.domain.enums import BomField, DemoRole, JobType, MappingMethod, ProjectStatus
from app.domain.errors import InvalidStateError, ValidationFailedError
from app.domain.ids import new_id
from app.domain.models import AuditEvent, BomUpload, ColumnMapping, Job, Project, utcnow
from app.infra.blobstore import BlobStore
from app.infra.repositories import Filter, Repositories
from app.ingestion.aliases import missing_required_fields
from app.ingestion.column_mapper import HeaderMapper, propose_mapping
from app.ingestion.header_detect import detect_header
from app.ingestion.readers import Grid, Workbook, read_bom_file
from app.jobs.dispatcher import JobPublisher, enqueue_job

logger = logging.getLogger(__name__)

PREVIEW_ROWS = 10
_LLM_CACHE_SIZE = 128
_CONTENT_TYPES = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".txt": "text/plain",
}
_BUSY = {ProjectStatus.ANALYZING, ProjectStatus.FINALIZED}


@dataclass(frozen=True, slots=True)
class MappingChoice:
    column_index: int
    field: BomField | None


@dataclass
class IngestionService:
    repos: Repositories
    blobs: BlobStore
    jobs: JobPublisher
    settings: Settings
    header_mapper: HeaderMapper | None = None
    _mapping_cache: "OrderedDict[str, tuple[list[ColumnMapping], list[str]]]" = field(
        default_factory=OrderedDict
    )

    async def upload(self, project_id: str, filename: str, data: bytes) -> BomUpload:
        project = await self.repos.projects.get(project_id)
        ensure_not_busy(project)

        workbook = read_bom_file(filename, data, self.settings.max_upload_bytes)
        location = detect_header(workbook)
        grid = workbook.sheets[location.sheet]
        headers = grid[location.row_index]
        body = grid[location.row_index + 1 :]
        if not any(any(row) for row in body):
            raise ValidationFailedError(
                f"The file has a header row (row {location.row_number}) but no BOM lines under it"
            )

        sha256 = hashlib.sha256(data).hexdigest()
        mapping, warnings = await self._propose(
            sha256, location.sheet, location.row_index, headers, body
        )
        missing = missing_required_fields({m.field for m in mapping if m.field is not None})
        if missing:
            warnings.append(f"Required columns not identified: {', '.join(missing)}")

        upload_id = new_id("upl")
        suffix = PurePath(filename).suffix.lower()
        blob_key = f"uploads/{project_id}/{upload_id}/{_safe_name(filename)}"
        await self.blobs.put(blob_key, data, _CONTENT_TYPES.get(suffix, "application/octet-stream"))

        upload = BomUpload(
            id=upload_id,
            filename=filename,
            sha256=sha256,
            blob_key=blob_key,
            size_bytes=len(data),
            sheets=list(workbook.sheets),
            selected_sheet=location.sheet,
            header_row=location.row_number,
            data_rows=sum(1 for row in body if any(row)),
            mapping=mapping,
            preview_rows=[row for row in body if any(row)][:PREVIEW_ROWS],
            warnings=warnings,
        )
        await self.repos.uploads(project_id).put(upload)
        project.status = ProjectStatus.MAPPING_REVIEW
        project.updated_at = utcnow()
        await self.repos.projects.put(project)
        return upload

    async def confirm_mapping(
        self,
        project_id: str,
        upload_id: str,
        choices: list[MappingChoice],
        role: DemoRole,
        *,
        sheet: str | None = None,
        header_row: int | None = None,
        idempotency_key: str | None = None,
    ) -> Job:
        project = await self.repos.projects.get(project_id)
        if idempotency_key:
            existing = await self.repos.jobs.list(
                filters=[
                    Filter("project_id", "==", project_id),
                    Filter("idempotency_key", "==", idempotency_key),
                ],
                limit=1,
            )
            if existing.items:
                return existing.items[0]
        ensure_not_busy(project)
        upload = await self.repos.uploads(project_id).get(upload_id)

        headers = await self._headers_for(upload, sheet, header_row)
        mapping = _apply_choices(upload.mapping, headers, choices)
        missing = missing_required_fields({m.field for m in mapping if m.field is not None})
        if missing:
            raise ValidationFailedError(
                f"Map the required columns before continuing: {', '.join(missing)}",
                {"missing": list(missing)},
            )

        before = {"mapping": [m.model_dump(mode="json") for m in upload.mapping]}
        upload.mapping = mapping
        upload.selected_sheet = sheet or upload.selected_sheet
        upload.header_row = header_row or upload.header_row
        upload.confirmed = True
        await self.repos.uploads(project_id).put(upload)

        project.status = ProjectStatus.ANALYZING
        project.updated_at = utcnow()
        await self.repos.projects.put(project)
        await self.repos.audit(project_id).put(
            AuditEvent(
                id=new_id("aud"),
                actor_role=role,
                action="MAPPING_CONFIRMED",
                target=f"upload:{upload.id}",
                before=before,
                after={"mapping": [m.model_dump(mode="json") for m in mapping]},
            )
        )
        return await enqueue_job(
            self.repos,
            self.jobs,
            project_id,
            JobType.ANALYSIS,
            payload={"upload_id": upload.id},
            idempotency_key=idempotency_key,
        )

    async def _propose(
        self, sha256: str, sheet: str, row_index: int, headers: list[str | None], body: Grid
    ) -> tuple[list[ColumnMapping], list[str]]:
        key = f"{sha256}:{sheet}:{row_index}"
        if key in self._mapping_cache:
            self._mapping_cache.move_to_end(key)
            mapping, warnings = self._mapping_cache[key]
            return list(mapping), list(warnings)
        mapping, warnings = await propose_mapping(headers, body[:20], self.header_mapper)
        if not warnings:  # never cache a degraded (LLM-unavailable) result
            self._mapping_cache[key] = (mapping, warnings)
            while len(self._mapping_cache) > _LLM_CACHE_SIZE:
                self._mapping_cache.popitem(last=False)
        return mapping, list(warnings)

    async def _headers_for(
        self, upload: BomUpload, sheet: str | None, header_row: int | None
    ) -> list[str | None]:
        same_location = sheet in (None, upload.selected_sheet) and header_row in (
            None,
            upload.header_row,
        )
        if same_location:
            return [m.header for m in upload.mapping]
        workbook = await self.load_workbook(upload)
        grid = workbook.sheets.get(sheet or upload.selected_sheet)
        row = (header_row or upload.header_row) - 1
        if grid is None or not 0 <= row < len(grid):
            raise ValidationFailedError("Selected sheet or header row does not exist in the file")
        return grid[row]

    async def load_workbook(self, upload: BomUpload) -> Workbook:
        data = await self.blobs.get(upload.blob_key)
        return read_bom_file(upload.filename, data, self.settings.max_upload_bytes)


def _apply_choices(
    proposed: list[ColumnMapping], headers: list[str | None], choices: list[MappingChoice]
) -> list[ColumnMapping]:
    if any(not 0 <= c.column_index < len(headers) for c in choices):
        raise ValidationFailedError("Mapping refers to a column that does not exist")
    duplicates = [f for f, n in Counter(c.field for c in choices if c.field).items() if n > 1]
    if duplicates:
        raise ValidationFailedError(
            f"Each field can map to only one column: {', '.join(str(d) for d in duplicates)}"
        )
    by_index = {m.column_index: m for m in proposed}
    chosen = {c.column_index: c.field for c in choices}
    result: list[ColumnMapping] = []
    for index, header in enumerate(headers):
        suggestion = by_index.get(index)
        target = chosen.get(index, suggestion.field if suggestion else None)
        if suggestion and suggestion.field == target and suggestion.header == (header or ""):
            result.append(suggestion)
        else:
            result.append(
                ColumnMapping(
                    column_index=index,
                    header=header or "",
                    field=target,
                    confidence=1.0 if target else 0.0,
                    method=MappingMethod.USER if target else MappingMethod.NONE,
                )
            )
    taken = Counter(m.field for m in result if m.field)
    if any(n > 1 for n in taken.values()):
        raise ValidationFailedError("A field is mapped to more than one column; unmap one of them")
    return result


def ensure_not_busy(project: Project) -> None:
    if project.status in _BUSY:
        raise InvalidStateError(
            f"Project is {project.status.value.lower()}; "
            "wait for it to finish or start a new revision",
            {"status": project.status.value},
        )


def _safe_name(filename: str) -> str:
    name = PurePath(filename).name
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:120] or "bom"
