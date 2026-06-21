from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.cache.constants import (
    CACHE_VERSION_TTL,
    ECacheKeyPrefix,
)
from app.common.cache.decorators import cache_invalidate, cached
from app.common.enums.version_source import EVersionSource
from app.models.document import Document, DocumentVersion
from app.modules.content.services import ContentDocumentService
from app.modules.versions.schemas import (
    TPaginatedResponse,
    TVersionOverride,
    TVersionRead,
    TVersionUpdate,
)


class VersionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.content_service = ContentDocumentService(session)
        self.version_repo = self.content_service.version_repo

    @cached(
        prefix=ECacheKeyPrefix.VERSION.value,
        ttl=CACHE_VERSION_TTL,
    )
    async def get_timeline(
        self, document_id: UUID, limit: int = 10, offset: int = 0
    ) -> TPaginatedResponse[TVersionRead]:
        doc = await self.content_service.get_document(document_id)
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
            )

        versions, total = await self.content_service.get_versions_by_document_id(
            document_id, limit, offset
        )

        return TPaginatedResponse(
            items=[TVersionRead.model_validate(v) for v in versions],
            total=total,
            limit=limit,
            offset=offset,
        )

    @cache_invalidate(ECacheKeyPrefix.VERSION.value)
    async def create_human_override(
        self, document_id: UUID, override: TVersionOverride, user_id: UUID
    ) -> TVersionRead:
        doc = await self.content_service.get_document(document_id)
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
            )

        latest_version = await self.content_service.get_latest_version(document_id)
        next_version_number = (
            (latest_version.version_number + 1) if latest_version else 1
        )
        parent_id = latest_version.id if latest_version else None

        new_version = DocumentVersion(
            document_id=document_id,
            version_number=next_version_number,
            data=override.data,
            source=EVersionSource.HUMAN,
            parent_version_id=parent_id,
            created_by=user_id,
        )

        created = await self.content_service.create_version(new_version)

        doc.current_version_id = created.id
        await self.session.commit()

        return TVersionRead.model_validate(created)

    @cache_invalidate(ECacheKeyPrefix.VERSION.value)
    async def update_human_version(
        self, version_id: UUID, update_data: TVersionUpdate
    ) -> TVersionRead:
        version = await self.content_service.get_version(version_id)
        if not version:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Version not found"
            )

        if version.source != EVersionSource.HUMAN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only human-generated versions can be edited directly.",
            )

        version.data = {**version.data, **update_data.data}

        updated = await self.content_service.update_version(version)
        await self.session.commit()

        return TVersionRead.model_validate(updated)

    async def _delete_child_versions(
        self,
        version_id: UUID,
        all_versions: list[DocumentVersion],
        doc: Document,
    ) -> None:
        """Recursively delete all descendant versions (children before parent)."""
        children = [v for v in all_versions if v.parent_version_id == version_id]
        for child in children:
            await self._delete_child_versions(child.id, all_versions, doc)
            if doc.current_version_id == child.id:
                doc.current_version_id = None
                await self.session.flush()
            await self.content_service.delete_version(child)

    @cache_invalidate(ECacheKeyPrefix.VERSION.value)
    async def delete_version(self, version_id: UUID) -> None:
        version = await self.content_service.get_version(version_id)
        if not version:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Version not found"
            )

        if version.source != EVersionSource.HUMAN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only human-generated versions can be deleted.",
            )

        doc = await self.content_service.get_document(version.document_id)

        all_versions, _ = await self.content_service.get_versions_by_document_id(
            doc.id, limit=1000
        )

        await self._delete_child_versions(version_id, all_versions, doc)

        if doc and doc.current_version_id == version_id:
            remaining = [v for v in all_versions if v.id != version_id]
            remaining.sort(key=lambda v: v.version_number, reverse=True)
            doc.current_version_id = remaining[0].id if remaining else None
            await self.session.flush()

        await self.content_service.delete_version(version)
        await self.session.commit()
