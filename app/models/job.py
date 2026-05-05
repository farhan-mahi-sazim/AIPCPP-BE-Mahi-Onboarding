from datetime import datetime, timezone
from typing import Optional, Dict, Any
from uuid import UUID, uuid4
from sqlmodel import Field, SQLModel, Relationship, Column, JSON, DateTime
from app.common.enums.job_status import EJobStatus
from app.common.enums.pipeline_stage import EPipelineStage


class ProcessingJob(SQLModel, table=True):
    __tablename__ = "processing_jobs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    document_id: UUID = Field(foreign_key="documents.id", index=True)

    status: EJobStatus = Field(default=EJobStatus.PENDING)
    stage: Optional[EPipelineStage] = None

    retry_count: int = Field(default=0)
    celery_task_id: Optional[str] = None

    # Store errors, stack traces, and intermediate metadata
    error_log: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    job_metadata: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
    )

    # Relationships
    document: "Document" = Relationship(back_populates="jobs")
