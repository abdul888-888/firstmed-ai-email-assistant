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
    """Rebuild user_role enum with uppercase values and convert existing data."""
    # Drop the old enum constraint
    op.execute(sa.text("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check CASCADE"))
    
    # Create a temporary column to store the data
    op.add_column("users", sa.Column("role_temp", sa.String(50), nullable=True))
    
    # Copy data with case conversion
    op.execute(sa.text("""
        UPDATE users 
        SET role_temp = CASE 
            WHEN role = 'admin' THEN 'ADMIN'
            WHEN role = 'front_office' THEN 'FRONT_OFFICE'
            WHEN role = 'nurse' THEN 'NURSE_SPECIALIST'
            WHEN role = 'specialist' THEN 'PHYSIOTHERAPY'
            ELSE role
        END
    """))
    
    # Drop the old role column
    op.drop_column("users", "role")
    
    # Rename temp column to role
    op.alter_column("users", "role_temp", new_column_name="role")
    
    # Recreate the enum type with uppercase values
    op.execute(sa.text("DROP TYPE IF EXISTS user_role CASCADE"))
    op.execute(sa.text("""
        CREATE TYPE user_role AS ENUM (
            'ADMIN',
            'FRONT_OFFICE',
            'PHYSIOTHERAPY',
            'GASTROENTEROLOGY',
            'LABORATORY',
            'NURSE_SPECIALIST'
        )
    """))
    
    # Convert role column back to enum
    op.alter_column("users", "role", type_=sa.Enum(
        "ADMIN",
        "FRONT_OFFICE",
        "PHYSIOTHERAPY",
        "GASTROENTEROLOGY",
        "LABORATORY",
        "NURSE_SPECIALIST",
        name="user_role"
    ))


def downgrade() -> None:
    """Revert to lowercase enum (not recommended)."""
    pass

