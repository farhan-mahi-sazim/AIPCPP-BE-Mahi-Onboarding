# Progress Tracking Flow Diagram

## Complete Flow: Upload to Completion

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           CLIENT (Browser)                              │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 1. User selects file and clicks Upload                         │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
                    POST /api/v1/content/upload
                          (with file data)
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                        BACKEND (FastAPI)                                │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 2. upload_document() in content/services.py                     │   │
│  │    • Validate file size/type                                    │   │
│  │    • Create progress callback for S3 upload                     │   │
│  │    • Upload file to S3 (0-50% progress)                        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                    ↓                                     │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 3. Create DB Records                                            │   │
│  │    • Document record with file metadata                         │   │
│  │    • ProcessingJob record (status=PROCESSING, progress=0)      │   │
│  │    • Commit to database                                         │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                    ↓                                     │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 4. Trigger Celery Pipeline                                      │   │
│  │    sse_manager.publish(doc_id, 0%, "processing_started")       │   │
│  │    celery.chain([extract, group(analyze, embed), finalize])    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                    ↓                                     │
│                    Return response to client:                            │
│                  {                                                       │
│                    "document": {...},                                    │
│                    "job": {                                              │
│                      "id": "...",                                        │
│                      "status": "processing",  ← Changed from PENDING    │
│                      "progress": 0,                                      │
│                    }                                                     │
│                  }                                                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                        CLIENT (Browser)                                 │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 5. Client receives document_id from response                    │   │
│  │    • Opens EventSource connection to SSE endpoint               │   │
│  │    GET /api/v1/content/jobs/{doc_id}/progress/stream           │   │
│  │                                                                  │   │
│  │    Progress Bar: ▓▓▓░░░░░░░ 0%                                │   │
│  │    Status: "Processing..."                                      │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                      CELERY WORKER (async task)                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 6. extract_text_task(document_id)                               │   │
│  │    • Download file from S3                                      │   │
│  │    • Extract text using OCR/PDF parser                          │   │
│  │    • Save raw_text to Document                                  │   │
│  │    • Update job: progress=20, stage=EXTRACTION                  │   │
│  │    • publish_progress_update(doc_id, 20, EXTRACTION)            │   │
│  │                                                                  │   │
│  │    → Updates database                                           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                        CLIENT (Browser)                                 │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 7. SSE Stream receives data                                      │   │
│  │    {                                                             │   │
│  │      "type": "progress",                                         │   │
│  │      "document_id": "...",                                       │   │
│  │      "progress": 20,                                             │   │
│  │      "stage": "EXTRACTION"                                       │   │
│  │    }                                                             │   │
│  │                                                                  │   │
│  │    Progress Bar: ▓▓▓▓▓▓▓░░░░░░ 20%                            │   │
│  │    Status: "Extracting text..."                                 │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                      CELERY WORKER (parallel)                           │
│  ┌──────────────────────────────┬──────────────────────────────────┐   │
│  │ 8a. analyze_content_task()  │ 8b. generate_embeddings_task()  │   │
│  │                              │                                  │   │
│  │ • Run LLM analysis           │ • Split text into chunks        │   │
│  │ • Extract summary/tags       │ • Generate embeddings           │   │
│  │ • Create AI version          │ • Store in DocumentChunk        │   │
│  │ • Update progress=50         │ • Update progress=75            │   │
│  │ • publish_progress(50)       │ • publish_progress(75)          │   │
│  │                              │                                  │   │
│  │ (Runs in parallel!)          │ (Runs in parallel!)             │   │
│  └──────────────────────────────┴──────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                        CLIENT (Browser)                                 │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 9. Receives multiple updates                                     │   │
│  │                                                                  │   │
│  │    Progress Bar: ▓▓▓▓▓▓▓▓▓▓░░░░ 50%                          │   │
│  │    Status: "Analyzing content..."                               │   │
│  │                                                                  │   │
│  │         ↓ (moments later)                                       │   │
│  │                                                                  │   │
│  │    Progress Bar: ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░ 75%                        │   │
│  │    Status: "Generating embeddings..."                           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                      CELERY WORKER (sync point)                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 10. validate_and_finalize_job_task(document_id)                 │   │
│  │     • Wait for both parallel tasks to complete                  │   │
│  │     • Validate raw_text exists                                  │   │
│  │     • Validate AI version exists                                │   │
│  │     • Validate embeddings exist                                 │   │
│  │     • Update job: status=COMPLETED, progress=100                │   │
│  │     • publish_progress_update(doc_id, 100, COMPLETED)           │   │
│  │                                                                  │   │
│  │     → Updates database                                          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                        CLIENT (Browser)                                 │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 11. Receives completion event                                    │   │
│  │     {                                                            │   │
│  │       "type": "progress",                                        │   │
│  │       "progress": 100,                                           │   │
│  │       "stage": "PERSISTENCE"                                     │   │
│  │     }                                                            │   │
│  │                                                                  │   │
│  │     Progress Bar: ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ 100%  [COMPLETE]           │   │
│  │     Status: "Complete!"                                          │   │
│  │                                                                  │   │
│  │     • Close SSE connection                                       │   │
│  │     • Show success message                                       │   │
│  │     • Redirect to document view                                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

## Error/Retry Flow

```
If Celery task fails:

┌──────────────────────┐
│ Celery task fails    │
└──────────────────────┘
         ↓
┌──────────────────────────────────────────────┐
│ Error callback triggered:                    │
│ _mark_job_failed_on_failure()               │
│                                              │
│ If retries exhausted:                        │
│ • Update job: status=FAILED, progress=0     │
│ • Update job: stage=PERSISTENCE             │
│ • Commit to database                         │
└──────────────────────────────────────────────┘
         ↓
┌──────────────────────────────────────────────┐
│ Frontend polling/SSE still receives updates  │
│ • Shows progress=0, status=FAILED            │
│ • Shows error message to user                │
│ • Allows user to retry upload                │
└──────────────────────────────────────────────┘
```

## SSE Fallback Flow

```
If EventSource connection fails:

┌──────────────────────────────┐
│ SSE connection error         │
└──────────────────────────────┘
         ↓
┌──────────────────────────────────────────────────────────┐
│ Frontend implements retry logic:                          │
│ • Retry 1: Wait 2s (exponential backoff)                 │
│ • Retry 2: Wait 4s                                       │
│ • Retry 3: Wait 8s                                       │
│ • Max retries exceeded → Fall back to polling             │
└──────────────────────────────────────────────────────────┘
         ↓
┌──────────────────────────────────────────────────────────┐
│ Polling mechanism (every 2-5 seconds):                   │
│ GET /api/v1/content/jobs/{doc_id}/progress              │
│                                                           │
│ Response:                                                │
│ {                                                        │
│   "job_id": "...",                                       │
│   "status": "processing",                                │
│   "progress": 50,                                        │
│   "stage": "AI_TASK"                                     │
│ }                                                        │
│                                                           │
│ • Frontend updates UI with latest state                  │
│ • Continues polling until progress=100                   │
└──────────────────────────────────────────────────────────┘
```

## Database State Transitions

```
Initial State (After Upload):
┌─────────────────────────────────┐
│ ProcessingJob                   │
│ ├─ id: "..."                    │
│ ├─ document_id: "..."           │
│ ├─ status: PROCESSING           │ ← Changed from PENDING
│ ├─ progress: 0                  │
│ ├─ stage: null                  │
│ └─ created_at: now              │
└─────────────────────────────────┘

After Extraction Task:
┌─────────────────────────────────┐
│ ProcessingJob                   │
│ ├─ status: PROCESSING           │
│ ├─ progress: 20                 │
│ ├─ stage: EXTRACTION            │ ← Updated
│ └─ updated_at: now              │
└─────────────────────────────────┘

After AI Analysis Task:
┌─────────────────────────────────┐
│ ProcessingJob                   │
│ ├─ status: PROCESSING           │
│ ├─ progress: 50                 │
│ ├─ stage: AI_TASK               │ ← Updated
│ └─ updated_at: now              │
└─────────────────────────────────┘

After Embeddings Task:
┌─────────────────────────────────┐
│ ProcessingJob                   │
│ ├─ status: PROCESSING           │
│ ├─ progress: 75                 │
│ ├─ stage: EMBEDDING             │ ← Updated
│ └─ updated_at: now              │
└─────────────────────────────────┘

After Finalization:
┌─────────────────────────────────┐
│ ProcessingJob                   │
│ ├─ status: COMPLETED            │ ← Changed
│ ├─ progress: 100                │ ← Changed
│ ├─ stage: PERSISTENCE           │ ← Changed
│ └─ updated_at: now              │
└─────────────────────────────────┘
```

## Files Involved

```
Upload Request Flow:
  Browser
    ↓
  routes.py:137 (upload_document)
    ↓
  services.py:134 (ContentService.upload_document)
    ├─ Storage to S3
    ├─ Create Document record
    ├─ Create ProcessingJob record (status=PROCESSING)
    └─ Trigger Celery pipeline

Pipeline Execution:
  tasks.py:67 (extract_text_task)
    ↓
  services.py:45 (ProcessingService.process_extraction)
    ├─ Update DB: progress=20
    └─ publish_progress_update()
        ↓
    celery_sse_bridge.py (publish_progress_to_db)
        ↓
    Database updated

SSE Subscription:
  Browser → EventSource
    ↓
  routes.py:111 (stream_job_progress)
    ↓
  sse_manager.py:subscribe()
    ↓
  Wait for events in queue
    ↓
  Yield to client via SSE
```

## Timeline Example

```
T=0s   : User clicks "Upload"
T=2s   : File uploaded, upload() returns with status=PROCESSING, progress=0
T=2.5s : Browser connects to SSE, receives cached "processing_started" event
T=3s   : Celery extract_text_task starts
T=5s   : Extraction complete, progress=20 published to SSE
T=5.1s : Browser receives SSE update, progress bar shows 20%
T=5.2s : Parallel tasks (analyze + embed) start
T=8s   : AI analysis complete, progress=50 published
T=8.1s : Browser receives update, progress bar shows 50%
T=12s  : Embedding complete, progress=75 published
T=12.1s: Browser receives update, progress bar shows 75%
T=13s  : Finalization complete, progress=100 published
T=13.1s: Browser receives update, progress bar shows 100% [COMPLETE]
T=13.2s: SSE connection closes, page redirects to document view
```

## Key Improvements vs Before

| Aspect | Before | After |
|--------|--------|-------|
| **Initial Status** | PENDING (stuck) | PROCESSING (immediate) |
| **Progress Updates** | None after upload | 0→20→50→75→100% |
| **Celery Integration** | No SSE publishing | All tasks publish progress |
| **Error Handling** | No fallback | SSE→Polling fallback |
| **Multiple Clients** | Each waits for next event | All get cached last event |
| **Reliability** | Stuck UI | Resilient with retry logic |

