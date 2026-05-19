import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.common.enums.file_type import EFileType
from app.common.enums.version_source import EVersionSource
from app.models.document import Document, DocumentVersion
from app.models.user import User
from tests.content.constants import DUMMY_USER_ID, TEST_EMAIL, TEST_FULL_NAME


async def ensure_user_exists(db_session: AsyncSession) -> User:
    """Ensures the dummy test user exists in the test database."""
    result = await db_session.execute(select(User).where(User.id == DUMMY_USER_ID))
    user = result.scalar_one_or_none()
    if not user:
        user = User(
            id=DUMMY_USER_ID,
            email=TEST_EMAIL,
            hashed_password="hashed-password",
            full_name=TEST_FULL_NAME,
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()
    return user


async def create_document_with_summary(
    db_session: AsyncSession,
    owner_id: uuid.UUID = DUMMY_USER_ID,
    filename: str = "test_doc.pdf",
    file_type: EFileType = EFileType.PDF,
    summary_text: str = "Test summary",
    tags: list[str] | None = None,
) -> tuple[Document, DocumentVersion]:
    """
    Create a test document with a summary version.
    Returns (document, version) tuple.
    """
    if tags is None:
        tags = ["test", "summary"]

    # Create document
    doc_id = uuid.uuid4()
    document = Document(
        id=doc_id,
        owner_id=owner_id,
        filename=filename,
        s3_key=f"{owner_id}/{doc_id}/{filename}",
        file_type=file_type,
    )
    db_session.add(document)
    await db_session.flush()

    # Create document version with summary
    version = DocumentVersion(
        id=uuid.uuid4(),
        document_id=doc_id,
        version_number=1,
        source=EVersionSource.AI,
        data={"summary": summary_text, "tags": tags},
        created_at=datetime.now(UTC),
    )
    db_session.add(version)
    await db_session.flush()

    # Link version to document
    document.current_version_id = version.id
    await db_session.flush()
    await db_session.refresh(document)
    await db_session.refresh(version)
    await db_session.commit()

    return document, version


async def create_document_without_summary(
    db_session: AsyncSession,
    owner_id: uuid.UUID = DUMMY_USER_ID,
    filename: str = "test_doc_no_summary.pdf",
    file_type: EFileType = EFileType.PDF,
) -> Document:
    """
    Create a test document without a summary version.
    Returns document.
    """
    doc_id = uuid.uuid4()
    document = Document(
        id=doc_id,
        owner_id=owner_id,
        filename=filename,
        s3_key=f"{owner_id}/{doc_id}/{filename}",
        file_type=file_type,
    )
    db_session.add(document)
    await db_session.flush()
    await db_session.refresh(document)
    await db_session.commit()
    return document
