import enum

class EFileType(str, enum.Enum):
    PDF = "pdf"
    IMAGE = "image"
    TEXT = "text"
