import asyncio
import sys
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from app.core.database import AsyncSessionLocal
from app.repositories.user import UserRepository
from app.core.security import hash_password
from app.models.user import UserRole


async def create_admin():
    async with AsyncSessionLocal() as session:
        repo = UserRepository(session)
        user = await repo.get_by_email("admin2@firstmed.com")
        if not user:
            user = await repo.create(
                email="admin2@firstmed.com",
                hashed_password=hash_password("AdminSecret123!"),
                full_name="Second Admin User",
                role=UserRole.ADMIN,
            )
            print(f"[SUCCESS] Created Admin user: {user.email}")
        else:
            user.hashed_password = hash_password("AdminSecret123!")
            user.role = UserRole.ADMIN
            user.is_active = True
            await session.commit()
            print(f"[SUCCESS] Updated user to Admin: {user.email}")


if __name__ == "__main__":
    asyncio.run(create_admin())
