# Document Processing & Summary Generation Pipeline

This document details the background processing pipeline responsible for transforming uploaded files into AI-powered insights, including text extraction, summary generation, and vector embeddings.

## Pipeline Architecture

The pipeline uses a **Celery Workflow** (**chain** + **group** + a final validation step), optimizing execution by running independent stages in parallel while only marking the job as completed after all parallel work finishes.

```mermaid
graph TD
    A[File Uploaded] --> B(Stage 1: Text Extraction)
    B --> C{Success?}
    C -- Yes --> D[Parallel Processing]
    D --> E(Stage 2: AI Analysis)
    D --> F(Stage 3: Vector Embeddings)
    C -- No --> G[Retry with Backoff]

    E --> H(Stage 4: Validate & Finalize Job)
    F --> H
    H --> I[Pipeline Complete]

    subgraph "External Dependencies"
        L[MinIO / S3]
        M[Gemini API / LiteLLM]
    end

    B -.-> L
    E -.-> M
    F -.-> M
```

---

## Processing Stages

### 1. Text Extraction (`extract_text_task`)

- **Responsibility**: Retrieves the raw file from S3/MinIO and extracts human-readable text.
- **Supported Formats**:
  - **PDF**: Uses `pypdf`.
  - **Images**: Uses `Tesseract OCR`.
  - **Text**: Direct reading.
  - **DOCX**: Extracts from Office OpenXML (`word/document.xml`).
- **Output**: Updates `Document.raw_text` and advances the `ProcessingJob` stage.

### 2. AI Analysis (`analyze_content_task`)

- **Responsibility**: Orchestrates AI models to generate structured summaries and metadata.
- **Logic**:
  - **Summarization**: Generates a concise summary of the extracted text.
  - **Tagging**: Extracts relevant keywords and topics.
  - **Categorization**: Classifies the document (e.g., Invoice, Report, Letter).
- **Resiliency**:
  - Uses **Exponential Backoff** for rate limits.
  - Implements **Model Fallback**: If Gemini-Pro fails, it retries with secondary providers via LiteLLM.
- **Output**: Creates a new `DocumentVersion` and updates `Document.current_version_id`.

### 3. Vector Embeddings (`generate_embeddings_task`)

- **Responsibility**: Converts the extracted text into high-dimensional vectors for semantic search.
- **Dimensions**: 3072 (optimized for Gemini-2).
- **Output**: Populates the `document_chunks` table with `pgvector` compatible embeddings.

### 4. Validate & Finalize (`validate_and_finalize_job_task`)

- **Responsibility**: Synchronization point that runs after the parallel stage.
- **Validation**:
  - `Document.raw_text` exists (extraction succeeded)
  - `Document.current_version_id` exists and points to a `DocumentVersion` with summary data (analysis succeeded)
  - At least one `DocumentChunk` exists (embeddings succeeded)
- **Output**: Marks `ProcessingJob` as **COMPLETED** only after all validations pass.

---

## Resiliency & Fault Tolerance

| Feature             | Implementation                                                                                                       |
| :------------------ | :------------------------------------------------------------------------------------------------------------------- |
| **Retries**         | 5 retries per task with randomized jitter to prevent "thundering herd" issues.                                       |
| **Backoff**         | Exponential increase in wait time (up to 15 minutes for Analysis).                                                   |
| **Timeouts**        | Strict timeouts (30s for Analysis, 20s for Embeddings) to prevent hanging workers.                                   |
| **Status Tracking** | Job is marked **COMPLETED** by the finalizer once all outputs exist; intermediate stages update `stage` as they run. |

## Error Handling

If the finalizer validation fails:

1.  The `ProcessingJob` is marked as **FAILED**.
2.  The error is logged with context (document ID).

If an upstream Celery task fails repeatedly and never reaches finalization, Celery will stop retrying after max retries; adding explicit job-failure hooks for that case is a follow-up improvement.
