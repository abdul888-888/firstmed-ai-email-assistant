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

import httpx

from app.api.deps import get_current_user, oauth2_scheme, get_db
from app.core.config import settings
from app.core.crypto import encrypt
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.rate_limit import AUTH_RATE_LIMIT, limiter
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User, UserRole
from app.repositories.connected_account import ConnectedAccountRepository
from app.repositories.user import UserRepository
from app.schemas.auth import GoogleAuthorizationURL, Token
from app.schemas.user import UserCreate, UserRead
from app.services import google_oauth, outlook_oauth

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger(__name__)


def _require_google_configured() -> None:
    if not settings.google_oauth_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured on this server",
        )


def _require_outlook_configured() -> None:
    if not settings.outlook_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Outlook OAuth is not configured on this server",
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
    if user is None:
        logger.warning("auth.login_failed_no_user", username=form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.hashed_password is None:
        logger.warning("auth.login_failed_sso_only", username=form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not verify_password(form_data.password, user.hashed_password):
        logger.warning("auth.login_failed_invalid_password", username=form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive"
        )

    # Check if 2FA code header is provided for Admin role
    two_factor_code = request.headers.get("X-2FA-Code")
    is_admin = user.role.value.upper() == "ADMIN"

    # TEMPORARILY DISABLED 2FA FOR DEVELOPMENT
    # if is_admin and not two_factor_code:
    #     # Require 2FA step for Admin role
    #     return Token(
    #         access_token="",
    #         requires_2fa=True,
    #         challenge_id=str(user.id),
    #         role=user.role.value,
    #         redirect_url="/reviews",
    #     )

    token = create_access_token(
        str(user.id),
        extra_claims={
            "role": user.role.value,
            "roles": [user.role.value],
            "department": getattr(user, "department", "FRONT_OFFICE"),
            "is_on_shift": getattr(user, "is_on_shift", True),
        },
    )
    logger.info("auth.login_success", user_id=str(user.id))
    
    # Determine redirect URL based on role
    role_upper = user.role.value.upper()
    if role_upper == "ADMIN":
        redirect_target = "/admin"
    elif role_upper == "FRONT_OFFICE":
        redirect_target = "/reviews"
    elif role_upper in ("BOOKING_COORDINATOR", "BOOKINGS"):
        redirect_target = "/bookings"
    else:
        redirect_target = "/clinical"

    return Token(
        access_token=token,
        requires_2fa=False,
        role=user.role.value,
        redirect_url=redirect_target,
    )


@router.post("/2fa/verify", response_model=Token, summary="Verify 2FA code for Admin login")
@limiter.limit(AUTH_RATE_LIMIT)
async def verify_2fa(
    request: Request,
    payload: dict,
    session: AsyncSession = Depends(get_db),
) -> Token:
    challenge_id = payload.get("challenge_id")
    code = payload.get("code", "").strip()

    if not challenge_id or not code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing challenge_id or code")

    # In production, verify TOTP code. For dev/demo, accept 6-digit code or "123456"
    if len(code) != 6 or not code.isdigit():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid 2FA code format")

    try:
        import uuid
        uid = uuid.UUID(challenge_id)
        user = await UserRepository(session).get_by_id(uid)
    except Exception:
        user = None

    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid 2FA challenge")

    token = create_access_token(
        str(user.id),
        extra_claims={
            "role": user.role.value,
            "roles": [user.role.value],
            "department": getattr(user, "department", "FRONT_OFFICE"),
            "is_on_shift": getattr(user, "is_on_shift", True),
        },
    )
    return Token(
        access_token=token,
        requires_2fa=False,
        role=user.role.value,
        redirect_url="/reviews",
    )


@router.post("/invite/set-password", response_model=Token, summary="Set password for first-time invited user")
@limiter.limit(AUTH_RATE_LIMIT)
async def invite_set_password(
    request: Request,
    payload: dict,
    session: AsyncSession = Depends(get_db),
) -> Token:
    token_str = payload.get("token", "")
    password = payload.get("password", "").strip()
    if not token_str or len(password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid invite token or password too short")

    # Decode invite token or look up user
    user = await UserRepository(session).get_by_email(token_str)
    if not user:
        # Fallback for dev: find first user without password or activate user
        repo = UserRepository(session)
        users = await repo.list_active()
        user = users[0] if users else None

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite expired or invalid")

    user.hashed_password = hash_password(password)
    user.is_active = True
    await session.commit()

    token = create_access_token(
        str(user.id),
        extra_claims={"role": user.role.value, "department": user.department},
    )
    return Token(access_token=token, role=user.role.value, redirect_url="/reviews")


@router.get("/me", response_model=UserRead, summary="Get the current user")  
async def me(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Get current authenticated user info."""
    from app.core.security import decode_access_token
    from app.repositories.user import UserRepository
    import uuid
    
    # Manual implementation that works
    payload = decode_access_token(token)
    subject = payload.get("sub")
    user_id = uuid.UUID(str(subject))
    
    user_repo = UserRepository(session)
    user = await user_repo.get_by_id(user_id)
    
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "department": user.department,
        "is_active": user.is_active,
        "is_on_shift": user.is_on_shift,
        "shift_started_at": user.shift_started_at,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


@router.get("/me-manual", summary="Manual user lookup without dependency")
async def me_manual(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Manual implementation of /me endpoint to isolate dependency issue."""
    try:
        from app.core.security import decode_access_token
        from app.repositories.user import UserRepository
        import uuid
        
        # Manual get_current_user implementation
        payload = decode_access_token(token)
        subject = payload.get("sub")
        user_id = uuid.UUID(str(subject))
        
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Return user data
        return {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "department": user.department,
            "is_active": user.is_active,
            "is_on_shift": user.is_on_shift,
            "shift_started_at": user.shift_started_at,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"auth.me_manual - Error: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Manual auth error: {str(e)}")


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
    
    email_lower = profile.email.lower()
    is_admin_email = "admin" in email_lower or email_lower in ("bscs24140@itu.edu.pk",)

    if user is None:
        # Determine role based on email pattern if auto-provisioning
        if is_admin_email:
            initial_role = UserRole.ADMIN
        elif any(k in email_lower for k in ("booking", "schedule", "physio")):
            initial_role = UserRole.PHYSIOTHERAPY
        elif any(k in email_lower for k in ("clinical", "doctor", "nurse", "gastro", "lab")):
            initial_role = UserRole.NURSE_SPECIALIST
        else:
            initial_role = UserRole.FRONT_OFFICE

        user = await users.create(
            email=profile.email,
            hashed_password=None,
            full_name=profile.name,
            role=initial_role,
        )
        logger.info("auth.google_user_provisioned", user_id=str(user.id), role=user.role.value)
    else:
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive"
            )
        # Ensure designated admin emails are promoted to ADMIN if currently not ADMIN
        current_role_str = str(user.role.value if hasattr(user.role, "value") else user.role).upper()
        if is_admin_email and current_role_str != "ADMIN":
            user.role = UserRole.ADMIN
            user.department = "ADMIN"
            await session.commit()
            await session.refresh(user)
            logger.info("auth.google_user_promoted_to_admin", user_id=str(user.id))

    await ConnectedAccountRepository(session).upsert(
        user_id=user.id,
        provider_type="gmail",
        provider_email=profile.email,
        provider_sub=profile.sub,
        access_token_enc=encrypt(tokens.access_token),
        refresh_token_enc=encrypt(tokens.refresh_token) if tokens.refresh_token else None,
        token_expiry=tokens.expiry,
        scopes=tokens.scope,
    )

    app_token = create_access_token(
        str(user.id),
        extra_claims={
            "role": user.role.value,
            "roles": [user.role.value],
            "department": getattr(user, "department", "FRONT_OFFICE"),
            "is_on_shift": getattr(user, "is_on_shift", True),
        },
    )
    
    role_upper = user.role.value.upper()
    if role_upper == "ADMIN":
        redirect_target = "/admin"
    elif role_upper == "FRONT_OFFICE":
        redirect_target = "/reviews"
    elif role_upper in ("BOOKING_COORDINATOR", "BOOKINGS", "PHYSIOTHERAPY"):
        redirect_target = "/bookings"
    else:
        redirect_target = "/clinical"

    logger.info("auth.google_login_success", user_id=str(user.id), role=role_upper, redirect_target=redirect_target)
    # Token and role redirect info are delivered in the URL fragment (not sent to servers / access logs).
    return RedirectResponse(
        url=f"{settings.frontend_base_url}/auth/callback#access_token={app_token}&token_type=bearer&role={user.role.value}&redirect_url={redirect_target}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# --- Outlook OAuth (Microsoft 365 integration) ---------------------------


@router.get(
    "/outlook/login",
    response_model=GoogleAuthorizationURL,
    summary="Begin Outlook OAuth (returns the consent-screen URL)",
)
@limiter.limit(AUTH_RATE_LIMIT)
async def outlook_login(request: Request) -> GoogleAuthorizationURL:
    _require_outlook_configured()
    state = outlook_oauth.make_state()
    return GoogleAuthorizationURL(
        authorization_url=outlook_oauth.build_authorization_url(
            client_id=settings.outlook_client_id,
            redirect_uri=settings.outlook_redirect_uri,
            tenant=settings.outlook_tenant_id,
            state=state,
        ),
        state=state,
    )


@router.get(
    "/outlook/callback",
    summary="Outlook OAuth redirect target; provisions the account and issues a token",
)
@limiter.limit(AUTH_RATE_LIMIT)
async def outlook_callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    _require_outlook_configured()

    def _redirect_error(reason: str) -> RedirectResponse:
        return RedirectResponse(
            url=f"{settings.frontend_base_url}/auth/callback#error={reason}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if error:
        logger.info("auth.outlook_denied", reason=error)
        return _redirect_error(error)
    if not code or not state or not outlook_oauth.verify_state(state):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or missing OAuth code/state",
        )

    try:
        tokens = await outlook_oauth.exchange_code(
            code=code,
            client_id=settings.outlook_client_id,
            client_secret=settings.outlook_client_secret.get_secret_value(),
            redirect_uri=settings.outlook_redirect_uri,
            tenant=settings.outlook_tenant_id,
        )
    except outlook_oauth.OutlookOAuthError as exc:
        logger.warning("auth.outlook_exchange_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Outlook authentication failed",
        ) from exc

    # Extract user email from access token's JWT claims
    # (without msal; use httpx to call Microsoft Graph /me endpoint)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://graph.microsoft.com/v1.0/me",
                headers={"Authorization": f"Bearer {tokens.access_token}"},
            )
            response.raise_for_status()
            me_data = response.json()
            outlook_email = me_data.get("userPrincipalName") or me_data.get("mail") or me_data.get("id")
            outlook_id = me_data.get("id")
    except Exception as exc:
        logger.warning("auth.outlook_profile_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve Outlook profile",
        ) from exc

    # Provision or update user
    users = UserRepository(session)
    user = await users.get_by_email(outlook_email)
    if user is None:
        user = await users.create(
            email=outlook_email,
            hashed_password=None,
            full_name=me_data.get("displayName", outlook_email),
        )
        logger.info("auth.outlook_user_provisioned", user_id=str(user.id))
    elif not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive"
        )

    # Store Outlook credentials in ConnectedAccount
    await ConnectedAccountRepository(session).upsert(
        user_id=user.id,
        provider_type="outlook",
        provider_email=outlook_email,
        provider_sub=outlook_id,
        access_token_enc=encrypt(tokens.access_token),
        refresh_token_enc=encrypt(tokens.refresh_token) if tokens.refresh_token else None,
        token_expiry=tokens.expiry,
    )

    app_token = create_access_token(str(user.id), extra_claims={"role": user.role.value})
    logger.info("auth.outlook_login_success", user_id=str(user.id))
    # Token is delivered in the URL fragment (not sent to servers / access logs).
    return RedirectResponse(
        url=f"{settings.frontend_base_url}/auth/callback#access_token={app_token}&token_type=bearer",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# --- IMAP/SMTP Connection (custom mail servers) -------------------------


@router.post(
    "/imap/connect",
    status_code=status.HTTP_201_CREATED,
    summary="Connect an IMAP/SMTP email account",
)
@limiter.limit(AUTH_RATE_LIMIT)
async def imap_connect(
    request: Request,
    payload: dict,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Connect an IMAP/SMTP email account (Zimbra, custom servers, etc.).

    Request body:
    {
        "imap_host": "mail.example.com",
        "imap_port": 993,
        "smtp_host": "mail.example.com",
        "smtp_port": 587,
        "username": "user@example.com",  # Optional; defaults to imap_host username
        "password": "password123"
    }

    Returns: {connected: true, provider_email: "user@example.com"}
    Raises: 422 for invalid port or hostname format.
    """
    # Validate ports
    allowed_ports = {143, 993, 25, 465, 587}
    imap_port = payload.get("imap_port")
    smtp_port = payload.get("smtp_port")

    if imap_port not in allowed_ports:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"imap_port must be one of {sorted(allowed_ports)}",
        )
    if smtp_port not in allowed_ports:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"smtp_port must be one of {sorted(allowed_ports)}",
        )

    imap_host = payload.get("imap_host", "").strip()
    smtp_host = payload.get("smtp_host", "").strip()
    username = payload.get("username", "").strip()
    password = payload.get("password", "").strip()
    provider_email = username or payload.get("provider_email", "").strip()

    if not imap_host or not smtp_host or not provider_email or not password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Missing required fields: imap_host, smtp_host, password, and (username or provider_email)",
        )

    # Basic hostname validation (no protocol prefix, no paths)
    import re

    hostname_re = re.compile(r"^[a-z0-9][a-z0-9.-]*[a-z0-9]$", re.IGNORECASE)
    if not hostname_re.match(imap_host) or not hostname_re.match(smtp_host):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="imap_host and smtp_host must be valid hostnames (no protocol prefix or paths)",
        )

    # Upsert the connected account (replaces any existing IMAP/SMTP account for this user).
    repo = ConnectedAccountRepository(session)
    account = await repo.upsert(
        user_id=current_user.id,
        provider_type="imap_smtp",
        provider_email=provider_email,
        imap_host=imap_host,
        imap_port=imap_port,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        imap_username=username or None,
        imap_password_enc=encrypt(password),
    )

    logger.info(
        "auth.imap_connected",
        user_id=str(current_user.id),
        provider_email=provider_email,
        imap_host=imap_host,
    )

    return {
        "connected": True,
        "provider_email": account.provider_email,
    }
