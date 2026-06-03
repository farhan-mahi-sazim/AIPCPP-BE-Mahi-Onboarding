from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlmodel import JSON, Column, DateTime, Field, Relationship, SQLModel

from app.common.enums.job_status import EJobStatus
from app.common.enums.pipeline_stage import EPipelineStage

if TYPE_CHECKING:
    from .document import Document


class ProcessingJob(SQLModel, table=True):
    __tablename__ = "processing_jobs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    document_id: UUID = Field(foreign_key="documents.id", index=True)

    status: EJobStatus = Field(default=EJobStatus.PENDING)
    progress: int = Field(default=0, ge=0, le=100)
    stage: EPipelineStage | None = None

    retry_count: int = Field(default=0)
    celery_task_id: str | None = None

    # Store errors, stack traces, and intermediate metadata
    error_log: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    job_metadata: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True)),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True)),
    )

    # Relationships
    document: "Document" = Relationship(back_populates="jobs")
