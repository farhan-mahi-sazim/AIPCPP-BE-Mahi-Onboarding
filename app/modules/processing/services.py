import io
import json
import logging
import uuid

import litellm
import pytesseract
from PIL import Image
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.common.enums.file_type import EFileType
from app.common.enums.job_status import EJobStatus
from app.common.enums.pipeline_stage import EPipelineStage
from app.common.enums.version_source import EVersionSource
from app.common.storage import StorageService
from app.config.settings import settings
from app.models.document import DocumentChunk, DocumentVersion
from app.modules.content.repositories import (
    DocumentChunkRepositorySync,
    DocumentRepositorySync,
    DocumentVersionRepositorySync,
    ProcessingJobRepositorySync,
)
from app.modules.processing.prompts import ANALYSIS_SYSTEM_PROMPT, ANALYSIS_USER_PROMPT

logger = logging.getLogger(__name__)


class ProcessingService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.doc_repo = DocumentRepositorySync(session)
        self.job_repo = ProcessingJobRepositorySync(session)
        self.version_repo = DocumentVersionRepositorySync(session)
        self.chunk_repo = DocumentChunkRepositorySync(session)
        self.storage = StorageService()

    def process_extraction(self, document_id: uuid.UUID) -> str:
        doc = self.doc_repo.get_by_id(document_id)
        if not doc:
            raise ValueError(f"Document {document_id} not found")

        if doc.raw_text:
            logger.info(
                "Document %s already has raw text, skipping extraction", document_id
            )
            return str(document_id)

        job = self.job_repo.get_by_document_id(document_id)
        if job:
            job.stage = EPipelineStage.EXTRACTION
            job.status = EJobStatus.PROCESSING
            self.session.commit()

        file_content = self.storage.get_file_content(doc.s3_key)

        extracted_text = ""
        if doc.file_type == EFileType.PDF:
            reader = PdfReader(io.BytesIO(file_content))
            for page in reader.pages:
                extracted_text += page.extract_text() + "\n"
        elif doc.file_type == EFileType.IMAGE:
            try:
                image = Image.open(io.BytesIO(file_content))
                extracted_text = pytesseract.image_to_string(image)
            except pytesseract.TesseractNotFoundError:
                logger.warning(
                    "Tesseract OCR not available for document %s. "
                    "Install with: brew install tesseract",
                    document_id,
                )
                extracted_text = f"[OCR unavailable for {doc.filename}]"
            except Exception as e:
                logger.error("Image OCR failed for document %s: %s", document_id, e)
                extracted_text = f"[Image extraction failed: {str(e)[:100]}]"
        elif doc.file_type == EFileType.TEXT:
            extracted_text = file_content.decode("utf-8")

        doc.raw_text = extracted_text
        self.session.commit()

        logger.info("Extraction completed for document %s", document_id)
        return str(document_id)

    def process_ai_analysis(self, document_id: uuid.UUID) -> str:
        doc = self.doc_repo.get_by_id(document_id)
        if not doc or not doc.raw_text:
            raise ValueError(f"Document {document_id} has no extracted text")

        job = self.job_repo.get_by_document_id(document_id)
        if job:
            job.stage = EPipelineStage.AI_TASK
            self.session.commit()

        models_to_try = [
            settings.LITELLM_MODEL,
            "gemini/gemini-2.0-flash",
            "gemini/gemini-pro-latest",
        ]

        last_exception = None
        for model_name in models_to_try:
            try:
                logger.info("Attempting AI Analysis with model: %s", model_name)
                response = litellm.completion(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": ANALYSIS_USER_PROMPT.format(
                                text=doc.raw_text[:8000]
                            ),
                        },
                    ],
                    response_format={"type": "json_object"},
                    timeout=settings.AI_ANALYSIS_TIMEOUT_SECONDS,
                )

                analysis_data = json.loads(response.choices[0].message.content)

                if job:
                    job.job_metadata = {
                        "usage": response.usage.to_dict(),
                        "category": analysis_data.get("category"),
                        "model_used": model_name,
                    }

                ai_version = DocumentVersion(
                    document_id=document_id,
                    version_number=1,
                    data={
                        "summary": analysis_data.get("summary"),
                        "tags": analysis_data.get("tags"),
                    },
                    source=EVersionSource.AI,
                )
                self.version_repo.create(ai_version)

                doc.current_version_id = ai_version.id
                self.session.commit()

                logger.info(
                    "AI Analysis completed for document %s using %s",
                    document_id,
                    model_name,
                )
                return str(document_id)

            except Exception as e:
                logger.warning(
                    "Model %s failed: %s. Trying next in chain...", model_name, e
                )
                last_exception = e
                continue

        logger.error("All models in fallback chain failed for %s", document_id)
        raise last_exception

    def _chunk_text(
        self, text: str, chunk_size: int = 1000, overlap: int = 200
    ) -> list[str]:
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunks.append(text[start:end])
            start += chunk_size - overlap
        return chunks

    def process_embeddings(self, document_id: uuid.UUID) -> str:
        doc = self.doc_repo.get_by_id(document_id)
        if not doc or not doc.raw_text:
            raise ValueError(f"Document {document_id} has no extracted text")

        job = self.job_repo.get_by_document_id(document_id)
        if job:
            job.stage = EPipelineStage.EMBEDDING
            self.session.commit()

        self.chunk_repo.delete_by_document_id(document_id)

        text_chunks = self._chunk_text(doc.raw_text)

        embedding_models = [
            settings.LITELLM_EMBEDDING_MODEL,
            "gemini/gemini-embedding-001",
        ]

        last_exception = None
        for model_name in embedding_models:
            try:
                logger.info("Attempting Embeddings with model: %s", model_name)
                response = litellm.embedding(
                    model=model_name,
                    input=text_chunks,
                    timeout=settings.MODEL_EMBEDDING_TIMEOUT_SECONDS,  # 20 second timeout
                )

                embeddings = [r["embedding"] for r in response.data]

                db_chunks = [
                    DocumentChunk(
                        id=uuid.uuid4(),
                        document_id=document_id,
                        chunk_index=i,
                        content=text_chunks[i],
                        embedding=embeddings[i],
                    )
                    for i in range(len(text_chunks))
                ]

                self.chunk_repo.create_many(db_chunks)

                if job:
                    job.status = EJobStatus.COMPLETED
                    job.stage = EPipelineStage.PERSISTENCE

                self.session.commit()

                logger.info(
                    "Embedding generation completed for document %s using %s",
                    document_id,
                    model_name,
                )
                return str(document_id)

            except Exception as e:
                logger.warning(
                    "Embedding model %s failed: %s. Trying next...", model_name, e
                )
                last_exception = e
                continue

        logger.error("All embedding models failed for %s", document_id)
        raise last_exception
