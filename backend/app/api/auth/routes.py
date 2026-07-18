"""Authentication: local email/password + Google OAuth staff SSO.

Local email/password auth issues JWT bearer tokens. Google SSO (Phase 2) runs
the OAuth authorization-code flow, provisions/links the staff user, stores their
(encrypted) Gmail credentials, and issues the same JWT.
"""

# NOTE: no ``from __future__ import annotations`` here (deliberately, unlike most
# other modules in this codebase). slowapi's ``@limiter.limit(...)`` decorator
# wraps these endpoints, and FastAPI resolves string annotations using the
# *wrapper's* ``__globals__`` (slowapi's module, not this one) — under postponed
# evaluation that breaks dependency/body-model resolution for the decorated
# routes (e.g. ``UserCreate`` silently falls back to a query param). Eager
# (real, non-string) annotations sidestep this entirely.

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.crypto import encrypt
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.rate_limit import AUTH_RATE_LIMIT, limiter
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.repositories.google_credential import GoogleCredentialRepository
from app.repositories.user import UserRepository
from app.schemas.auth import GoogleAuthorizationURL, Token
from app.schemas.user import UserCreate, UserRead
from app.services import google_oauth

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger(__name__)


def _require_google_configured() -> None:
    if not settings.google_oauth_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured on this server",
        )


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new staff user",
)
@limiter.limit(AUTH_RATE_LIMIT)
async def register(
    request: Request,
    payload: UserCreate,
    session: AsyncSession = Depends(get_db),
) -> User:
    repo = UserRepository(session)
    if await repo.get_by_email(payload.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )
    user = await repo.create(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
    )
    logger.info("auth.user_registered", user_id=str(user.id), role=user.role.value)
    return user


@router.post("/login", response_model=Token, summary="Obtain an access token")
@limiter.limit(AUTH_RATE_LIMIT)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(OAuth2PasswordRequestForm),
    session: AsyncSession = Depends(get_db),
) -> Token:
    # OAuth2 form uses ``username``; we treat it as the email.
    user = await UserRepository(session).get_by_email(form_data.username)
    # ``hashed_password`` is None for SSO-only accounts, which can't password-login.
    if (
        user is None
        or user.hashed_password is None
        or not verify_password(form_data.password, user.hashed_password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive"
        )
    token = create_access_token(str(user.id), extra_claims={"role": user.role.value})
    logger.info("auth.login_success", user_id=str(user.id))
    return Token(access_token=token)


@router.get("/me", response_model=UserRead, summary="Get the current user")
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


# --- Google OAuth (staff SSO) --------------------------------------------


@router.get(
    "/google/login",
    response_model=GoogleAuthorizationURL,
    summary="Begin Google OAuth (returns the consent-screen URL)",
)
@limiter.limit(AUTH_RATE_LIMIT)
async def google_login(request: Request) -> GoogleAuthorizationURL:
    _require_google_configured()
    state = google_oauth.make_state()
    return GoogleAuthorizationURL(
        authorization_url=google_oauth.build_authorization_url(state),
        state=state,
    )


@router.get(
    "/google/callback",
    summary="Google OAuth redirect target; provisions the user and issues a token",
)
@limiter.limit(AUTH_RATE_LIMIT)
async def google_callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    _require_google_configured()

    def _redirect_error(reason: str) -> RedirectResponse:
        return RedirectResponse(
            url=f"{settings.frontend_base_url}/auth/callback#error={reason}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if error:
        logger.info("auth.google_denied", reason=error)
        return _redirect_error(error)
    if not code or not state or not google_oauth.verify_state(state):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or missing OAuth code/state",
        )

    try:
        tokens = await google_oauth.exchange_code(code)
        if not tokens.id_token:
            raise google_oauth.GoogleOAuthError("no id_token in token response")
        profile = google_oauth.decode_id_token(tokens.id_token)
    except google_oauth.GoogleOAuthError as exc:
        logger.warning("auth.google_exchange_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Google authentication failed",
        ) from exc

    users = UserRepository(session)
    user = await users.get_by_email(profile.email)
    if user is None:
        user = await users.create(
            email=profile.email,
            hashed_password=None,
            full_name=profile.name,
        )
        logger.info("auth.google_user_provisioned", user_id=str(user.id))
    elif not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive"
        )

    await GoogleCredentialRepository(session).upsert(
        user_id=user.id,
        google_sub=profile.sub,
        google_email=profile.email,
        access_token_enc=encrypt(tokens.access_token),
        refresh_token_enc=encrypt(tokens.refresh_token) if tokens.refresh_token else None,
        token_expiry=tokens.expiry,
        scopes=tokens.scope,
    )

    app_token = create_access_token(str(user.id), extra_claims={"role": user.role.value})
    logger.info("auth.google_login_success", user_id=str(user.id))
    # Token is delivered in the URL fragment (not sent to servers / access logs).
    return RedirectResponse(
        url=f"{settings.frontend_base_url}/auth/callback#access_token={app_token}&token_type=bearer",
        status_code=status.HTTP_303_SEE_OTHER,
    )
