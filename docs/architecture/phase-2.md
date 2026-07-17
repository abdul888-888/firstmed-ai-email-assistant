# Phase 2 — Google SSO + Gmail Read Access

**Goal:** Let staff sign in with their Google (Workspace) account and give the
backend read-only access to the shared clinical inbox, so later phases can
triage and draft against real messages.

## What was built

### Authentication — Google OAuth staff SSO
- `GET /api/v1/auth/google/login` — returns the Google consent-screen URL plus a
  signed, short-lived `state` token (stateless CSRF protection). Responds `503`
  if the server has no Google client id/secret configured.
- `GET /api/v1/auth/google/callback` — the OAuth redirect target. Validates
  `state`, exchanges the `code` for tokens, provisions or links the staff `User`
  by email, stores their (encrypted) Gmail credentials, issues our own JWT, and
  `303`-redirects to `${FRONTEND_BASE_URL}/auth/callback#access_token=…`. The
  token is delivered in the URL **fragment** so it isn't sent to servers or
  written to access logs.
- The existing email/password `login` still works; SSO-only accounts (no local
  password) correctly cannot password-login.

### Gmail — read access to the shared inbox
- `GET /api/v1/gmail/connection` — whether the current user has linked Gmail,
  with the granted scopes and the target mailbox.
- `GET /api/v1/gmail/messages?max_results=&q=` — list message ids/threads.
- `GET /api/v1/gmail/messages/{id}` — a single message's headers + snippet.
- `GET /api/v1/gmail/status` — now reports `implemented: true`.
- Access tokens are refreshed transparently (proactively when near expiry, and
  once reactively on a `401`) using the stored refresh token.

### Data model
```
google_credentials            (one-to-one with users)
  id                UUID  PK
  user_id           UUID  FK users.id (unique, cascade delete)
  google_sub        str   unique, indexed   -- Google OIDC subject
  google_email      str
  access_token_enc  text                    -- Fernet ciphertext
  refresh_token_enc text  nullable          -- Fernet ciphertext
  token_expiry      datetime nullable
  scopes            text                     -- space-separated
  created_at / updated_at
```
`users.hashed_password` is now **nullable** (SSO users have no local password).
Migration: `0002_google_credentials`.

### Security notes
- OAuth tokens are encrypted at rest with **Fernet** (`app/core/crypto.py`). The
  key comes from `TOKEN_ENCRYPTION_KEY`; in dev it is derived deterministically
  from `SECRET_KEY`. **Production must set an explicit `TOKEN_ENCRYPTION_KEY`.**
- The ID token from Google is decoded without re-verifying its signature: it is
  received directly from Google's token endpoint over server-to-server TLS,
  which Google documents as a trusted source.
- No external Google libraries are required — the flow uses `httpx` + `PyJWT`.
  The only new runtime dependency is `cryptography` (for Fernet).

## Implementation map (`backend/app`)
- `core/config.py` — Google/Gmail/frontend/token-key settings + `google_oauth_configured`.
- `core/crypto.py` — Fernet `encrypt`/`decrypt`.
- `services/google_oauth.py` — auth URL, code exchange, token refresh, id-token decode, CSRF state.
- `services/gmail_service.py` — Gmail REST calls + transparent token refresh.
- `models/google_credential.py`, `repositories/google_credential.py`.
- `api/auth/routes.py` — `google/login`, `google/callback`.
- `api/gmail/__init__.py` — `connection`, `messages`, `messages/{id}`, `status`.
- `schemas/auth.py`, `schemas/gmail.py`.

## Configuration
Set in `.env` (see `.env.example`):
```
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback
GMAIL_SHARED_INBOX=            # blank => the signed-in mailbox ("me")
GOOGLE_OAUTH_SCOPES=openid email profile https://www.googleapis.com/auth/gmail.readonly
TOKEN_ENCRYPTION_KEY=          # blank in dev; REQUIRED in prod
FRONTEND_BASE_URL=http://localhost:3000
```
The Google Cloud OAuth client must whitelist `GOOGLE_REDIRECT_URI` as an
authorized redirect URI.

## How to verify
```bash
cd backend && pytest          # 52 tests, incl. crypto / OAuth / Gmail
ruff check . && ruff format --check .
alembic upgrade head          # applies 0002_google_credentials
```
Tests mock all Google/Gmail HTTP (via `httpx.MockTransport`) and the OAuth
exchange, so no network or real credentials are needed.

## Notes / follow-ups
- **Shared-inbox delegation:** reading `users/{shared-address}/messages` with a
  per-user token requires Google Workspace domain-wide delegation (or the user
  having delegated access). With `GMAIL_SHARED_INBOX` blank the service reads the
  signed-in user's own mailbox (`me`). Wiring up delegation/service-account
  access is deferred.
- Token delivery to the SPA via URL fragment is a pragmatic Phase-2 choice; an
  httpOnly-cookie session is a candidate hardening for a later phase.
- Message body parsing (beyond headers + snippet) and inbox sync/pagination land
  with the triage/workflow phases.

## Not in this phase (deliberately)
Sending or modifying mail (read-only only), Notion (Phase 3), RAG/search
(Phase 4+), intent classification, workflow engine, and draft generation.
