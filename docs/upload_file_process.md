# File Upload API: Implementation Walkthrough & Trade-offs

This document provides a deep dive into how the File Upload API is structured in the AI-Powered Content Processing Pipeline.

## 1. API Architecture Breakdown

The upload process follows a strict layered architecture to ensure separation of concerns:

```mermaid
sequenceDiagram
    participant Client
    participant API as FastAPI
    participant Service
    participant S3 as MinIO
    participant Celery
    participant DB as Postgres

    Client->>API: POST /upload
    API->>Service: upload_document()
    Service->>S3: Upload File
    S3-->>Service: OK
    Service->>DB: Save Metadata (flush)
    Service->>DB: Create Job (flush)
    Service->>Celery: Trigger Pipeline
    Celery-->>Service: OK
    Service->>DB: Commit Transaction
    Service-->>API: Response
    API-->>Client: 201 Created

    Note over Service,DB: If pipeline trigger fails: rollback + cleanup S3
```

### Core Components:

- **`app/modules/content/routes.py`**: Handles the HTTP contract. It uses `UploadFile` which streams the file to memory/spool, preventing RAM spikes for large files.
- **`app/modules/content/services.py`**: The "Orchestrator." It doesn't know _how_ S3 works or _how_ the DB saves; it just directs the flow.
- **`app/common/storage.py`**: A thin wrapper around `boto3`. It abstracts away the bucket creation and credential handling.
- **`app/modules/content/tasks.py` (or processing tasks)**: Celery tasks for async pipeline execution.

---

## 2. Implementation Decisions & Trade-offs

### A. The "Sync-in-Async" Challenge

**Decision**: Use `run_in_threadpool` for S3 uploads.

- **Why?**: The official AWS SDK (`boto3`) is synchronous. In a FastAPI `async def` function, a large upload would block the entire server's thread, stopping other users.
- **Trade-off**: Managing thread pools adds a small amount of overhead, but it is the standard "safe" way to use stable libraries like `boto3` in an async environment.

### B. Decoupling Content from Processing

**Decision**: Create a `Document` record AND a `ProcessingJob` record simultaneously.

- **Why?**: This allows the API to return immediately while the actual AI processing happens in the background.
- **Trade-off**: Requires more complex state management (checking job status later), but provides a much better User Experience (UX) as the user doesn't wait for AI to finish.

---

## 3. MinIO vs. Database Storage (Trade-offs)

In this project, we chose **MinIO (S3-compatible Object Storage)** over storing files as `BYTEA` or `BLOB` in Postgres.

| Feature         | MinIO / S3 (Chosen)                                           | Database (BYTEA)                                            |
| :-------------- | :------------------------------------------------------------ | :---------------------------------------------------------- |
| **Performance** | High. Offloads heavy binary data from DB engine.              | Low. Bloat makes DB backups and queries slower.             |
| **Scalability** | Unlimited. Can scale storage independently of the app.        | Limited by the DB's storage and memory limits.              |
| **Cost**        | Cheap. S3-compatible storage is very cost-effective.          | Expensive. High-performance DB storage is pricey.           |
| **Consistency** | **Weak**. If DB fails after upload, a file is orphaned in S3. | **Strong**. File and metadata are saved in one transaction. |
| **Portability** | High. Can switch to AWS, GCS, or R2 easily.                   | Low. Locked into the specific DB engine.                    |

### The "Orphaned File" Problem

One major trade-off of using S3 is that we don't have atomic transactions across S3 and Postgres.

- **The Risk**: If the file uploads to MinIO but the database insert fails (e.g., a connection error), we have a file in MinIO with no database record.
- **Our Strategy**: We perform the upload _before_ the DB insert. This ensures we never have a DB record pointing to a non-existent file. Additionally, we trigger the Celery pipeline _before_ committing the transaction, ensuring that if pipeline enqueue fails, we rollback the entire DB state and clean up the S3 object.

### Transaction Order (Critical)

The order of operations is crucial to prevent inconsistencies:

1. **Upload to S3** (succeeds/fails here)
2. **Create Document & Job records** (flush to DB, not committed)
3. **Trigger Celery pipeline** (enqueue background tasks)
4. **Commit transaction** (only if all above succeed)

If step 3 fails:
- Rollback DB transaction (no orphaned records)
- Delete S3 object (no orphaned files)

This prevents the scenario where DB records exist but no background job is queued.

---

## 3. Delete Flow

The document deletion process follows the reverse order to ensure consistency:

```mermaid
sequenceDiagram
    participant Client
    participant API as FastAPI
    participant Service
    participant S3 as MinIO
    participant DB as Postgres

    Client->>API: DELETE /documents/{id}
    API->>Service: delete_document()
    Service->>S3: Delete File
    S3-->>Service: OK
    Service->>DB: Set current_version_id = NULL
    Service->>DB: Delete DocumentVersion (summary)
    Service->>DB: Commit Transaction
    Service-->>API: Response
    API-->>Client: 204 No Content
```

**Critical Order**: S3 deletion happens FIRST. If S3 delete fails, we raise an error and do NOT commit the DB changes. This prevents the case where DB records are deleted but S3 objects remain (orphaned files).

If S3 delete succeeds, we proceed to:
1. Clear the document's `current_version_id`
2. Delete the associated `DocumentVersion` (summary data)
3. Commit the transaction

---

## 4. Why Postgres 17 + pgvector?

Even though the file lives in MinIO, we need Postgres for:

1. **Metadata**: Tracking filename, owner, and status.
2. **Semantic Search**: Once the file is processed, we extract text and store **Vector Embeddings** in Postgres using `pgvector`. This allows the "AI" to search through your documents by "meaning" rather than just keywords.
