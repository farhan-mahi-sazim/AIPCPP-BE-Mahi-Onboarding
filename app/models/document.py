from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID, uuid4

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql
from sqlmodel import JSON, Column, DateTime, Field, Relationship, SQLModel

from app.common.enums.file_type import EFileType
from app.common.enums.version_source import EVersionSource
from app.config.settings import settings

if TYPE_CHECKING:
    from .job import ProcessingJob
    from .user import User


class Document(SQLModel, table=True):
    __tablename__ = "documents"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    owner_id: UUID = Field(foreign_key="users.id", index=True)
    filename: str
    s3_key: str
    file_type: EFileType
    raw_text: str | None = Field(default=None, sa_column=Column(Text))

    current_version_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_versions.id", ondelete="SET NULL"),
        ),
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True)),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True)),
    )

    # Relationships
    owner: "User" = Relationship(back_populates="documents")
    versions: list["DocumentVersion"] = Relationship(
        back_populates="document",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "primaryjoin": "Document.id==DocumentVersion.document_id",
        },
    )
    chunks: list["DocumentChunk"] = Relationship(
        back_populates="document",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    jobs: list["ProcessingJob"] = Relationship(
        back_populates="document",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class DocumentVersion(SQLModel, table=True):
    __tablename__ = "document_versions"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    document_id: UUID = Field(foreign_key="documents.id", index=True)
    version_number: int

    # Flexible schema for summary, tags, category
    data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    source: EVersionSource
    parent_version_id: UUID | None = Field(
        default=None, foreign_key="document_versions.id"
    )

    created_by: UUID | None = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True)),
    )

    # Relationships
    document: "Document" = Relationship(
        back_populates="versions",
        sa_relationship_kwargs={
            "primaryjoin": "DocumentVersion.document_id==Document.id"
        },
    )
    creator: Optional["User"] = Relationship(back_populates="versions")


class DocumentChunk(SQLModel, table=True):
    __tablename__ = "document_chunks"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    document_id: UUID = Field(foreign_key="documents.id", index=True)
    chunk_index: int
    content: str = Field(sa_column=Column(Text))

    # Semantic Search Layer (1536 is standard for OpenAI embeddings)
    embedding: Any = Field(sa_column=Column(Vector(settings.EMBEDDING_DIMENSION)))

    chunk_metadata: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True)),
    )

    # Relationships
    document: "Document" = Relationship(back_populates="chunks")
