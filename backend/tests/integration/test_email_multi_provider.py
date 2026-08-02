"""Integration tests for multi-provider email system (Phase 1–2).

Tests the provider abstraction layer, factory dispatch, workflow service
refactor, and API endpoints across all provider types (Gmail, Outlook stub,
IMAP/SMTP).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from app.core.crypto import encrypt
from app.core.email import (
    BaseEmailProvider,
    EmailProviderError,
    EmailProviderNotConnectedError,
    get_email_provider,
    GmailProvider,
    ImapSmtpProvider,
    MSGraphProvider,
)
from app.models.connected_account import ConnectedAccount
from app.models.user import User
from app.repositories.connected_account import ConnectedAccountRepository
from app.repositories.user import UserRepository
from app.schemas.email import NormalizedEmail
from app.services.workflow_service import WorkflowService
from sqlalchemy.ext.asyncio import AsyncSession


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    repo = UserRepository(db_session)
    return await repo.create(
        email="test@example.com",
        hashed_password="hashed",
        full_name="Test User",
    )


@pytest.fixture
async def gmail_account(db_session: AsyncSession, test_user: User) -> ConnectedAccount:
    """Create a test Gmail connected account."""
    repo = ConnectedAccountRepository(db_session)
    return await repo.create(
        user_id=test_user.id,
        provider_type="gmail",
        provider_email="test@gmail.com",
        provider_sub="1234567890",
        access_token_enc=encrypt("test_access_token"),
        refresh_token_enc=encrypt("test_refresh_token"),
        token_expiry=datetime.utcnow() + timedelta(hours=1),
        scopes="openid email profile",
    )


@pytest.fixture
async def imap_account(db_session: AsyncSession, test_user: User) -> ConnectedAccount:
    """Create a test IMAP/SMTP connected account."""
    repo = ConnectedAccountRepository(db_session)
    return await repo.create(
        user_id=test_user.id,
        provider_type="imap_smtp",
        provider_email="user@zimbra.example.com",
        imap_host="mail.zimbra.example.com",
        imap_port=993,
        smtp_host="mail.zimbra.example.com",
        smtp_port=587,
        imap_username="user",
        imap_password_enc=encrypt("imap_password"),
    )


@pytest.fixture
async def outlook_account(db_session: AsyncSession, test_user: User) -> ConnectedAccount:
    """Create a test Outlook connected account."""
    repo = ConnectedAccountRepository(db_session)
    return await repo.create(
        user_id=test_user.id,
        provider_type="outlook",
        provider_email="test@outlook.com",
        provider_sub="outlook_sub_123",
        access_token_enc=encrypt("outlook_token"),
        refresh_token_enc=encrypt("outlook_refresh"),
        token_expiry=datetime.utcnow() + timedelta(hours=1),
        scopes="Mail.Read",
    )


class FakeEmailProvider(BaseEmailProvider):
    """Fake provider for testing without external APIs."""

    def __init__(self):
        self.messages: list[NormalizedEmail] = []
        self.created_drafts: list[dict] = []
        self.sent_drafts: list[str] = []

    async def fetch_messages(
        self, history_id: str | None = None, *, max_results: int = 25, query: str | None = None
    ) -> tuple[list[NormalizedEmail], str | None]:
        """Return test messages."""
        return self.messages[:max_results], "fake_cursor_001"

    async def get_message(self, message_id: str) -> NormalizedEmail:
        """Fetch a single test message."""
        for msg in self.messages:
            if msg.external_message_id == message_id:
                return msg
        raise EmailProviderError(f"Message {message_id} not found", status_code=404)

    async def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        *,
        thread_id: str | None = None,
        in_reply_to: str | None = None,
    ) -> str:
        """Create a test draft."""
        draft_id = f"draft_{len(self.created_drafts)}"
        self.created_drafts.append(
            {"id": draft_id, "to": to, "subject": subject, "body": body}
        )
        return draft_id

    async def send_draft(self, draft_id: str) -> str:
        """Send a test draft."""
        self.sent_drafts.append(draft_id)
        return f"msg_{draft_id}"

    async def send_email(
        self, to: str, subject: str, body: str, *, thread_id: str | None = None
    ) -> str:
        """Send a test email."""
        msg_id = f"msg_{len(self.sent_drafts)}"
        self.sent_drafts.append(msg_id)
        return msg_id


# ============================================================================
# Factory Tests
# ============================================================================


@pytest.mark.asyncio
async def test_factory_returns_gmail_provider(gmail_account, db_session):
    """Factory should return GmailProvider for Gmail accounts."""
    provider = get_email_provider(gmail_account, db_session)
    assert isinstance(provider, GmailProvider)
    assert provider.account == gmail_account


@pytest.mark.asyncio
async def test_factory_returns_imap_provider(imap_account, db_session):
    """Factory should return ImapSmtpProvider for IMAP accounts."""
    provider = get_email_provider(imap_account, db_session)
    assert isinstance(provider, ImapSmtpProvider)
    assert provider.account == imap_account


@pytest.mark.asyncio
async def test_factory_returns_outlook_provider(outlook_account, db_session):
    """Factory should return MSGraphProvider for Outlook accounts."""
    provider = get_email_provider(outlook_account, db_session)
    assert isinstance(provider, MSGraphProvider)
    assert provider.account == outlook_account


@pytest.mark.asyncio
async def test_factory_raises_on_unknown_provider(gmail_account, db_session):
    """Factory should raise ValueError for unknown provider type."""
    gmail_account.provider_type = "unknown_provider"
    with pytest.raises(ValueError, match="Unknown provider type"):
        get_email_provider(gmail_account, db_session)


# ============================================================================
# Connected Account Repository Tests
# ============================================================================


@pytest.mark.asyncio
async def test_create_gmail_account(db_session, test_user):
    """Should create a Gmail connected account."""
    repo = ConnectedAccountRepository(db_session)
    account = await repo.create(
        user_id=test_user.id,
        provider_type="gmail",
        provider_email="test@gmail.com",
        provider_sub="1234567890",
    )
    assert account.provider_type == "gmail"
    assert account.provider_email == "test@gmail.com"
    assert account.user_id == test_user.id


@pytest.mark.asyncio
async def test_upsert_replaces_existing_account(db_session, test_user):
    """Upsert should replace existing account for a user."""
    repo = ConnectedAccountRepository(db_session)
    account1 = await repo.create(
        user_id=test_user.id,
        provider_type="gmail",
        provider_email="old@gmail.com",
    )
    account2 = await repo.upsert(
        user_id=test_user.id,
        provider_type="imap_smtp",
        provider_email="new@example.com",
        imap_host="mail.example.com",
        imap_port=993,
        smtp_host="mail.example.com",
        smtp_port=587,
        imap_password_enc=encrypt("pass"),
    )
    # Should be same ID (updated in place).
    assert account2.id == account1.id
    assert account2.provider_type == "imap_smtp"
    assert account2.provider_email == "new@example.com"


@pytest.mark.asyncio
async def test_get_by_user_id(db_session, test_user, gmail_account):
    """Should retrieve account by user ID."""
    repo = ConnectedAccountRepository(db_session)
    account = await repo.get_by_user_id(test_user.id)
    assert account is not None
    assert account.id == gmail_account.id
    assert account.provider_email == "test@gmail.com"


@pytest.mark.asyncio
async def test_list_connected_user_ids_filters_active(db_session, test_user, gmail_account):
    """list_connected_user_ids should only return active users."""
    repo = ConnectedAccountRepository(db_session)
    user_ids = await repo.list_connected_user_ids()
    assert test_user.id in user_ids

    # Deactivate user.
    test_user.is_active = False
    await db_session.commit()

    # Should be filtered out.
    user_ids = await repo.list_connected_user_ids()
    assert test_user.id not in user_ids


# ============================================================================
# WorkflowService Tests with FakeEmailProvider
# ============================================================================


@pytest.mark.asyncio
async def test_workflow_service_with_injected_provider(db_session, test_user):
    """WorkflowService should use injected provider."""
    fake_provider = FakeEmailProvider()
    svc = WorkflowService(db_session, email_provider=fake_provider)

    # The injected provider should be returned by _provider().
    resolved = await svc._provider(None)
    assert resolved is fake_provider


@pytest.mark.asyncio
async def test_workflow_service_rejects_no_account(db_session, test_user):
    """WorkflowService._provider should reject when no account and no injected provider."""
    svc = WorkflowService(db_session)
    with pytest.raises(EmailProviderNotConnectedError):
        await svc._provider(None)


# ============================================================================
# API Endpoint Tests
# ============================================================================


@pytest.mark.asyncio
async def test_connection_status_no_account(client, test_user):
    """GET /email/connection should return connected:false when no account."""
    # Create user and log in.
    from app.core.security import create_access_token

    token = create_access_token(str(test_user.id))
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.get("/api/v1/email/connection", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"connected": False}


@pytest.mark.asyncio
async def test_connection_status_with_account(client, test_user, gmail_account, db_session):
    """GET /email/connection should return account info when connected."""
    from app.core.security import create_access_token

    token = create_access_token(str(test_user.id))
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.get("/api/v1/email/connection", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is True
    assert body["provider_type"] == "gmail"
    assert body["provider_email"] == "test@gmail.com"


@pytest.mark.asyncio
async def test_fetch_messages_no_account(client, test_user):
    """GET /email/messages should return 404 when no account connected."""
    from app.core.security import create_access_token

    token = create_access_token(str(test_user.id))
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.get("/api/v1/email/messages", headers=headers)
    assert resp.status_code == 404
    assert "No email account connected" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_draft_no_account(client, test_user):
    """POST /email/drafts should return 404 when no account connected."""
    from app.core.security import create_access_token

    token = create_access_token(str(test_user.id))
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post(
        "/api/v1/email/drafts",
        json={
            "to": "user@example.com",
            "subject": "Test",
            "body": "Test body",
        },
        headers=headers,
    )
    assert resp.status_code == 404


# ============================================================================
# IMAP Connect Endpoint Tests
# ============================================================================


@pytest.mark.asyncio
async def test_imap_connect_success(client, test_user):
    """POST /auth/imap/connect should create an IMAP account."""
    from app.core.security import create_access_token

    token = create_access_token(str(test_user.id))
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post(
        "/api/v1/auth/imap/connect",
        json={
            "imap_host": "mail.example.com",
            "imap_port": 993,
            "smtp_host": "mail.example.com",
            "smtp_port": 587,
            "username": "user@example.com",
            "password": "secret",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["connected"] is True
    assert body["provider_email"] == "user@example.com"


@pytest.mark.asyncio
async def test_imap_connect_invalid_port(client, test_user):
    """POST /auth/imap/connect should reject invalid ports."""
    from app.core.security import create_access_token

    token = create_access_token(str(test_user.id))
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post(
        "/api/v1/auth/imap/connect",
        json={
            "imap_host": "mail.example.com",
            "imap_port": 9999,  # Invalid port
            "smtp_host": "mail.example.com",
            "smtp_port": 587,
            "username": "user@example.com",
            "password": "secret",
        },
        headers=headers,
    )
    assert resp.status_code == 422
    assert "imap_port must be one of" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_imap_connect_invalid_hostname(client, test_user):
    """POST /auth/imap/connect should reject invalid hostnames."""
    from app.core.security import create_access_token

    token = create_access_token(str(test_user.id))
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post(
        "/api/v1/auth/imap/connect",
        json={
            "imap_host": "http://mail.example.com",  # Protocol prefix
            "imap_port": 993,
            "smtp_host": "mail.example.com",
            "smtp_port": 587,
            "username": "user@example.com",
            "password": "secret",
        },
        headers=headers,
    )
    assert resp.status_code == 422
    assert "valid hostnames" in resp.json()["detail"]


# ============================================================================
# Review Approve/Send Endpoint Tests
# ============================================================================


@pytest.mark.asyncio
async def test_approve_requires_account(client, test_user):
    """POST /reviews/{id}/approve should return 409 if no account connected."""
    from app.core.security import create_access_token

    # Create a pending review for the user.
    from app.models.draft_review import DraftReview

    review = DraftReview(
        user_id=test_user.id,
        provider_message_id="msg_123",
        sender="sender@example.com",
        subject="Test email",
        status="pending",
        classification="admin_direct_reply",
        intent="appointment",
        urgency="normal",
        department="front_office",
        confidence=0.9,
        draft_body="Test draft",
    )

    token = create_access_token(str(test_user.id))
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post(
        f"/api/v1/reviews/{review.id}/approve",
        headers=headers,
    )
    assert resp.status_code == 404
    assert "No email account connected" in resp.json()["detail"]


# ============================================================================
# NormalizedEmail Schema Tests
# ============================================================================


@pytest.mark.asyncio
async def test_normalized_email_identity_by_provider_and_message_id():
    """NormalizedEmail should use (provider_type, external_message_id) for identity."""
    msg1 = NormalizedEmail(
        provider_type="gmail",
        external_message_id="12345",
        sender="test@example.com",
        subject="Test",
        received_at=datetime.utcnow(),
    )
    msg2 = NormalizedEmail(
        provider_type="gmail",
        external_message_id="12345",
        sender="different@example.com",  # Different sender
        subject="Different subject",
        received_at=datetime.utcnow(),
    )
    # Should be equal despite different fields (same provider + message ID).
    assert msg1 == msg2
    assert hash(msg1) == hash(msg2)


@pytest.mark.asyncio
async def test_normalized_email_different_message_ids():
    """NormalizedEmail with different message IDs should not be equal."""
    msg1 = NormalizedEmail(
        provider_type="gmail",
        external_message_id="12345",
        sender="test@example.com",
        subject="Test",
        received_at=datetime.utcnow(),
    )
    msg2 = NormalizedEmail(
        provider_type="gmail",
        external_message_id="54321",
        sender="test@example.com",
        subject="Test",
        received_at=datetime.utcnow(),
    )
    assert msg1 != msg2
    assert hash(msg1) != hash(msg2)


@pytest.mark.asyncio
async def test_normalized_email_utc_coercion():
    """NormalizedEmail should coerce naive datetimes to UTC."""
    naive_dt = datetime(2024, 1, 1, 12, 0, 0)  # Naive
    msg = NormalizedEmail(
        provider_type="gmail",
        external_message_id="12345",
        sender="test@example.com",
        subject="Test",
        received_at=naive_dt,
    )
    # Should be coerced to UTC-aware.
    assert msg.received_at.tzinfo is not None
    assert msg.received_at.tzinfo.utcoffset(None).total_seconds() == 0
