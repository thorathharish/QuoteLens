"""Request/response DTOs for /api/v1. Domain models are reused for responses where their
shape is already the public contract; internal fields are excluded explicitly."""

from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import BomField, DataMode, MappingMethod
from app.domain.models import BomLine, BomUpload, Project


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    customer: str | None = Field(default=None, max_length=120)
    currency: str = Field(default="USD", pattern="^[A-Z]{3}$")
    build_quantities: list[Annotated[int, Field(ge=1, le=1_000_000)]] = Field(
        min_length=1, max_length=5
    )
    target_ship_date: date | None = None
    data_mode: DataMode = DataMode.CACHE_FIRST


class ProjectPage(ApiModel):
    items: list[Project]
    next_cursor: str | None = None


class MappingColumn(ApiModel):
    column_index: int
    header: str
    field: BomField | None
    confidence: float
    method: MappingMethod
    reason: str | None = None


class UploadPreview(ApiModel):
    upload_id: str
    filename: str
    sheets: list[str]
    selected_sheet: str
    header_row: int = Field(description="1-based row number of the detected header")
    data_rows: int
    proposed_mapping: list[MappingColumn]
    preview_rows: list[list[str | None]]
    unmapped: list[str]
    warnings: list[str]

    @classmethod
    def of(cls, upload: BomUpload) -> "UploadPreview":
        return cls(
            upload_id=upload.id,
            filename=upload.filename,
            sheets=upload.sheets,
            selected_sheet=upload.selected_sheet,
            header_row=upload.header_row,
            data_rows=upload.data_rows,
            proposed_mapping=[MappingColumn.model_validate(m.model_dump()) for m in upload.mapping],
            preview_rows=upload.preview_rows,
            unmapped=[m.header for m in upload.mapping if m.field is None and m.header],
            warnings=upload.warnings,
        )


class MappingChoiceIn(ApiModel):
    column_index: int = Field(ge=0)
    field: BomField | None


class MappingConfirm(ApiModel):
    upload_id: str
    mapping: list[MappingChoiceIn] = Field(
        description="Overrides by column; columns not listed keep the proposed field"
    )
    sheet: str | None = None
    header_row: int | None = Field(default=None, ge=1)


class JobAccepted(ApiModel):
    job_id: str


class LinePage(ApiModel):
    items: list[BomLine]
    issue_counts: dict[str, int]
    next_cursor: str | None = None
