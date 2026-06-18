import uuid

from sqlalchemy.orm import Session

from app.models.job import ProcessingJob
from app.modules.content.repositories import ProcessingJobRepositorySync


class JobProgressServiceSync:
    """Sync service for updating job progress (used by Celery workers).

    Follows the convention that cross-module access goes through services,
    not repositories.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.job_repo = ProcessingJobRepositorySync(session)

    def get_job_by_document_id(self, document_id: uuid.UUID) -> ProcessingJob | None:
        return self.job_repo.get_by_document_id(document_id)
