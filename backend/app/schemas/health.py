"""Health / readiness schemas."""

from __future__ import annotations

from pydantic import BaseModel


class HealthStatus(BaseModel):
    status: str
    service: str
    version: str
    environment: str


class ReadinessStatus(BaseModel):
    status: str
    checks: dict[str, str]
