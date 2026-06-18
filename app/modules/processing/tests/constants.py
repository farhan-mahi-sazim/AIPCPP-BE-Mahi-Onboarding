import uuid

# Mock IDs
MOCK_DOCUMENT_ID = uuid.uuid4()
MOCK_JOB_ID = uuid.uuid4()
MOCK_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")

# Test Data
TEST_RAW_TEXT = "This is a test document content. It has multiple sentences. It should be summarized and embedded."
TEST_SUMMARY = "Test summary of the document."
TEST_TAGS = ["test", "document", "mock"]
TEST_CATEGORY = "Test Category"
TEST_EMAIL = "test@example.com"
TEST_FULL_NAME = "Test User"

# Mock S3
MOCK_S3_KEY = f"{MOCK_USER_ID}/{MOCK_DOCUMENT_ID}.pdf"

# Mock LiteLLM Response
MOCK_AI_RESPONSE = {
    "summary": TEST_SUMMARY,
    "tags": TEST_TAGS,
    "category": TEST_CATEGORY,
}

# BAAI/bge-base-en-v1.5 standard dimension
MOCK_EMBEDDING = [0.1] * 768
