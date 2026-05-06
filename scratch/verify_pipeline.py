import asyncio
import uuid
import time
from sqlalchemy.ext.asyncio import AsyncSession
from app.config.db import AsyncSessionLocal
from app.modules.content.services import ContentService
from app.modules.content.repositories import DocumentRepository, ProcessingJobRepository
from app.common.storage import StorageService
from app.common.enums.job_status import EJobStatus
from fastapi import UploadFile
import io


async def verify_pipeline():
    print("🚀 Starting Pipeline Verification...")

    # 1. Setup
    async with AsyncSessionLocal() as session:
        storage = StorageService()
        content_service = ContentService(session, storage)
        job_repo = ProcessingJobRepository(session)

        # 1.1 Create Test User (to avoid FK violation)
        from app.models.user import User

        owner_id = uuid.uuid4()
        test_user = User(
            id=owner_id,
            email=f"test_{owner_id.hex[:8]}@example.com",
            hashed_password="mock_password",
            full_name="Test User",
        )
        session.add(test_user)
        await session.commit()
        print(f"👤 Created Test User: {test_user.email}")

        # 2. Mock File Upload
        print("📁 Uploading test file...")
        test_content = b"This is a test document about artificial intelligence. It explains how neural networks work."
        test_file = UploadFile(
            file=io.BytesIO(test_content),
            filename="test_ai.txt",
            size=len(test_content),
        )

        response = await content_service.upload_document(test_file, owner_id=owner_id)
        doc_id = response.document.id
        print(f"✅ Uploaded! Document ID: {doc_id}")

        # 3. Wait for Background Job
        print("⏳ Waiting for Celery worker (max 30s)...")
        start_time = time.time()
        while time.time() - start_time < 30:
            # Refresh session to get latest DB state
            async with AsyncSessionLocal() as check_session:
                check_job_repo = ProcessingJobRepository(check_session)
                job = await check_job_repo.get_by_document_id(doc_id)

                if not job:
                    print("Still waiting for job record...")
                elif job.status == EJobStatus.COMPLETED:
                    print(f"🎉 Job COMPLETED in {int(time.time() - start_time)}s!")

                    # 4. Check results
                    from app.models.document import DocumentVersion
                    from sqlalchemy import select

                    stmt = select(DocumentVersion).where(
                        DocumentVersion.document_id == doc_id
                    )
                    result = await check_session.execute(stmt)
                    version = result.scalar_one_or_none()

                    if version:
                        print("\n--- AI SUMMARY ---")
                        print(version.data.get("summary"))
                        print("--- TAGS ---")
                        print(version.data.get("tags"))
                        return
                    else:
                        print("❌ Job marked completed but no AI version found!")
                        return

                elif job.status == EJobStatus.FAILED:
                    print(f"❌ Job FAILED: {job.error_log}")
                    return

                print(f"Current Stage: {job.stage}...")
                await asyncio.sleep(2)

        print("⏰ Timeout: Job took too long or worker is not running.")


if __name__ == "__main__":
    asyncio.run(verify_pipeline())
