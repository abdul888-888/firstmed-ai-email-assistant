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
    
    try:
        payload = decode_access_token(token)
        subject = payload.get("sub")

        if not subject:
            raise _CREDENTIALS_EXC

        user_id = uuid.UUID(str(subject))
    except (jwt.PyJWTError, ValueError) as exc:
        raise _CREDENTIALS_EXC from exc

    user = await UserRepository(session).get_by_id(user_id)

    if user is None or not user.is_active:
        raise _CREDENTIALS_EXC

    return user


def require_roles(
    *roles: UserRole,
) -> Callable[[User], Coroutine[Any, Any, User]]:
    """Dependency factory enforcing that the current user has one of ``roles``."""

    async def _dependency(current_user: User = Depends(get_current_user)) -> User:
        if roles:
            # Handle case-insensitive role comparison for PostgreSQL compatibility
            user_role_upper = current_user.role.value.upper()
            role_values = [r.value.upper() for r in roles]
            if user_role_upper not in role_values:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions for this resource",
                )
        return current_user

    return _dependency
