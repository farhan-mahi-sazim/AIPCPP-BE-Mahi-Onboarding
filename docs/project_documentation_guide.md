# AI-Powered Content Processing Pipeline (AIPCPP)
## Detailed System Documentation & Architecture Guide

Welcome to the comprehensive architecture and documentation guide for the **AI-Powered Content Processing Pipeline (AIPCPP)**. This system is engineered to ingest raw, multi-format content (PDFs, Images, DOCX, Text), parse the data asynchronously, generate AI summaries and topic classifications, compute high-dimensional vector embeddings, and enable instant semantic search alongside a human-in-the-loop editing timeline.

---

## 1. System Overview

AIPCPP is built using a modern, scalable, and asynchronous Python stack. The core objectives of the system are:
1. **Multi-Format Ingestion**: Ingest and store files (up to 50MB) like text, PDFs, and images (OCR required) securely using S3-compatible storage.
2. **Asynchronous Analysis**: Decouple file uploads from computation by executing text extraction, LLM analysis, and embedding generation in background workers.
3. **Semantic Querying**: Enable intelligent, conceptually driven search across document chunks using vector databases instead of simple keyword matching.
4. **Human-in-the-Loop Override**: Keep a persistent audit trail of edits made to AI-generated details, allowing users to override, update, and rollback summaries or categorization tags.

```
┌──────────────┐     File Ingestion      ┌─────────────────┐     Vector Store
│ Next.js Client│ ─────────────────────> │ FastAPI Backend │ ──────────────────> PostgreSQL
└──────────────┘                         └─────────────────┘                    (pgvector)
       ▲                                          │ Trigger
       │ SSE Real-time Updates                    │ Background Job
       │                                          ▼
┌──────────────────┐                     ┌─────────────────┐                    ┌──────────────┐
│  SSE Connection  │                     │ Celery Workers  │ ─────────────────> │ LiteLLM API  │
└──────────────────┘                     └─────────────────┘      AI Insights   └──────────────┘
```

---

## 2. Technical Stack & Core Abstractions

* **Core Framework**: **FastAPI** (Python 3.12) utilizing asynchronous handlers.
* **Database & ORM**: **PostgreSQL 17** + **pgvector** for vector search, mapped via **SQLModel** (which unifies SQLAlchemy and Pydantic).
* **Asynchronous Task Queue**: **Celery** with **Redis** as a broker for distributed background workers.
* **AI Integration**: **LiteLLM** (supporting a fallback chain between Google Gemini and OpenAI).
* **Text & OCR Engines**: **PyPDF** (PDF extraction) and **Tesseract OCR** (Image parsing).
* **Caching & Performance**: **Redis** caching utilizing custom decorators for caching search and version timeline operations.
* **Storage Layer**: S3-compatible object storage (e.g., **MinIO** or **LocalStack**) to isolate and manage raw uploaded files.

---

## 3. Database Schema & Data Models

The system architecture utilizes 5 primary database tables to map relationships. Below is the entity-relationship layout:

```mermaid
erDiagram
    users ||--o{ documents : owns
    users ||--o{ document_versions : edits
    documents ||--o{ document_versions : tracks_history
    documents ||--o{ document_chunks : segments
    documents ||--o{ processing_jobs : logs_pipeline

    users {
        uuid id PK
        string email
        string hashed_password
    }

    documents {
        uuid id PK
        uuid owner_id FK
        string filename
        string s3_key
        string file_hash
        string file_type
        string raw_text
        uuid current_version_id FK
        datetime created_at
        datetime updated_at
    }

    document_versions {
        uuid id PK
        uuid document_id FK
        int version_number
        json data "summary, tags, category"
        string source "AI or HUMAN"
        uuid parent_version_id FK
        uuid created_by FK
        datetime created_at
    }

    document_chunks {
        uuid id PK
        uuid document_id FK
        int chunk_index
        string content
        vector embedding "768 dims"
        json chunk_metadata
        datetime created_at
    }

    processing_jobs {
        uuid id PK
        uuid document_id FK
        string status "PENDING, PROCESSING, COMPLETED, FAILED"
        int progress "0-100"
        string stage "EXTRACTION, AI_TASK, EMBEDDING, PERSISTENCE"
        int retry_count
        string celery_task_id
        json error_log
        json job_metadata
        datetime created_at
        datetime updated_at
    }
```

---

## 4. Architectural Layer Pattern

Each capability resides under `app/modules/<domain>/` and follows a strict **Layered Module Pattern** to isolate HTTP boundaries, business logic, data persistence, and models:

1. **Routes Layer (`routes.py`)**: HTTP handlers validating schemas and invoking scoped services. HTTP logic remains strictly in this layer.
2. **Service Layer (`services.py`)**: Core business orchestrator. Scoped services take an active `AsyncSession` to construct repositories. Coordinate operations across repositories.
3. **Repository Layer (`repositories.py`)**: Clean data access abstraction. Focuses entirely on SQL queries and basic persistent operations, using `flush()` for inline actions and leaving transaction commits to the service layer.
4. **Schemas Layer (`schemas.py`)**: Contains plain Pydantic models for request payloads and response shapes, strictly using the `T` prefix (e.g., `TVersionRead`).

---

## 5. Module Breakdown & Processes

### A. The `content` Module
Manages file ingestion, storage interactions, status polling, and pagination.
* **Core Endpoints**:
  * `POST /api/v1/content/upload`: Parses raw files, verifies format constraints, saves the binary data to S3, instantiates a `ProcessingJob`, and triggers the async pipeline.
  * `GET /api/v1/content/summaries`: A fully paginated list handler supporting searching, sorting, and multi-file filtering.
  * `GET /api/v1/content/jobs/{document_id}/progress/stream`: A **Server-Sent Events (SSE)** connection allowing real-time pipeline status updates on the frontend.
* **Text Extraction Engine**:
  * Decodes text formats dynamically.
  * Parses DOCX files from the raw OpenXML schema (`word/document.xml`).
  * Employs PyPDF to scan page elements and Tesseract OCR to perform image text recognition.

---

### B. The `processing` Module
Operates in Celery background workers. It leverages asynchronous stages to process raw document materials without blockages.
* **Celery Workflow Design**:
  * Runs a pipeline sequence configured as a **Celery Chain** containing a **Group** for parallelization:
    `Chain( Extraction ──> Group(AI Analysis, Embedding Generation) ──> Finalize & Validate )`
* **Fallback AI Chains**:
  * Uses **LiteLLM** to invoke `gemini/gemini-2.0-flash`.
  * If a rate limit or service interruption strikes, it intercepts the error and cascades to alternate models (`gemini/gemini-pro-latest` or OpenAI endpoints) to guarantee system resilience.

```mermaid
sequenceDiagram
    participant Celery
    participant Extractor as Text Extraction
    participant Analyzer as AI Analyst
    participant Embedder as Embedding Engine
    participant Finalizer as Validator

    Celery->>Extractor: extract_text_task
    Note over Extractor: PyPDF, OCR, or DOCX Parse
    Extractor-->>Celery: raw_text persisted

    rect rgb(230, 240, 255)
        Note over Celery: Parallel Group Execution
        Celery->>Analyzer: analyze_content_task
        Celery->>Embedder: generate_embeddings_task
        Note over Analyzer: LiteLLM Fallback Chain
        Note over Embedder: Local Embeddings (BAAI/bge-base-en-v1.5, 768 dims)
        Analyzer-->>Celery: DocumentVersion Created
        Embedder-->>Celery: DocumentChunks Saved
    end

    Celery->>Finalizer: validate_and_finalize_job_task
    Note over Finalizer: Assert text + version + chunks exist
    Finalizer-->>Celery: Mark job COMPLETED
```

---

### C. The `search` Module
Orchestrates intelligent semantic retrieval using pgvector.
* **Similarity Search Logic**:
  * Receives a search prompt, generates its corresponding 768-dimensional vector embedding using the local embedding model (`BAAI/bge-base-en-v1.5`), and performs a cosine-distance search.
  * Cosine similarity is computed directly in SQL using the operator `<=>` (cosine distance) and mapped as `1 - distance`.
  * Allows pagination, strict document owner validation, and joins the related `document_versions` table to yield summaries inline.
* **Performance Enhancements**:
  * The search service is cached utilizing a customized Redis decorator (`@cached`) invalidating search queries automatically as document modifications occur.

---

### D. The `versions` Module
Enables a robust human-in-the-loop review architecture. When the AI finishes processing a document, a base version (`version_number = 1`, `source = AI`) is logged.
* **Human Overrides**:
  * When a user modifies summary notes, categories, or keywords via `POST /api/v1/versions/{document_id}/override`, a new version entry is committed (`version_number = 2`, `source = HUMAN`), pointing back to its parent version.
  * The parent pointer enables full timeline navigation.
* **Deletion & Rollbacks**:
  * Deleting a version updates the parent pointer and rolls back `Document.current_version_id` to the preceding version, ensuring chronological continuity without breaking document status.
* **Caching Decorators**:
  * Accelerates retrieving histories using `@cached` and clears old items via `@cache_invalidate` upon creating, editing, or deleting entries.

---

## 6. Detailed Process Flows

### Flow 1: Document Upload & Real-time Progress Tracking
The client requests an ingestion process. To give users a fluid interface, AIPCPP leverages a dual-process connection combining upload APIs and Server-Sent Events:

```mermaid
sequenceDiagram
    autonumber
    participant Client UI
    participant API as FastAPI Router
    participant Store as Object Storage (MinIO)
    participant DB as PostgreSQL
    participant Celery as Celery Tasks Broker

    Client UI->>API: POST /upload (File payload)
    API->>Store: Put raw binary (S3 Key)
    API->>DB: Create Document (raw_text = Null)
    API->>DB: Instantiate ProcessingJob (PENDING)
    API->>Celery: Trigger Asynchronous Pipeline
    API-->>Client UI: Returns Document UUID
    
    Note over Client UI, API: SSE Stream Connection Established
    Client UI->>API: GET /jobs/{id}/progress/stream
    
    loop Every status transition in worker
        Celery->>DB: Update progress (e.g., Extraction: 20%)
        DB-->>API: Read current progress
        API-->>Client UI: Send progress event payload (SSE)
    end
```

---

### Flow 2: Human Override Versioning Lifecycle
This flowchart details how the system keeps a linear versioning history of content analysis, preserving the original AI extraction while allowing user modifications:

```mermaid
flowchart TD
    A["Celery AI Pipeline Completes"] --> B["Create Version 1: source=AI"]
    B --> C["Set Document.current_version_id = Version 1"]
    
    C --> D{User makes an edit?}
    D -- Yes --> E["POST /versions/{id}/override"]
    E --> F["Generate Version 2: source=HUMAN"]
    F --> G["Set parent_version_id = Version 1"]
    G --> H["Set Document.current_version_id = Version 2"]
    
    H --> I{User deletes Version 2?}
    I -- Yes --> J["Identify parent version: Version 1"]
    J --> K["Set Document.current_version_id = Version 1"]
    K --> L["Delete Version 2 record"]
    I -- No --> M["Document maintains Version 2 active"]
```

---

## 7. Resiliency & Performance Measures

AIPCPP is built to survive large loads and external system faults:

| Scenario / Threat | Countermeasure | Implementation details |
|---|---|---|
| **Large Ingestions (PDFs/Images)** | Asynchronous Offloading | Workers execute slow operations (OCR, PDF reading, Vector embeddings) in Celery background threads. |
| **Model Invocations Hanging** | Enforced Deadlines | AI tasks are constrained by strict timeouts (30s for Analysis). |
| **Model Rate Limits / Outages** | Fallback Cascades | LiteLLM cycles through fallback options (Gemini 2.0 -> Gemini Pro -> alternate providers) dynamically. |
| **Network & Connection Blips** | Jittered Backoffs | Celery tasks execute up to 5 retries with exponential backoffs and randomized jitter intervals. |
| **Hot Path Search Queries** | Redis Caching Decorators | Scoped caches for search keys and timelines; instant programmatic invalidate prefixes upon edits. |
| **Large DB Join Overhead** | pgvector Cosine Operators | Computes similarity values natively inside PostgreSQL index space before returning results. |
