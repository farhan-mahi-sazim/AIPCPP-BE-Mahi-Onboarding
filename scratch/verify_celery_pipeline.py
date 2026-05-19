import asyncio
import io
import time
import uuid

from fastapi import UploadFile

from app.common.enums.job_status import EJobStatus
from app.common.storage import StorageService
from app.config.db import AsyncSessionLocal
from app.modules.content.repositories import ProcessingJobRepository
from app.modules.content.services import ContentService


async def test_pipeline():
    print("🚀 Starting Pipeline Test...")

    async with AsyncSessionLocal() as session:
        storage = StorageService()
        content_service = ContentService(session, storage)

        # 1. Ensure a user exists
        from sqlalchemy import select

        from app.models.user import User

        result = await session.execute(select(User).limit(1))
        user = result.scalar_one_or_none()

        if not user:
            owner_id = uuid.uuid4()
            user = User(
                id=owner_id,
                email=f"test_{owner_id.hex[:8]}@example.com",
                hashed_password="mock_password",
                full_name="Test User",
            )
            session.add(user)
            await session.commit()
            print(f"👤 Created Test User: {user.email}")
        else:
            owner_id = user.id
            print(f"👤 Using Existing User: {user.email}")

        # 2. Upload test file
        print("📁 Uploading test file...")
        test_content = b"Artificial Intelligence (AI) is intelligence demonstrated by machines, as opposed to the natural intelligence displayed by humans or animals. Leading AI textbooks define the field as the study of 'intelligent agents'."
        test_file = UploadFile(
            file=io.BytesIO(test_content),
            filename="test_parallel.txt",
            size=len(test_content),
        )

        response = await content_service.upload_document(test_file, owner_id=owner_id)
        doc_id = response.document.id
        print(f"✅ Uploaded! Document ID: {doc_id}")
        print("⏳ Waiting for pipeline processing (check celery logs)...")

        # 3. Monitor Job
        start_time = time.time()
        while time.time() - start_time < 60:
            async with AsyncSessionLocal() as check_session:
                job_repo = ProcessingJobRepository(check_session)
                job = await job_repo.get_by_document_id(doc_id)

                if job:
                    print(f"Status: {job.status} | Stage: {job.stage}")
                    if job.status == EJobStatus.COMPLETED:
                        print(
                            f"🎉 Pipeline COMPLETED in {int(time.time() - start_time)}s!"
                        )

                        # Verify results
                        from app.models.document import DocumentChunk, DocumentVersion

                        v_result = await check_session.execute(
                            select(DocumentVersion).where(
                                DocumentVersion.document_id == doc_id
                            )
                        )
                        version = v_result.scalar_one_or_none()

                        c_result = await check_session.execute(
                            select(DocumentChunk).where(
                                DocumentChunk.document_id == doc_id
                            )
                        )
                        chunks = c_result.scalars().all()

                        if version:
                            print("\n--- AI SUMMARY ---")
                            print(version.data.get("summary"))

                        if chunks:
                            print("\n--- VECTOR CHUNKS ---")
                            print(f"Generated {len(chunks)} chunks with embeddings.")

                        return
                    elif job.status == EJobStatus.FAILED:
                        print(f"❌ Job FAILED: {job.error_log}")
                        return

                await asyncio.sleep(3)

        print("⏰ Timeout: Pipeline processing took too long.")


if __name__ == "__main__":
    asyncio.run(test_pipeline())
