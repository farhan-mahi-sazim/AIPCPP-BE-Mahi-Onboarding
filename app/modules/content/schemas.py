from pydantic import BaseModel


class TContentCreate(BaseModel):
    raw_text: str
    source_type: str = "text"


class TContentRead(BaseModel):
    id: int
    raw_text: str
    summary: str | None = None
    source_type: str
