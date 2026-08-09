#!/usr/bin/env python3
"""Debug script to check user record and serialization."""

import asyncio
import os
import sys
sys.path.append('backend')

from backend.app.core.database import AsyncSessionLocal
from backend.app.repositories.user import UserRepository
from backend.app.schemas.user import UserRead


async def debug_user():
    """Check user record and try to serialize it."""
    
    async with AsyncSessionLocal() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_email("bscs24140@itu.edu.pk")
        
        if user:
            print(f"✅ User found: {user}")
            print(f"   ID: {user.id}")
            print(f"   Email: {user.email}")
            print(f"   Role: {user.role} (type: {type(user.role)})")
            print(f"   Department: {user.department}")
            print(f"   Active: {user.is_active}")
            print(f"   On shift: {user.is_on_shift}")
            print(f"   Shift started: {user.shift_started_at}")
            print(f"   Created: {user.created_at}")
            print(f"   Updated: {user.updated_at}")
            
            # Try to serialize to UserRead
            try:
                user_read = UserRead.model_validate(user)
                print(f"✅ UserRead serialization successful")
                print(f"   Serialized: {user_read.model_dump_json()}")
            except Exception as e:
                print(f"❌ UserRead serialization failed: {type(e).__name__}: {e}")
                
        else:
            print(f"❌ User not found")

if __name__ == "__main__":
    asyncio.run(debug_user())