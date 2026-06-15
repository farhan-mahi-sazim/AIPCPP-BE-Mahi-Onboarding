from app.common.enums.file_type import EFileType

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
UPLOAD_ERROR_MESSAGE = "An error occurred during file upload."
DELETE_ERROR_MESSAGE = "An error occurred while deleting the document."
INVALID_FILE_TYPE_MESSAGE = "Unsupported file type: {extension}"
FILE_TOO_LARGE_MESSAGE = "File too large. Maximum size is 50MB."
INVALID_FILE_CONTENT_MESSAGE = "File content does not match expected type: {file_type}"

MAGIC_BYTE_READ_SIZE = 64

# Magic byte signatures for file type validation
# Each entry is a tuple of (offset, expected_bytes)
FILE_MAGIC_SIGNATURES: dict[EFileType, list[tuple[int, bytes]]] = {
    EFileType.PDF: [(0, b"%PDF")],
    EFileType.IMAGE: [
        (0, b"\x89PNG\r\n\x1a\n"),  # PNG
        (0, b"\xff\xd8\xff"),  # JPEG/JPG
        (0, b"GIF87a"),  # GIF
        (0, b"GIF89a"),  # GIF
        (0, b"BM"),  # BMP
        (8, b"WEBP"),  # WEBP (RIFF + 4B size + WEBP)
        (0, b"II\x2a\x00"),  # TIFF LE
        (0, b"MM\x00\x2a"),  # TIFF BE
    ],
    EFileType.DOCX: [(0, b"PK\x03\x04")],
    EFileType.DOC: [(0, b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")],
    EFileType.TEXT: [],  # No reliable magic bytes for plain text
}
