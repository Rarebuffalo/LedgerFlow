from celery import Celery
from app.config import settings

celery_app = Celery(
    "ledgerflow_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.tasks"]
)

# Standard configuration for production scalability
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Make tasks more reliable
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
