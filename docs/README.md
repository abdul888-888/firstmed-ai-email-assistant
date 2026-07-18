# Documentation

| Folder | Contents |
|--------|----------|
| `architecture/` | System architecture, module boundaries, data model |
| `api/` | API reference (also auto-published at `/docs` via OpenAPI) |
| `workflows/` | FirstMed operational workflow documentation |
| `deployment/` | Environments, Docker, CI/CD, infra |
| `security/` | AuthN/Z, RBAC, GDPR, PII handling, secrets |
| `user-guide/` | Staff-facing guides for the review dashboard |

Phase notes:
- [`architecture/phase-1.md`](./architecture/phase-1.md) — project foundation (backend/frontend scaffold, infra).
- [`architecture/phase-2.md`](./architecture/phase-2.md) — Google SSO login + Gmail read access.
- [`architecture/phase-3.md`](./architecture/phase-3.md) — Notion knowledge-base read access.
- [`architecture/phase-4.md`](./architecture/phase-4.md) — unified retrieval/search over Gmail + Notion.
- [`architecture/phase-5.md`](./architecture/phase-5.md) — AI triage + draft generation (Claude, human-in-the-loop).
- [`architecture/phase-6.md`](./architecture/phase-6.md) — workflow intelligence engine + review-queue slice (persisted `DraftReview`, approve → Gmail draft).
- [`architecture/phase-9.md`](./architecture/phase-9.md) — semantic retrieval (fastembed embeddings, hybrid lexical + semantic RRF).
