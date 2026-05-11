from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class TPaginationParams(BaseModel):
    page: int = Field(
        default=1, ge=1, description="Page number (1-indexed, default: 1)"
    )
    page_size: int = Field(
        default=20, ge=1, le=100, description="Items per page (max: 100, default: 20)"
    )
    sort_by: str | None = Field(
        default=None, description="Field name to sort by (prefix with - for descending)"
    )

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


class TPaginatedResponse(BaseModel):
    data: list[Any]
    total: int = Field(description="Total number of items across all pages")
    page: int = Field(description="Current page number")
    page_size: int = Field(description="Items per page")
    total_pages: int = Field(description="Total number of pages")

    @classmethod
    def create(
        cls, data: list[Any], total: int, page: int, page_size: int
    ) -> TPaginatedResponse:
        total_pages = (total + page_size - 1) // page_size
        return cls(
            data=data,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
