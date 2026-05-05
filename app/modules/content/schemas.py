from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional, List
from app.common.enums.file_type import EFileType
from app.common.enums.job_status import EJobStatus


class TDocumentBase(BaseModel):
    filename: str
    file_type: EFileType


class TDocumentRead(TDocumentBase):
    id: UUID
    owner_id: UUID
    s3_key: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TJobRead(BaseModel):
    id: UUID
    status: EJobStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TUploadResponse(BaseModel):
    document: TDocumentRead
    job: TJobRead
    message: str = "Upload successful. Processing started."
