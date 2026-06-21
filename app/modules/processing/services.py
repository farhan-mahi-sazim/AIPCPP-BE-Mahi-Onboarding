import io
import json
import logging
import os
import re
import tempfile
import uuid
import zipfile
from xml.etree import ElementTree

import litellm
import pytesseract
import textract
from PIL import Image
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.common.celery_sse_bridge import publish_progress_update
from app.common.embedding import LocalEmbeddingService
from app.common.enums.file_type import EFileType
from app.common.enums.job_status import EJobStatus
from app.common.enums.pipeline_stage import EPipelineStage
from app.common.enums.version_source import EVersionSource
from app.common.storage import StorageService
from app.config.settings import settings
from app.models.document import Document, DocumentChunk, DocumentVersion
from app.models.job import ProcessingJob
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

            publish_progress_update(
                document_id,
                progress=40,
                stage=EPipelineStage.EXTRACTION,
                status=EJobStatus.PROCESSING,
            )

        file_content = self.storage.get_file_content(doc.s3_key)

        try:
            extracted_text = self._get_extracted_text(doc, file_content)
        except ValueError:
            if job:
                job.status = EJobStatus.FAILED
                job.stage = EPipelineStage.PERSISTENCE
                job.progress = 0
                self.session.commit()
            raise

        doc.raw_text = extracted_text
        self.session.commit()

        if job:
            job.progress = 60
            self.session.commit()
            publish_progress_update(
                document_id,
                progress=60,
                stage=EPipelineStage.EXTRACTION,
            )

        logger.info("Extraction completed for document %s", document_id)
        return str(document_id)

    def _get_extracted_text(self, doc: Document, file_content: bytes) -> str:
        """Helper to extract text based on document file type."""
        extracted_text = ""
        if doc.file_type == EFileType.PDF:
            reader = PdfReader(io.BytesIO(file_content))
            for page in reader.pages:
                extracted_text += (page.extract_text() or "") + "\n"
        elif doc.file_type == EFileType.IMAGE:
            try:
                image = Image.open(io.BytesIO(file_content))
                extracted_text = pytesseract.image_to_string(image)
            except pytesseract.TesseractNotFoundError:
                logger.warning(
                    "Tesseract OCR not available for document %s. ",
                    doc.id,
                )
                extracted_text = f"[OCR unavailable for {doc.filename}]"
            except Exception as e:
                logger.error("Image OCR failed for document %s: %s", doc.id, e)
                extracted_text = f"[Image extraction failed: {str(e)[:100]}]"
        elif doc.file_type == EFileType.TEXT:
            extracted_text = file_content.decode("utf-8")
        elif doc.file_type == EFileType.DOCX:
            extracted_text = self._extract_docx_text(file_content)
        elif doc.file_type == EFileType.DOC:
            extracted_text = self._extract_doc_text(file_content)
        else:
            raise ValueError(f"Unsupported file type for extraction: {doc.file_type}")

        return extracted_text

    def _extract_docx_text(self, file_content: bytes) -> str:
        try:
            with zipfile.ZipFile(io.BytesIO(file_content)) as docx_zip:
                xml_bytes = docx_zip.read("word/document.xml")
        except KeyError as e:
            raise ValueError("DOCX document.xml not found") from e
        except zipfile.BadZipFile as e:
            raise ValueError("Invalid DOCX file") from e

        root = ElementTree.fromstring(xml_bytes)
        namespaces = {
            "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        }

        paragraphs: list[str] = []
        for paragraph in root.findall(".//w:p", namespaces):
            texts = [
                node.text
                for node in paragraph.findall(".//w:t", namespaces)
                if node.text
            ]
            if texts:
                paragraphs.append("".join(texts))

        return "\n".join(paragraphs)

    def _extract_doc_text(self, file_content: bytes) -> str:
        if file_content[:4] == b"PK\x03\x04":
            return self._extract_docx_text(file_content)

        try:
            with tempfile.NamedTemporaryFile(suffix=".doc", delete=False) as tmp:
                tmp.write(file_content)
                tmp_path = tmp.name

            try:
                text = textract.process(tmp_path, extension="doc")
                return text.decode("utf-8")
            finally:
                os.unlink(tmp_path)
        except Exception as e:
            raise ValueError(f"DOC extraction failed: {str(e)}") from e

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
            "gemini/gemini-2.5-flash",
            "gemini/gemini-2.0-flash",
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
                                filename=doc.filename,
                                text=doc.raw_text[:8000],
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
                        "summary_title": analysis_data.get("summary_title"),
                        "tags": analysis_data.get("tags"),
                        "category": analysis_data.get("category"),
                    },
                    source=EVersionSource.AI,
                )
                self.version_repo.create(ai_version)

                doc.current_version_id = ai_version.id
                self.session.commit()

                if job:
                    job.progress = 80
                    self.session.commit()
                publish_progress_update(
                    document_id,
                    progress=80,
                    stage=EPipelineStage.AI_TASK,
                )

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
        if last_exception:
            raise last_exception
        raise RuntimeError("No models available to try")

    def _chunk_text(
        self, text: str, chunk_size: int = 1000, overlap: int = 200
    ) -> list[str]:
        sentences = re.split(r"(?<=[.?!])\s+", text)
        sentences = [s.strip() for s in sentences if s.strip()]

        chunks: list[str] = []
        current_chunk: list[str] = []
        current_len = 0

        for sentence in sentences:
            sentence_len = len(sentence)
            if current_len + sentence_len > chunk_size and current_chunk:
                chunks.append(" ".join(current_chunk))
                overlap_sentences: list[str] = []
                overlap_len = 0
                for s in reversed(current_chunk):
                    if overlap_len + len(s) > overlap:
                        break
                    overlap_sentences.insert(0, s)
                    overlap_len += len(s)
                current_chunk = list(overlap_sentences)
                current_len = overlap_len

            current_chunk.append(sentence)
            current_len += sentence_len

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        if not chunks:
            return [text]

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

        try:
            logger.info("Attempting local Embeddings generation")
            service = LocalEmbeddingService()
            embeddings = service.embed(text_chunks)

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
                job.stage = EPipelineStage.EMBEDDING

                self.session.commit()

                if job:
                    job.progress = 90
                    self.session.commit()
                publish_progress_update(
                    document_id,
                    progress=90,
                    stage=EPipelineStage.EMBEDDING,
                )

            logger.info(
                "Embedding generation completed for document %s using local model %s",
                document_id,
                settings.LOCAL_EMBEDDING_MODEL,
            )
            return str(document_id)

        except Exception as e:
            logger.error("Local embedding generation failed for %s: %s", document_id, e)
            raise

    def _mark_job_failed(self, job: ProcessingJob | None, reason: str) -> None:
        """Mark job as FAILED and commit changes."""
        if job:
            job.status = EJobStatus.FAILED
            job.stage = EPipelineStage.PERSISTENCE
            job.progress = 0
        self.session.commit()
        logger.error("Job finalization failed: %s", reason)

    def _validate_pipeline_outputs(
        self, doc: Document, document_id: uuid.UUID
    ) -> tuple[int, uuid.UUID]:
        """
        Validate all pipeline outputs exist.

        Returns:
            Tuple of (chunk_count, version_id)

        Raises:
            ValueError: If any validation fails
        """
        if not doc.raw_text:
            raise ValueError(f"Document {document_id} has no extracted text")

        if not doc.current_version_id:
            raise ValueError(f"Document {document_id} has no AI analysis version")

        version = self.version_repo.get_by_id(doc.current_version_id)
        if not version or not version.data.get("summary"):
            raise ValueError(f"Document {document_id} version missing summary data")

        chunk_count = self.chunk_repo.count_by_document_id(document_id)
        if chunk_count == 0:
            raise ValueError(f"Document {document_id} has no embeddings")

        return chunk_count, doc.current_version_id

    def validate_and_finalize_job(self, document_id: uuid.UUID) -> str:
        """
        Stage 4: Validate all outputs exist and mark job as COMPLETED.

        This is a synchronization point that ensures both parallel tasks
        (AI Analysis and Embeddings) completed successfully before marking
        the job as complete.

        Validates:
        - Document has extracted text (extraction succeeded)
        - Document has a current version (analysis succeeded)
        - Document has embeddings (embedding generation succeeded)

        Args:
            document_id: UUID of the document to finalize

        Returns:
            str: document_id as string

        Raises:
            ValueError: If any critical validation fails
        """
        doc = self.doc_repo.get_by_id(document_id)
        if not doc:
            raise ValueError(f"Document {document_id} not found")

        job = self.job_repo.get_by_document_id(document_id)

        try:
            chunk_count, version_id = self._validate_pipeline_outputs(doc, document_id)
        except ValueError as e:
            self._mark_job_failed(job, str(e))
            raise

        if job:
            job.stage = EPipelineStage.PERSISTENCE
            job.progress = 95
        self.session.commit()
        publish_progress_update(
            document_id,
            progress=95,
            stage=EPipelineStage.PERSISTENCE,
        )

        # All validations passed - mark as COMPLETED
        if job:
            job.status = EJobStatus.COMPLETED
            job.progress = 100

        self.session.commit()

        # Publish completion update
        publish_progress_update(
            document_id,
            progress=100,
            stage=EPipelineStage.PERSISTENCE,
            status=EJobStatus.COMPLETED,
        )

        logger.info(
            "Pipeline validation and finalization completed for document %s. "
            "Chunks: %d, Version ID: %s",
            document_id,
            chunk_count,
            version_id,
        )

        return str(document_id)
