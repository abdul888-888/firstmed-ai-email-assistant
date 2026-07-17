"""Example Celery task — proves the worker wiring end-to-end."""

from __future__ import annotations

from app.workers.celery_app import celery_app


@celery_app.task(name="example.ping")
def ping() -> str:
    """Return 'pong'. Useful as a worker health check."""
    return "pong"
