#!/usr/bin/env python
"""
Set up admin users for the FirstMed backend.

Usage:
    cd backend
    source .venv/bin/activate  # or .venv\Scripts\Activate.ps1 on Windows
    python scripts/setup_admin_user.py <email> [name] [database_url]

This script creates or updates a user with the ADMIN role.

Examples:
    # Local development (SQLite)
    python scripts/setup_admin_user.py admin@example.com "Admin User"
    
    # Production/Staging (PostgreSQL on Railway)
    python scripts/setup_admin_user.py admin@example.com "Admin User" "postgresql://user:pass@host:port/db"
"""

import asyncio
import sys
from pathlib import Path

# Add parent to path so imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.core.config import settings
from app.models.user import User, UserRole
from app.core.security import hash_password


async def setup_admin_user(email: str, full_name: str | None = None, database_url: str | None = None) -> None:
    """Create or update a user with ADMIN role."""
    # Use provided database URL or fall back to settings
    db_url = database_url or settings.sqlalchemy_database_uri
    db_display = db_url[:50] + "..." if len(db_url) > 50 else db_url
    print(f"Using database: {db_display}")
    
    engine = create_async_engine(db_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Check if user exists
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalars().first()
        
        if user:
            print(f"Found existing user: {user.email}")
            print(f"  Current role: {user.role.value}")
            print(f"  Current name: {user.full_name}")
            
            user.role = UserRole.ADMIN
            user.is_active = True
            if full_name:
                user.full_name = full_name
            await session.commit()
            
            print(f"Updated:")
            print(f"  Role: {user.role.value}")
            print(f"  Name: {user.full_name}")
            print(f"  Status: Active")
        else:
            print(f"Creating new admin user: {email}")
            user = User(
                email=email,
                full_name=full_name or "Admin User",
                role=UserRole.ADMIN,
                department="ADMIN",
                is_active=True,
                is_on_shift=True,
                hashed_password=hash_password("TemporaryPassword123!")
            )
            session.add(user)
            await session.commit()
            
            print(f"Created new admin user:")
            print(f"  Email: {user.email}")
            print(f"  Role: {user.role.value}")
            print(f"  Name: {user.full_name}")
            print(f"  Status: Active")
            print(f"  Temporary password set (should be changed on first login)")
    
    await engine.dispose()
    print("\nAdmin user setup complete!")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/setup_admin_user.py <email> [full_name] [database_url]")
        print("Example: python scripts/setup_admin_user.py admin@example.com 'John Admin'")
        print("Example with Railway: python scripts/setup_admin_user.py admin@example.com 'John' 'postgresql://...'")
        sys.exit(1)
    
    email = sys.argv[1]
    full_name = sys.argv[2] if len(sys.argv) > 2 else None
    database_url = sys.argv[3] if len(sys.argv) > 3 else None
    
    asyncio.run(setup_admin_user(email, full_name, database_url))
