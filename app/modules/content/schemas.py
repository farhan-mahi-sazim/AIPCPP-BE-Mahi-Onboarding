from datetime import datetime
from math import ceil
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.common.enums.file_type import EFileType
from app.common.enums.job_status import EJobStatus


class TDocumentBase(BaseModel):
    filename: str
    file_type: EFileType


class TDocumentRead(TDocumentBase):
    id: UUID
    owner_id: UUID
    s3_key: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TJobRead(BaseModel):
    id: UUID
    status: EJobStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TUploadResponse(BaseModel):
    document: TDocumentRead
    job: TJobRead
    message: str = "Upload successful. Processing started."


class TSummaryRead(BaseModel):
    document_id: UUID
    filename: str
    file_type: EFileType | None = None
    summary_title: str | None = None
    summary: str | None = None
    category: str | None = None
    tags: list[str] = []
    category: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class TPaginatedSummariesResponse(BaseModel):
    """Paginated summaries response with metadata."""

    data: list[TSummaryRead]
    total: int = Field(description="Total number of items across all pages")
    page: int = Field(description="Current page number")
    page_size: int = Field(description="Items per page")
    total_pages: int = Field(description="Total number of pages")

    @classmethod
    def create(
        cls, data: list[TSummaryRead], total: int, page: int, page_size: int
    ) -> "TPaginatedSummariesResponse":
        """Factory method to create a paginated response with calculated total_pages."""
        total_pages = ceil(total / page_size) if page_size > 0 else 0
        return cls(
            data=data,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
