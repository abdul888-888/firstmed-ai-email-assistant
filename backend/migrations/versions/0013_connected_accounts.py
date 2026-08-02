"""Multi-provider email: connected_accounts table + draft_reviews column renames

Introduces the ``connected_accounts`` table that supersedes
``google_credentials`` as the canonical credential store for all email
providers (Gmail, Outlook, IMAP/SMTP).  Existing Gmail credentials are
data-migrated into the new table so no token data is lost.

Also renames the three Gmail-specific columns on ``draft_reviews`` to
provider-agnostic names (``gmail_*`` → ``provider_*``), preserving all
existing row data and recreating the unique constraint under its new name.

Migration is **additive + rename only** — ``google_credentials`` is NOT
dropped here (deferred to migration 0014 after production stabilisation).

Revision ID: 0013_connected_accounts
Revises: 0012_gmail_history_id
Create Date: 2026-08-02

Upgrade steps
-------------
1. CREATE TABLE connected_accounts (all columns + constraints)
2. INSERT INTO connected_accounts SELECT … FROM google_credentials
   (ON CONFLICT DO NOTHING for idempotency on re-runs)
3. RENAME draft_reviews.gmail_message_id → provider_message_id
4. RENAME draft_reviews.gmail_thread_id  → provider_thread_id
5. RENAME draft_reviews.gmail_draft_id   → provider_draft_id
6. DROP CONSTRAINT uq_draft_reviews_user_gmail_message
7. ADD CONSTRAINT uq_draft_reviews_user_provider_message

Downgrade steps (exact reverse)
--------------------------------
1. DROP CONSTRAINT uq_draft_reviews_user_provider_message
2. ADD CONSTRAINT uq_draft_reviews_user_gmail_message
3. RENAME provider_draft_id   → gmail_draft_id
4. RENAME provider_thread_id  → gmail_thread_id
5. RENAME provider_message_id → gmail_message_id
6. DROP TABLE connected_accounts
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# ---------------------------------------------------------------------------
# Revision identifiers — used by Alembic's revision chain.
# ---------------------------------------------------------------------------
revision: str = "0013_connected_accounts"
down_revision: str | None = "0012_gmail_history_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_sqlite() -> bool:
    """Return True when running against a SQLite database.

    SQLite does not support ``ON CONFLICT DO NOTHING`` in INSERT … SELECT, and
    also does not support ``ALTER TABLE … RENAME COLUMN`` in older versions
    (added in 3.25.0 / 2018).  The aiosqlite driver used in tests is recent
    enough to support RENAME COLUMN, but we still need a dialect branch for the
    INSERT idempotency guard.
    """
    bind = op.get_bind()
    return bind.dialect.name == "sqlite"


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    # ── Step 1: CREATE TABLE connected_accounts ──────────────────────────
    op.create_table(
        "connected_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        # Plain VARCHAR — no SQLAlchemy Enum so adding a 4th provider never
        # requires an ALTER TYPE statement.
        sa.Column("provider_type", sa.String(length=20), nullable=False),
        sa.Column("provider_email", sa.String(length=320), nullable=False),
        sa.Column("provider_sub", sa.String(length=255), nullable=True),
        # OAuth tokens (Gmail, Outlook) — Fernet ciphertext.
        # NULL for IMAP/SMTP accounts.
        sa.Column("access_token_enc", sa.Text(), nullable=True),
        sa.Column("refresh_token_enc", sa.Text(), nullable=True),
        sa.Column("token_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", sa.Text(), nullable=False, server_default=""),
        # Provider-specific incremental-sync cursor (nullable until first pull).
        sa.Column("history_id", sa.String(length=64), nullable=True),
        # IMAP/SMTP fields — NULL for OAuth providers.
        sa.Column("imap_host", sa.String(length=255), nullable=True),
        sa.Column("imap_port", sa.Integer(), nullable=True),
        sa.Column("smtp_host", sa.String(length=255), nullable=True),
        sa.Column("smtp_port", sa.Integer(), nullable=True),
        sa.Column("imap_username", sa.String(length=320), nullable=True),
        sa.Column("imap_password_enc", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_connected_accounts_user_id"),
    )
    op.create_index(
        "ix_connected_accounts_user_id",
        "connected_accounts",
        ["user_id"],
    )

    # ── Step 2: Data-migrate existing Gmail credentials ───────────────────
    # Copy every row from google_credentials into connected_accounts, mapping
    # provider-specific column names to the generic equivalents.  Token
    # ciphertext is copied verbatim — no re-encryption required.
    #
    # ON CONFLICT DO NOTHING makes the INSERT idempotent so a failed-then-
    # retried upgrade never raises a duplicate-key error.
    #
    # SQLite (used in tests) has supported RENAME COLUMN since 3.25.0 but does
    # NOT support the ON CONFLICT clause in INSERT … SELECT, so we use a
    # dialect-specific INSERT form there.
    if _is_sqlite():
        op.execute(
            sa.text(
                """
                INSERT OR IGNORE INTO connected_accounts
                    (id, user_id, provider_type, provider_email, provider_sub,
                     access_token_enc, refresh_token_enc, token_expiry,
                     scopes, history_id, created_at, updated_at)
                SELECT
                    id,
                    user_id,
                    'gmail'        AS provider_type,
                    google_email   AS provider_email,
                    google_sub     AS provider_sub,
                    access_token_enc,
                    refresh_token_enc,
                    token_expiry,
                    scopes,
                    history_id,
                    created_at,
                    updated_at
                FROM google_credentials
                """
            )
        )
    else:
        # PostgreSQL — standard ON CONFLICT clause.
        op.execute(
            sa.text(
                """
                INSERT INTO connected_accounts
                    (id, user_id, provider_type, provider_email, provider_sub,
                     access_token_enc, refresh_token_enc, token_expiry,
                     scopes, history_id, created_at, updated_at)
                SELECT
                    id,
                    user_id,
                    'gmail'        AS provider_type,
                    google_email   AS provider_email,
                    google_sub     AS provider_sub,
                    access_token_enc,
                    refresh_token_enc,
                    token_expiry,
                    scopes,
                    history_id,
                    created_at,
                    updated_at
                FROM google_credentials
                ON CONFLICT (user_id) DO NOTHING
                """
            )
        )

    # ── Steps 3–7: Rename columns + swap unique constraint on draft_reviews
    #
    # We use batch_alter_table so this works on both PostgreSQL (native ALTER
    # TABLE RENAME COLUMN) and SQLite (copy-and-move table rebuild, which is
    # the only way SQLite supports constraint/column changes).  On PostgreSQL,
    # batch mode issues the same ALTER TABLE statements as the direct ops would,
    # so there is no performance or behaviour difference in production.
    #
    # SQLite note: the unique constraint from migration 0010 was created as a
    # plain index (CREATE UNIQUE INDEX), not as an inline CONSTRAINT clause.
    # batch_alter_table's drop_constraint looks for named constraints, which
    # don't exist on SQLite.  We therefore drop it as an index on SQLite and
    # as a named constraint on PostgreSQL.
    if _is_sqlite():
        op.drop_index(
            "uq_draft_reviews_user_gmail_message",
            table_name="draft_reviews",
        )

    with op.batch_alter_table("draft_reviews") as batch_op:
        # Steps 3–5: rename
        batch_op.alter_column(
            "gmail_message_id",
            new_column_name="provider_message_id",
            existing_type=sa.String(length=128),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "gmail_thread_id",
            new_column_name="provider_thread_id",
            existing_type=sa.String(length=128),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "gmail_draft_id",
            new_column_name="provider_draft_id",
            existing_type=sa.String(length=128),
            existing_nullable=True,
        )
        if not _is_sqlite():
            # Step 6 (PostgreSQL only): drop the named unique constraint.
            # SQLite already dropped it as an index above.
            batch_op.drop_constraint(
                "uq_draft_reviews_user_gmail_message",
                type_="unique",
            )
            # Step 7 (PostgreSQL): add the new named constraint inside batch.
            batch_op.create_unique_constraint(
                "uq_draft_reviews_user_provider_message",
                ["user_id", "provider_message_id"],
            )

    # Step 7 (SQLite only): batch_alter_table creates anonymous autoindex
    # entries for create_unique_constraint rather than named indexes.
    # Create the named unique index explicitly outside the batch so it has
    # the canonical name that the downgrade step can find and drop.
    if _is_sqlite():
        op.create_index(
            "uq_draft_reviews_user_provider_message",
            "draft_reviews",
            ["user_id", "provider_message_id"],
            unique=True,
        )


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    # ── Reverse steps 3–7: rename columns back + restore original constraint
    if _is_sqlite():
        # On SQLite the new constraint is a named index; drop it explicitly.
        op.drop_index(
            "uq_draft_reviews_user_provider_message",
            table_name="draft_reviews",
        )

    with op.batch_alter_table("draft_reviews") as batch_op:
        if not _is_sqlite():
            # Reverse step 7 (PostgreSQL): drop named constraint.
            batch_op.drop_constraint(
                "uq_draft_reviews_user_provider_message",
                type_="unique",
            )
        # Reverse steps 3–5: rename back
        batch_op.alter_column(
            "provider_draft_id",
            new_column_name="gmail_draft_id",
            existing_type=sa.String(length=128),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "provider_thread_id",
            new_column_name="gmail_thread_id",
            existing_type=sa.String(length=128),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "provider_message_id",
            new_column_name="gmail_message_id",
            existing_type=sa.String(length=128),
            existing_nullable=False,
        )
        if not _is_sqlite():
            # Reverse step 6 (PostgreSQL): restore the original named constraint.
            batch_op.create_unique_constraint(
                "uq_draft_reviews_user_gmail_message",
                ["user_id", "gmail_message_id"],
            )

    # Reverse step 6 (SQLite): restore original named unique index.
    if _is_sqlite():
        op.create_index(
            "uq_draft_reviews_user_gmail_message",
            "draft_reviews",
            ["user_id", "gmail_message_id"],
            unique=True,
        )

    # ── Reverse step 2: no-op — data in connected_accounts is redundant ──
    # We do NOT delete rows from connected_accounts here because a clean
    # downgrade should leave google_credentials untouched; the data copy was
    # one-directional.  Deleting from connected_accounts on downgrade risks
    # data loss if rows were added by other providers since the upgrade.

    # ── Reverse step 1: drop the table and its index ─────────────────────
    op.drop_index("ix_connected_accounts_user_id", table_name="connected_accounts")
    op.drop_table("connected_accounts")
