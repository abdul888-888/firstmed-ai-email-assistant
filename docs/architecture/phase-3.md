# Phase 3 — Notion Integration (Knowledge Base Read Access)

**Goal:** Give the backend read access to the FirstMed Notion workspace — SOPs,
FAQs, and templates — so later phases can retrieve and ground responses on it.

## What was built

### Notion service (`services/notion_service.py`)
Async `httpx` client for the Notion REST API (`https://api.notion.com/v1`),
authenticated with a **server-side internal integration token** (`NOTION_API_KEY`).
Read-only. Simplifies Notion's deeply-nested objects down to what the assistant
needs (id, title, url, timestamps, plain-text block content), passing raw page
`properties` through for callers that want more.

Methods: `get_connection` (`/users/me`), `search`, `get_page`,
`get_page_content` (block children → text), `query_database`.

### API endpoints (`/api/v1/notion`, all require a logged-in staff user)
- `GET /status` — now reports `implemented: true`.
- `GET /connection` — whether Notion is configured (+ bot/workspace name).
- `GET /search?q=&page_size=` — search visible pages/databases.
- `GET /pages/{page_id}` — page metadata + properties.
- `GET /pages/{page_id}/content?page_size=` — page's child blocks as text.
- `GET /databases/{database_id}/query?page_size=` — database rows.

Error mapping: not configured → `503`; upstream Notion failure → `502`;
unauthenticated → `401`.

### Configuration (`.env` / `.env.example`)
```
NOTION_API_KEY=            # internal integration token (secret_...)
NOTION_ROOT_PAGE_ID=       # optional; page/space the integration is shared into
NOTION_VERSION=2022-06-28  # Notion-Version request header
```
`settings.notion_configured` gates the endpoints. The Notion integration must be
**shared into** the pages/databases it should see (Notion's per-integration
access model) — a page the integration can't see simply won't appear in results.

## Why an API key (not OAuth)?
Notion access here is workspace-level and server-side (one integration for the
clinic), not per-end-user, so an internal integration token is the right model —
simpler than the per-user OAuth used for Gmail in Phase 2. Public OAuth
(multi-workspace) is out of scope.

## How to verify
```bash
cd backend && pytest          # 63 tests (incl. Notion service + API)
ruff check . && ruff format --check .
```
All Notion HTTP is mocked via `httpx.MockTransport`; no token or network needed.

## Not in this phase (deliberately)
Writing to Notion, syncing/caching Notion content locally, embedding/indexing for
retrieval (that's the RAG phase), pagination beyond a single `next_cursor`
passthrough, and recursive block-tree traversal.
