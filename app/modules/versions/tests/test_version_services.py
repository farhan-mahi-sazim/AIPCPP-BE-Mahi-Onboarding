import uuid

import pytest

from app.common.enums.file_type import EFileType
from app.common.enums.version_source import EVersionSource
from app.models.document import Document, DocumentVersion
from app.models.user import User
from app.modules.versions.schemas import TVersionOverride, TVersionUpdate
from app.modules.versions.services import VersionService


class TestVersionService:
    @pytest.fixture
    def service(self, db_session):
        return VersionService(db_session)

    @pytest.fixture
    async def sample_user(self, db_session):
        user = User(
            id=uuid.uuid4(),
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            hashed_password="hashed",
            full_name="Test User",
        )
        db_session.add(user)
        await db_session.flush()
        return user

    @pytest.fixture
    async def sample_doc(self, db_session, sample_user):
        doc = Document(
            id=uuid.uuid4(),
            owner_id=sample_user.id,
            filename="test.txt",
            s3_key="key",
            file_type=EFileType.TEXT,
        )
        db_session.add(doc)
        await db_session.flush()
        return doc

    @pytest.fixture
    async def ai_version(self, db_session, sample_doc):
        version = DocumentVersion(
            document_id=sample_doc.id,
            version_number=1,
            data={"summary": "AI summary", "category": "General"},
            source=EVersionSource.AI,
        )
        db_session.add(version)
        await db_session.flush()
        sample_doc.current_version_id = version.id
        await db_session.flush()
        return version

    async def test_get_timeline_success(self, service, sample_doc, ai_version):
        response = await service.get_timeline(sample_doc.id)
        assert len(response.items) == 1
        assert response.items[0].version_number == 1
        assert response.items[0].source == EVersionSource.AI

    async def test_create_human_override(
        self, service, sample_doc, ai_version, sample_user
    ):
        override = TVersionOverride(data={"summary": "Human summary", "tags": ["tag1"]})

        new_version = await service.create_human_override(
            sample_doc.id, override, sample_user.id
        )

        assert new_version.version_number == 2
        assert new_version.source == EVersionSource.HUMAN
        assert new_version.data["summary"] == "Human summary"
        assert new_version.parent_version_id == ai_version.id

        # Verify document updated
        await service.session.refresh(sample_doc)
        assert sample_doc.current_version_id == new_version.id

    async def test_update_human_version_success(self, service, db_session, sample_doc):
        # Create a human version first
        human_version = DocumentVersion(
            document_id=sample_doc.id,
            version_number=2,
            data={"summary": "Old summary"},
            source=EVersionSource.HUMAN,
        )
        db_session.add(human_version)
        await db_session.flush()

        update = TVersionUpdate(data={"summary": "New summary"})
        updated = await service.update_human_version(human_version.id, update)

        assert updated.data["summary"] == "New summary"

    async def test_delete_version_success(
        self, service, db_session, sample_doc, ai_version, sample_user
    ):
        # Create a human version
        human_version = DocumentVersion(
            document_id=sample_doc.id,
            version_number=2,
            data={"summary": "To delete"},
            source=EVersionSource.HUMAN,
        )
        db_session.add(human_version)
        await db_session.flush()
        sample_doc.current_version_id = human_version.id
        await db_session.flush()

        await service.delete_version(human_version.id)

        # Verify document current_version rolled back to AI version
        await service.session.refresh(sample_doc)
        assert sample_doc.current_version_id == ai_version.id

        # Verify version is gone
        v = await service.version_repo.get_by_id(human_version.id)
        assert v is None
