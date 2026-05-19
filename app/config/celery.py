import sys

from celery import Celery

from app.config.settings import settings

celery_app = Celery(
    "aipcpp_tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.modules.processing.tasks"],
)

# Optional configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max per task
    worker_pool="threads" if sys.platform == "darwin" else "prefork",
)

if __name__ == "__main__":
    celery_app.start()
