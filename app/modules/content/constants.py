MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
UPLOAD_ERROR_MESSAGE = "An error occurred during file upload."
DELETE_ERROR_MESSAGE = "An error occurred while deleting the document."
INVALID_FILE_TYPE_MESSAGE = "Unsupported file type: {extension}"
FILE_TOO_LARGE_MESSAGE = "File too large. Maximum size is 50MB."


class StorageError(Exception):
    """Exception raised for storage/S3 operations failures."""

    def __init__(self, message: str, s3_key: str | None = None):
        self.message = message
        self.s3_key = s3_key
        super().__init__(self.message)
