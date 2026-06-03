from datetime import datetime
from typing import Any, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.common.enums.version_source import EVersionSource

T = TypeVar("T")


class TVersionBase(BaseModel):
    data: dict[str, Any]


class TVersionRead(TVersionBase):
    id: UUID
    document_id: UUID
    version_number: int
    source: EVersionSource
    parent_version_id: UUID | None = None
    created_by: UUID | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TVersionOverride(TVersionBase):
    """Data for creating a new version (summary, tags, category)."""

    pass


class TVersionUpdate(TVersionBase):
    """Data for updating an existing human version."""

    pass


class TPaginatedResponse[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int


class TMessageResponse(BaseModel):
    message: str
