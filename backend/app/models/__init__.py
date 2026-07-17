"""SQLAlchemy models.

Import models here so that ``Base.metadata`` is fully populated (used by Alembic
autogenerate and by the test suite's ``create_all``).
"""

from app.models.base import Base, TimestampMixin
from app.models.document import Document, DocumentSource
from app.models.draft_review import DraftReview
from app.models.google_credential import GoogleCredential
from app.models.user import User, UserRole

__all__ = [
    "Base",
    "TimestampMixin",
    "User",
    "UserRole",
    "GoogleCredential",
    "Document",
    "DocumentSource",
    "DraftReview",
]
