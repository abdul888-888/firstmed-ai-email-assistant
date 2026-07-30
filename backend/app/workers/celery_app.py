"""Celery application.

Background processing (Gmail pull/triage/draft pipeline) runs on Celery workers
so it never blocks the FastAPI request/response cycle or an HTTP timeout, and
can be retried on transient Gmail/AI failures. Run a worker with:

    celery -A app.workers.celery_app.celery_app worker --loglevel=info

Run the periodic auto-pull scheduler (separate process) with:

    celery -A app.workers.celery_app.celery_app beat --loglevel=info
"""

from __future__ import annotations

import asyncio

from celery import Celery
from celery.signals import worker_process_init

from app.core.config import settings

celery_app = Celery(
    "firstmed",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.example", "app.tasks.workflow_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    beat_schedule={
        "gmail-auto-pull": {
            "task": "workflow.pull_all_connected",
            "schedule": settings.gmail_auto_pull_interval_seconds,
        },
    },
)


@worker_process_init.connect
def _reset_async_db_engine(**_kwargs: object) -> None:
    """Dispose the app's async SQLAlchemy engine in each forked worker process.

    Celery's default (prefork) pool forks worker processes from the parent
    after this module — and therefore ``app.core.database``'s module-level
    async engine — has already been imported. An asyncpg connection pool
    is not fork-safe: a child process must not reuse connections/event-loop
    state that existed in the parent before the fork. Disposing here forces
    each worker process to lazily open its own fresh connections on first use.
    """
    from app.core.database import engine

    asyncio.run(engine.dispose())
