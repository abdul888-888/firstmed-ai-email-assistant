"""Shared FastAPI dependencies (auth, current user, RBAC)."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Coroutine
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User, UserRole
from app.repositories.user import UserRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_v1_prefix}/auth/login")

_CREDENTIALS_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the authenticated user from a bearer token."""
    print(f"\n[AUTH DEBUG] Token received: {token[:50] if token else 'NONE'}...")

    try:
        payload = decode_access_token(token)
        subject = payload.get("sub")
        print(f"[AUTH DEBUG] Token decoded. Subject (user ID): {subject}")

        if not subject:
            print(f"[AUTH DEBUG] ERROR: No subject in token payload")
            raise _CREDENTIALS_EXC

        user_id = uuid.UUID(str(subject))
        print(f"[AUTH DEBUG] Converted to UUID: {user_id}")
    except (jwt.PyJWTError, ValueError) as exc:
        print(f"[AUTH DEBUG] ERROR: Token decode failed: {type(exc).__name__}: {exc}")
        raise _CREDENTIALS_EXC from exc

    user = await UserRepository(session).get_by_id(user_id)
    print(f"[AUTH DEBUG] Database lookup: user={user.email if user else 'NOT FOUND'}, active={user.is_active if user else 'N/A'}")

    if user is None or not user.is_active:
        print(f"[AUTH DEBUG] ERROR: User not found or inactive")
        raise _CREDENTIALS_EXC

    print(f"[AUTH DEBUG] SUCCESS: Authenticated as {user.email}")
    return user


def require_roles(
    *roles: UserRole,
) -> Callable[[User], Coroutine[Any, Any, User]]:
    """Dependency factory enforcing that the current user has one of ``roles``."""

    async def _dependency(current_user: User = Depends(get_current_user)) -> User:
        if roles and current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this resource",
            )
        return current_user

    return _dependency
