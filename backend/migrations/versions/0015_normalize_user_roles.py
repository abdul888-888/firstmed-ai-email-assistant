"""Normalize user_role values to uppercase

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Normalize all user role values to uppercase."""
    # Update any lowercase role values to their uppercase equivalents
    op.execute(sa.text("UPDATE users SET role = UPPER(role) WHERE role != UPPER(role)"))


def downgrade() -> None:
    """Revert user role values to lowercase (not recommended)."""
    op.execute(sa.text("UPDATE users SET role = LOWER(role) WHERE role = UPPER(role)"))
