"""Drop google_credentials table (Phase 5 cleanup).

Revision ID: 0014
Revises: 0013
Create Date: 2024-08-02 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Drop google_credentials table after data is safely in connected_accounts."""
    # Safety check: verify connected_accounts has Gmail rows
    connection = op.get_bind()
    result = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM connected_accounts WHERE provider_type = 'gmail'"
        )
    )
    gmail_count = result.scalar() or 0

    result = connection.execute(sa.text("SELECT COUNT(*) FROM google_credentials"))
    old_count = result.scalar() or 0

    if old_count > 0 and gmail_count < old_count:
        raise RuntimeError(
            f"Data loss detected: google_credentials has {old_count} rows but "
            f"connected_accounts has only {gmail_count} Gmail rows. "
            "Migration aborted to protect data integrity."
        )

    # Drop the table
    op.drop_table("google_credentials")


def downgrade() -> None:
    """Recreate google_credentials table and restore data from connected_accounts."""
    op.create_table(
        "google_credentials",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("google_sub", sa.String(255), nullable=False),
        sa.Column("google_email", sa.String(255), nullable=False),
        sa.Column("access_token_enc", sa.LargeBinary(), nullable=False),
        sa.Column("refresh_token_enc", sa.LargeBinary(), nullable=True),
        sa.Column("token_expiry", sa.DateTime(), nullable=True),
        sa.Column("scopes", sa.String(2048), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_google_credentials_user"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    # Restore data from connected_accounts
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            INSERT INTO google_credentials
            (id, created_at, updated_at, user_id, google_sub, google_email,
             access_token_enc, refresh_token_enc, token_expiry, scopes)
            SELECT
                id, created_at, updated_at, user_id, provider_sub, provider_email,
                access_token_enc, refresh_token_enc, token_expiry, ''
            FROM connected_accounts
            WHERE provider_type = 'gmail'
            ON CONFLICT DO NOTHING
            """
        )
    )
