# Phase 4 — Retrieval / Search over Gmail + Notion

**Goal:** Build a unified, searchable index of content ingested from Gmail and
Notion, so later phases can retrieve relevant context (SOPs, prior emails) when
triaging and drafting. This is the retrieval foundation; **semantic (embedding)
search is Phase 5** and plugs in behind the same interface.

## What was built

### Unified index — `documents`
A normalized, searchable copy of each ingested item.
```
documents
  id             UUID  PK
  source         str   (gmail | notion), indexed
  source_id      str   -- external id (gmail message id / notion page id)
  title          str
  content        text  -- normalized plain text
  url            text  nullable
  doc_metadata   json  -- source-specific extras (thread_id, from, object, …)
  created_at / updated_at
  UNIQUE (source, source_id)   -- re-ingest updates the same row (idempotent)
```
Migration: `0003_documents`.

### Services
- **`services/ingestion_service.py`** — reads from `GmailService` (per-user
  shared inbox) and `NotionService` (workspace) and upserts `Document` rows.
  `reindex(user)` runs every available source and **skips unavailable ones
  gracefully** (Gmail not linked / Notion not configured are reported in
  `notes`, not errors). Idempotent via the `(source, source_id)` unique key.
- **`services/search_service.py`** — lexical search: fetch candidates matching
  any query term (case-insensitive `ILIKE`, portable across SQLite/Postgres),
  then rank in memory by weighted term frequency (title ×3, body ×1). Empty
  query → browse mode (most-recent first).

### API (`/api/v1/search`, auth required)
- `GET /search?q=&source=&limit=` — ranked hits (`score` + document).
- `GET /search/stats` — index size per source.
- `POST /search/reindex` — ingest Gmail + Notion into the index; returns counts
  and skip notes.
- `GET /search/documents/{id}` — a single indexed document.
- `GET /search/status` — `implemented: true`.

Unknown `source` filter values → `400`; missing document → `404`.

## Design notes
- **No new dependencies.** Ranking is pure Python over `ILIKE`-filtered
  candidates — enough for the current corpus and fully testable offline.
- Gmail documents currently index subject + sender + snippet (Phase 2 exposes
  metadata + snippet, not full bodies); richer body extraction lands when the
  Gmail service grows message-body parsing.
- Synchronous reindex is fine at this scale; moving ingestion onto the Celery
  worker (incremental sync, scheduling) is a later-phase concern.

## How to verify
```bash
cd backend && pytest          # 80 tests (incl. ranking + ingestion + search API)
ruff check . && ruff format --check .
```
Gmail/Notion are mocked in tests via injected fakes / `httpx.MockTransport`.

## Not in this phase (deliberately)
Embeddings / vector search (Phase 5), chunking, incremental/scheduled sync,
Postgres full-text (`tsvector`) or `pgvector`, and relevance tuning beyond the
simple term-frequency weighting.
