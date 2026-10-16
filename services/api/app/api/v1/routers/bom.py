"""BOM upload (preview + proposed mapping) and mapping confirmation (human gate 1)."""

from typing import Annotated

from fastapi import APIRouter, File, Header, UploadFile

from app.api.deps import ContainerDep, DemoRoleDep
from app.api.v1.schemas import JobAccepted, MappingConfirm, UploadPreview
from app.domain.errors import FileTooLargeError, ValidationFailedError
from app.ingestion.service import MappingChoice

router = APIRouter(prefix="/projects/{pid}/bom", tags=["bom"])


@router.post("", response_model=UploadPreview)
async def upload_bom(
    pid: str, container: ContainerDep, file: Annotated[UploadFile, File()]
) -> UploadPreview:
    limit = container.settings.max_upload_bytes
    data = await file.read(limit + 1)  # never buffer more than the limit + 1 byte
    if len(data) > limit:
        raise FileTooLargeError(f"File exceeds the {limit // 1_048_576} MB limit")
    if not file.filename:
        raise ValidationFailedError("The upload has no filename")
    upload = await container.ingestion.upload(pid, file.filename, data)
    return UploadPreview.of(upload)


@router.put("/mapping", status_code=202, response_model=JobAccepted)
async def confirm_mapping(
    pid: str,
    body: MappingConfirm,
    container: ContainerDep,
    role: DemoRoleDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)] = None,
) -> JobAccepted:
    job = await container.ingestion.confirm_mapping(
        pid,
        body.upload_id,
        [MappingChoice(c.column_index, c.field) for c in body.mapping],
        role,
        sheet=body.sheet,
        header_row=body.header_row,
        idempotency_key=idempotency_key,
    )
    return JobAccepted(job_id=job.id)
