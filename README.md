# FirstMed AI Administrative Email Assistant

A **human-in-the-loop** AI administrative assistant that prepares accurate Gmail
**drafts** for routine administrative inquiries at FirstMed, a multi-specialty
healthcare clinic. It **never sends email automatically**, **never provides
medical advice**, and **always escalates** clinical, legal, or uncertain matters
to staff.

> Objective: reduce repetitive administrative work while maintaining full human
> oversight over all patient communications.

---

## Project status

This is a **greenfield** project built **incrementally, one phase at a time**.
Each phase compiles and runs before the next begins.

| Phase | Title | Status |
|------:|-------|--------|
| 1 | Project Foundation | ✅ Done |
| 2 | Google SSO + Gmail Integration | ✅ Done |
| 3 | Notion Integration | ✅ Done |
| 4 | Retrieval / Search (Gmail + Notion) | ✅ Done |
| 5 | AI Triage & Draft Generation | ✅ Done |
| 6 | Workflow Intelligence Engine | ✅ Done |
| 7 | Template Management | ⏳ Planned |
| 8 | Human Review Dashboard | ✅ Done (edit / approve / reject / send) |
| 9 | Semantic Retrieval (embeddings) | ✅ Done (fastembed local; hybrid RRF) |
| 10 | Healzz Integration | ⏳ Planned |
| 11 | Internal Collaboration | ⏳ Planned |
| 12 | Analytics & Reporting | ⏳ Planned |
| 13 | Production Readiness | ⏳ Planned |

Phases 1–5 (the MVP) are complete — see [`DEMO_GUIDE.md`](./DEMO_GUIDE.md) to
demo it, and [`docs/architecture/`](./docs/architecture) (`phase-1.md` …
`phase-5.md`) for per-phase details.

---

## Phase 1 — Project Foundation

Phase 1 establishes the project architecture and development environment:

- Monorepo structure (`backend/`, `frontend/`, `shared/`, `docs/`)
- **Backend** — FastAPI (Python 3.13, runs on 3.11+) with clean layered
  architecture: `core`, `api`, `services`, `models`, `schemas`, `repositories`,
  `middleware`, `workers`, `tasks`, `utils`
- **Frontend** — Next.js (App Router) + TypeScript + TailwindCSS + shadcn/ui +
  TanStack Query
- **PostgreSQL** and **Redis** via Docker Compose
- Centralized configuration management (`pydantic-settings`)
- Structured, PII-masking logging (`structlog`)
- Health-check endpoints (backend + frontend)
- Authentication skeleton (JWT, password hashing, RBAC roles)
- Unit / integration / API test setup (`pytest`)
- CI pipeline skeleton (GitHub Actions)

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.13+, FastAPI, SQLAlchemy 2 (async), Alembic |
| Datastores | PostgreSQL 16 (+ pgvector later), Redis 7 |
| Async / jobs | Celery |
| Frontend | React, Next.js, TypeScript, TailwindCSS, shadcn/ui, TanStack Query |
| AI (later phases) | OpenAI, Claude, LangGraph, RAG, embeddings |
| Infra | Docker, Docker Compose, GitHub Actions, Nginx |
| Observability | structlog, OpenTelemetry, LangSmith, Sentry (optional) |

---

## Quick start (local, with Docker)

```bash
# 1. Clone and configure
cp .env.example .env        # then edit values as needed

# 2. Start the full stack (Postgres, Redis, backend, frontend)
docker compose up --build

# Backend:  http://localhost:8000      (docs at /docs)
# Frontend: http://localhost:3000
```

## Quick start (local, without Docker)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
cp ../.env.example ../.env
uvicorn app.main:app --reload    # http://localhost:8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev                      # http://localhost:3000
```

---

## Health checks

| Service | Endpoint |
|---------|----------|
| Backend liveness | `GET http://localhost:8000/api/v1/health` |
| Backend readiness (checks DB + Redis) | `GET http://localhost:8000/api/v1/health/ready` |
| Frontend | `GET http://localhost:3000/api/health` |

---

## Testing

```bash
# Backend (uses in-memory SQLite; no external services needed)
cd backend
pytest

# Frontend
cd frontend
npm run typecheck
npm run lint
```

See [`docs/`](./docs) for per-module manual testing instructions.

---

## Repository layout

```
firstmed-ai-email-assistant/
├── backend/     FastAPI application, tests, migrations
├── frontend/    Next.js application
├── shared/      Cross-cutting prompts, workflows, templates, schemas, constants
├── docs/        Architecture, API, workflows, deployment, security, user guide
├── scripts/     Helper scripts
├── docker/      Container assets
├── .github/     CI/CD workflows
└── docker-compose.yml
```

---

## Safety principles (enforced across all phases)

- Human-in-the-loop — **no email is ever sent automatically**
- Verified knowledge only — no answers from general knowledge, memory, or the internet
- Explainable decisions — every AI decision carries a reason + confidence
- Escalate uncertainty — clinical / legal / complex matters go to humans
- GDPR compliant — PII masking, audit logging, least-privilege access

## License

See [LICENSE](./LICENSE).
