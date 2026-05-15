from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.cache.constants import (
    CACHE_VERSION_TTL,
    ECacheKeyPrefix,
)
from app.common.cache.decorators import cache_invalidate, cached
from app.common.enums.version_source import EVersionSource
from app.models.document import DocumentVersion
from app.modules.content.repositories import (
    DocumentRepository,
    DocumentVersionRepository,
)
from app.modules.versions.schemas import (
    TPaginatedResponse,
    TVersionOverride,
    TVersionRead,
    TVersionUpdate,
)


class VersionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.doc_repo = DocumentRepository(session)
        self.version_repo = DocumentVersionRepository(session)

    @cached(
        prefix=ECacheKeyPrefix.VERSION.value,
        ttl=CACHE_VERSION_TTL,
    )
    async def get_timeline(
        self, document_id: UUID, limit: int = 10, offset: int = 0
    ) -> TPaginatedResponse[TVersionRead]:
        doc = await self.doc_repo.get_by_id(document_id)
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
            )

        versions = await self.version_repo.get_all_by_document_id(
            document_id, limit, offset
        )

        return TPaginatedResponse(
            items=[TVersionRead.model_validate(v) for v in versions],
            total=len(versions),
            limit=limit,
            offset=offset,
        )

    @cache_invalidate(ECacheKeyPrefix.VERSION.value)
    async def create_human_override(
        self, document_id: UUID, override: TVersionOverride, user_id: UUID
    ) -> TVersionRead:
        doc = await self.doc_repo.get_by_id(document_id)
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
            )

        latest_version = await self.version_repo.get_latest_by_document_id(document_id)
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

        created = await self.version_repo.create(new_version)

        doc.current_version_id = created.id
        await self.session.commit()

        return TVersionRead.model_validate(created)

    @cache_invalidate(ECacheKeyPrefix.VERSION.value)
    async def update_human_version(
        self, version_id: UUID, update_data: TVersionUpdate, user_id: UUID
    ) -> TVersionRead:
        version = await self.version_repo.get_by_id(version_id)
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

        updated = await self.version_repo.update(version)
        await self.session.commit()

        return TVersionRead.model_validate(updated)

    @cache_invalidate(ECacheKeyPrefix.VERSION.value)
    async def delete_version(self, version_id: UUID, user_id: UUID) -> None:
        version = await self.version_repo.get_by_id(version_id)
        if not version:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Version not found"
            )

        if version.source != EVersionSource.HUMAN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only human-generated versions can be deleted.",
            )

        doc = await self.doc_repo.get_by_id(version.document_id)

        # If this was the current version, roll back current_version_id
        if doc and doc.current_version_id == version_id:
            # Find the previous version
            all_versions = await self.version_repo.get_all_by_document_id(
                doc.id, limit=2
            )
            previous_version = None
            for v in all_versions:
                if v.id != version_id:
                    previous_version = v
                    break

            doc.current_version_id = previous_version.id if previous_version else None
            await self.session.flush()

        await self.session.delete(version)
        await self.session.commit()
