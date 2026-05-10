import uuid

from app.common.enums.version_source import EVersionSource
from app.models.document import Document, DocumentVersion
from tests.content.helpers import ensure_user_exists


class TestVersionsE2E:
    async def test_get_timeline_success(self, client, db_session):
        user = await ensure_user_exists(db_session)
        doc = Document(
            id=uuid.uuid4(),
            owner_id=user.id,
            filename="test.txt",
            s3_key="key",
            file_type="text",
        )
        db_session.add(doc)
        await db_session.flush()

        v1 = DocumentVersion(
            document_id=doc.id,
            version_number=1,
            data={"summary": "v1"},
            source=EVersionSource.AI,
        )
        db_session.add(v1)
        await db_session.flush()
        doc.current_version_id = v1.id
        await db_session.commit()

        response = await client.get(f"/api/v1/versions/{doc.id}/timeline")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["version_number"] == 1

    async def test_create_override_success(self, client, db_session):
        user = await ensure_user_exists(db_session)
        doc = Document(
            id=uuid.uuid4(),
            owner_id=user.id,
            filename="test.txt",
            s3_key="key",
            file_type="text",
        )
        db_session.add(doc)
        await db_session.flush()

        v1 = DocumentVersion(
            document_id=doc.id,
            version_number=1,
            data={"summary": "v1"},
            source=EVersionSource.AI,
        )
        db_session.add(v1)
        await db_session.flush()
        doc.current_version_id = v1.id
        await db_session.commit()

        payload = {"data": {"summary": "human summary", "tags": ["human"]}}
        response = await client.post(
            f"/api/v1/versions/{doc.id}/override", json=payload
        )
        assert response.status_code == 200
        data = response.json()
        assert data["version_number"] == 2
        assert data["source"] == EVersionSource.HUMAN

    async def test_edit_version_success(self, client, db_session):
        user = await ensure_user_exists(db_session)
        doc = Document(
            id=uuid.uuid4(),
            owner_id=user.id,
            filename="test.txt",
            s3_key="key",
            file_type="text",
        )
        db_session.add(doc)
        await db_session.flush()

        v1 = DocumentVersion(
            document_id=doc.id,
            version_number=1,
            data={"summary": "v1"},
            source=EVersionSource.HUMAN,
        )
        db_session.add(v1)
        await db_session.commit()

        payload = {"data": {"summary": "edited summary"}}
        response = await client.patch(f"/api/v1/versions/version/{v1.id}", json=payload)
        assert response.status_code == 200
        assert response.json()["data"]["summary"] == "edited summary"

    async def test_delete_version_success(self, client, db_session):
        user = await ensure_user_exists(db_session)
        doc = Document(
            id=uuid.uuid4(),
            owner_id=user.id,
            filename="test.txt",
            s3_key="key",
            file_type="text",
        )
        db_session.add(doc)
        await db_session.flush()

        v1 = DocumentVersion(
            document_id=doc.id,
            version_number=1,
            data={"summary": "v1"},
            source=EVersionSource.HUMAN,
        )
        db_session.add(v1)
        await db_session.commit()

        response = await client.delete(f"/api/v1/versions/version/{v1.id}")
        assert response.status_code == 204

        # Verify gone
        check = await client.get(f"/api/v1/versions/{doc.id}/timeline")
        assert len(check.json()["items"]) == 0

    async def test_pagination(self, client, db_session):
        user = await ensure_user_exists(db_session)
        doc = Document(
            id=uuid.uuid4(),
            owner_id=user.id,
            filename="test.txt",
            s3_key="key",
            file_type="text",
        )
        db_session.add(doc)
        await db_session.flush()

        for i in range(5):
            v = DocumentVersion(
                document_id=doc.id,
                version_number=i + 1,
                data={"summary": f"v{i + 1}"},
                source=EVersionSource.AI,
            )
            db_session.add(v)
        await db_session.commit()

        response = await client.get(
            f"/api/v1/versions/{doc.id}/timeline?limit=2&offset=0"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["limit"] == 2
        assert data["offset"] == 0
