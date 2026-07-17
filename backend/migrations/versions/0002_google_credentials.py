"""google oauth: nullable password + google_credentials

Revision ID: 0002_google_credentials
Revises: 0001_initial
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_google_credentials"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # SSO users have no local password.
    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.String(length=255),
        nullable=True,
    )

    op.create_table(
        "google_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("google_sub", sa.String(length=255), nullable=False),
        sa.Column("google_email", sa.String(length=320), nullable=False),
        sa.Column("access_token_enc", sa.Text(), nullable=False),
        sa.Column("refresh_token_enc", sa.Text(), nullable=True),
        sa.Column("token_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_google_credentials_user_id"),
        "google_credentials",
        ["user_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_google_credentials_google_sub"),
        "google_credentials",
        ["google_sub"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_google_credentials_google_sub"), table_name="google_credentials")
    op.drop_index(op.f("ix_google_credentials_user_id"), table_name="google_credentials")
    op.drop_table("google_credentials")
    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.String(length=255),
        nullable=False,
    )
