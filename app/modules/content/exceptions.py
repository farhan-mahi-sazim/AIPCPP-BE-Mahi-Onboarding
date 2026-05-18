class StorageError(Exception):
    """Exception raised for storage/S3 operations failures."""

    def __init__(self, message: str, s3_key: str | None = None):
        self.message = message
        self.s3_key = s3_key
        super().__init__(self.message)
