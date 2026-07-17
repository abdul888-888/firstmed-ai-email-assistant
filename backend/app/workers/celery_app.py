"""Celery application.

Background processing (email ingestion, embedding, sync) runs on Celery workers
in later phases. Run a worker with:

    celery -A app.workers.celery_app.celery_app worker --loglevel=info
"""

from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "firstmed",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.example"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)
