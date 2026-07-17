# Phase 1 — Project Foundation

**Goal:** Establish the project architecture and development environment so that
later phases plug into a clean, production-grade base.

## What was built

### Monorepo
```
backend/   FastAPI app (clean layered architecture) + tests + migrations
frontend/  Next.js (App Router) + TS + Tailwind + shadcn/ui + TanStack Query
shared/    prompts / workflows / templates / schemas / constants
docs/      architecture / api / workflows / deployment / security / user-guide
docker/    container assets
.github/   CI workflow
```

### Backend layers (`backend/app`)
- **core/** — `config` (pydantic-settings), `logging` (structlog + PII masking),
  `security` (JWT + password hashing), `database` (async SQLAlchemy engine/session).
- **api/** — versioned router (`/api/v1`) with `health` and an auth **skeleton**
  (`register`, `login`, `me`). Sub-package folders exist for `gmail`, `notion`,
  `healzz`, `drafts`, `workflows`, `analytics`, `admin` (filled in later phases).
- **models/** — SQLAlchemy `Base`, `TimestampMixin`, and the `User` model with a
  `UserRole` enum (front_office, nurse, specialist, admin — per PRD).
- **schemas/** — Pydantic v2 request/response models.
- **repositories/** — data-access layer (`UserRepository`).
- **services/**, **workers/**, **tasks/**, **middleware/**, **utils/** — seams for
  later phases (Celery app + example task, request-id middleware, PII utils).

### Infrastructure
- `docker-compose.yml` — Postgres 16, Redis 7, backend, frontend, with healthchecks.
- Backend + frontend `Dockerfile`s.
- GitHub Actions CI: backend (ruff + pytest) and frontend (lint + typecheck + build).

## Data model (Phase 1)

```
users
  id            UUID  PK
  email         str   unique, indexed
  hashed_password str
  full_name     str
  role          enum(front_office|nurse|specialist|admin)
  is_active     bool
  created_at    datetime
  updated_at    datetime
```

## Health checks
- `GET /api/v1/health` — liveness (always fast, no dependencies).
- `GET /api/v1/health/ready` — readiness; checks DB connectivity and Redis ping.
- Frontend `GET /api/health` — returns `{status, backend}` and proxies backend liveness.

## How to verify
See the repo root [README](../../README.md#testing). In short:

```bash
cd backend && pip install -r requirements.txt -r requirements-dev.txt && pytest
cd frontend && npm install && npm run typecheck && npm run build
docker compose config      # validates the compose file
```

## Not in this phase (deliberately)
Gmail/Notion/Healzz integrations, RAG, intent classification, workflow engine,
templates, draft generation, and the full dashboard — these are Phases 2–13.
Auth here is a **skeleton** (local email/password + JWT); Google OAuth arrives in Phase 2.
