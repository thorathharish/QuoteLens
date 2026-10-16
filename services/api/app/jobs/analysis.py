"""The analysis job: a staged, idempotent pipeline (ADR-0003).

Phase 2 stages: parse → validate/consolidate → save. Phase 3 appends sourcing, impact
and risk stages. Re-running overwrites documents keyed by source row, so Pub/Sub
redelivery is safe. Any failure marks the project FAILED so the user can retry.
"""

import logging
from collections import Counter
from dataclasses import dataclass

from app.domain.enums import ProjectStatus
from app.domain.errors import ValidationFailedError
from app.domain.models import BomUpload, Job, Project, SourceFile, utcnow
from app.infra.repositories import Repositories
from app.ingestion.parse import ParsedBom, parse_rows
from app.ingestion.service import IngestionService
from app.jobs.dispatcher import JobContext
from app.sourcing.service import SourcingService

logger = logging.getLogger(__name__)


@dataclass
class AnalysisPipeline:
    repos: Repositories
    ingestion: IngestionService
    sourcing: SourcingService

    async def __call__(self, job: Job, ctx: JobContext) -> None:
        project = await self.repos.projects.get(job.project_id)
        try:
            await self._run(job, ctx, project)
        except Exception:
            project = await self.repos.projects.get(job.project_id)
            project.status = ProjectStatus.FAILED
            project.updated_at = utcnow()
            await self.repos.projects.put(project)
            raise

    async def _run(self, job: Job, ctx: JobContext, project: Project) -> None:
        upload_id = job.payload.get("upload_id")
        if upload_id is not None:
            if not isinstance(upload_id, str):
                raise ValidationFailedError("Analysis job has an invalid upload_id")
            await self._ingest(project, upload_id, ctx)

        lines = await self.repos.lines(project.id).all()
        if not lines:
            raise ValidationFailedError("The project has no BOM lines to analyze")
        wanted = job.payload.get("line_ids")
        if isinstance(wanted, list) and wanted:
            lines = [line for line in lines if line.id in set(map(str, wanted))]

        await ctx.progress("sourcing", 70)
        outcome = await self.sourcing.source(project, lines)
        for warning in outcome.warnings:
            await ctx.warn(warning)

        project = await self.repos.projects.get(project.id)
        all_lines = await self.repos.lines(project.id).all()
        project.stats.lines = len(all_lines)
        project.stats.matched = sum(1 for line in all_lines if line.match.status == "MATCHED")
        project.stats.data_issues = dict(
            Counter(issue.code for line in all_lines for issue in line.validation)
        )
        project.status = ProjectStatus.IN_REVIEW
        project.updated_at = utcnow()
        await self.repos.projects.put(project)

    async def _ingest(self, project: Project, upload_id: str, ctx: JobContext) -> None:
        upload = await self.repos.uploads(project.id).get(upload_id)
        await ctx.progress("parse", 10)
        parsed = await self._parse(upload)
        if not parsed.lines:
            raise ValidationFailedError("No BOM lines were found below the header row")

        await ctx.progress("save", 40)
        await self._replace_lines(project.id, parsed)
        project.source_file = SourceFile(
            filename=upload.filename,
            gcs_uri=upload.blob_key,
            sha256=upload.sha256,
            sheet=upload.selected_sheet,
            header_row=upload.header_row,
        )
        project.mapping = {m.header: (m.field.value if m.field else None) for m in upload.mapping}
        await self.repos.projects.put(project)
        logger.info(
            "Parsed BOM",
            extra={"fields": {"lines": len(parsed.lines), "skipped_rows": parsed.skipped_rows}},
        )

    async def _parse(self, upload: BomUpload) -> ParsedBom:
        workbook = await self.ingestion.load_workbook(upload)
        grid = workbook.sheets.get(upload.selected_sheet)
        if grid is None:
            raise ValidationFailedError(f"Sheet '{upload.selected_sheet}' is missing from the file")
        return parse_rows(
            grid,
            upload.header_row - 1,
            upload.mapping,
            filename=upload.filename,
            sheet=upload.selected_sheet,
        )

    async def _replace_lines(self, project_id: str, parsed: ParsedBom) -> None:
        lines = self.repos.lines(project_id)
        evidence = self.repos.evidence(project_id)
        keep_lines = {line.id for line in parsed.lines}
        keep_evidence = {ev.id for ev in parsed.evidence}
        for old in await lines.all():
            if old.id not in keep_lines:
                await lines.delete(old.id)
        for old_ev in await evidence.all():
            if old_ev.kind == "BOM_CELL" and old_ev.id not in keep_evidence:
                await evidence.delete(old_ev.id)
        await evidence.put_many(parsed.evidence)
        await lines.put_many(parsed.lines)
