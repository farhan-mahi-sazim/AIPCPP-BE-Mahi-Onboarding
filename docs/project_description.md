# Project: AI-Powered Content Processing Pipeline

## 1. Overview
A system designed for users to upload raw content (text, PDFs, images) for automated extraction, summarization, and categorization using AI. The system processes data asynchronously and includes a robust human-in-the-loop versioning system.

---

## 2. Core Features & Functional Requirements

### A. Upload & Ingestion API
- **Supported Formats:** Text, PDF, Image.
- **Storage:** Raw files are stored using S3-compatible solutions (e.g., MinIO, LocalStack).

### B. Background Processing (Worker System)
- **Engine:** Celery (Python) or RQ.
- **Pipeline Stages:**
    1. **Extraction:** Convert PDF/Image to raw text.
    2. **Normalization:** Clean and normalize extracted text.
    3. **AI Task Execution:** Process text through LLMs.
    4. **Persistence:** Store final results in the database.

### C. AI Layer
- **Model Support:** OpenAI or local models (e.g., Llama, Mistral).
- **Tasks:**
    - Generate concise summaries.
    - Extract keywords and metadata.
    - Classify content into topics/categories.
- **Advanced Features:** Semantic search via chunking and embeddings.

### D. Search Layer
- **Basic:** Full-text search within the database.
- **Advanced:** Vector search using FAISS or pgvector for semantic retrieval.

### E. Status Tracking & UI
- **Tracking:** Monitor processing status, errors, and results via API/UI.
- **Interface:** Minimal frontend or CLI for uploading files and viewing processed outputs.

---

## 3. Human Override & Version History System (Critical)

### A. Editable Outputs
Users have the authority to modify AI-generated summaries, tags, and categories. The system must clearly distinguish between:
- **AI-generated versions**
- **User-edited versions**

### B. Versioning Logic
Every modification creates a new entry in the history.
- **Attributes per Version:** `version_id`, `content`, `source` (AI/USER), `timestamp`, `user_id`.

### C. Timeline View
A chronological history log showing:
- "AI generated initial summary"
- "User edited summary"
- Change details (what, when, and who).

---

## 4. Technical Constraints & Considerations
- **Prompt Design:** Strategies to handle token limits and ensure structured output.
- **Performance:** Trade-offs between cost and processing speed.
- **Asynchronicity:** Entire pipeline must be non-blocking.
