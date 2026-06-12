from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums.file_type import EFileType
from app.models.document import Document, DocumentChunk, DocumentVersion
from app.models.user import User
from app.modules.search.tests.constants import DUMMY_USER_ID


async def ensure_user_exists(db_session: AsyncSession):
    """Ensures the dummy test user exists in the test database."""
    result = await db_session.execute(select(User).where(User.id == DUMMY_USER_ID))
    user = result.scalar_one_or_none()
    if not user:
        user = User(
            id=DUMMY_USER_ID,
            email="test@example.com",
            hashed_password="hashed-password",
            full_name="Test User",
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()
    return user


async def create_document_with_chunks(
    db_session: AsyncSession,
    owner_id: uuid4,
    document_id: uuid4,
    filename: str,
    chunks_content: list[str],
    embeddings: list[list[float]],
) -> Document:
    """Creates a document with document chunks for testing search."""
    doc = Document(
        id=document_id,
        owner_id=owner_id,
        filename=filename,
        s3_key=f"{owner_id}/{document_id}/{filename}",
        file_type=EFileType.PDF,
        raw_text=" ".join(chunks_content),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(doc)
    await db_session.flush()

    version = DocumentVersion(
        id=uuid4(),
        document_id=document_id,
        version_number=1,
        data={"summary": "Test summary", "category": "Invoice", "tags": ["test"]},
        source="AI",
        created_at=datetime.now(UTC),
    )
    db_session.add(version)
    await db_session.flush()

    doc.current_version_id = version.id

    for i, (content, embedding) in enumerate(zip(chunks_content, embeddings)):
        chunk = DocumentChunk(
            id=uuid4(),
            document_id=document_id,
            chunk_index=i,
            content=content,
            embedding=embedding,
            created_at=datetime.now(UTC),
        )
        db_session.add(chunk)

    await db_session.commit()
    return doc
