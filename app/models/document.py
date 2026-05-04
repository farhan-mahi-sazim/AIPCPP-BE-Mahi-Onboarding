from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4
from sqlmodel import Field, SQLModel, Relationship, Column, JSON
from sqlalchemy import Text
from pgvector.sqlalchemy import Vector
from app.common.enums.file_type import EFileType
from app.common.enums.version_source import EVersionSource


class Document(SQLModel, table=True):
    __tablename__ = "documents"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    owner_id: UUID = Field(foreign_key="users.id", index=True)
    filename: str
    s3_key: str
    file_type: EFileType
    raw_text: Optional[str] = Field(default=None, sa_column=Column(Text))

    # Version Pointer for Performance
    current_version_id: Optional[UUID] = Field(
        default=None, foreign_key="document_versions.id"
    )

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    owner: "User" = Relationship(back_populates="documents")
    versions: List["DocumentVersion"] = Relationship(
        back_populates="document",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "primaryjoin": "Document.id==DocumentVersion.document_id",
        },
    )
    chunks: List["DocumentChunk"] = Relationship(
        back_populates="document",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    jobs: List["ProcessingJob"] = Relationship(
        back_populates="document",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class DocumentVersion(SQLModel, table=True):
    __tablename__ = "document_versions"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    document_id: UUID = Field(foreign_key="documents.id", index=True)
    version_number: int

    # Flexible schema for summary, tags, category
    data: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    source: EVersionSource
    parent_version_id: Optional[UUID] = Field(
        default=None, foreign_key="document_versions.id"
    )

    created_by: Optional[UUID] = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    document: Document = Relationship(
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
    embedding: Any = Field(sa_column=Column(Vector(1536)))

    metadata: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    document: Document = Relationship(back_populates="chunks")
