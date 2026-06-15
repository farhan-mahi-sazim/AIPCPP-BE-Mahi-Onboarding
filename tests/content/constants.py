from uuid import UUID

DUMMY_USER_ID = UUID("00000000-0000-0000-0000-000000000000")
TEST_EMAIL = "test@example.com"
TEST_FULL_NAME = "Test User"

PDF_FILENAME = "test.pdf"
PDF_CONTENT = b"%PDF-1.4\n%fake pdf content"
EXE_FILENAME = "test.exe"
EXE_CONTENT = b"fake exe content"
TXT_FILENAME = "test.txt"
TXT_CONTENT = b"fake text content"

SUCCESS_STATUS = "processing"
UNSUPPORTED_TYPE_ERROR = "Unsupported file type"
SUMMARY_NOT_FOUND_ERROR = "Summary not found"
DOCUMENT_NOT_FOUND_ERROR = "Document not found"
FAILED_DELETE_ERROR = "Failed to delete document"
