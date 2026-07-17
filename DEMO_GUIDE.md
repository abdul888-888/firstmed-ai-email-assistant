# FirstMed AI Email Assistant — MVP Demo Guide

A **human-in-the-loop** assistant that triages patient emails and prepares Gmail
**draft** replies grounded in clinic knowledge. It **never sends email**, **never
gives medical advice**, and **flags every result for staff review**.

**MVP scope (Phases 1–5):** auth + Google SSO · Gmail read · Notion knowledge
base · unified search/retrieval · AI triage + draft generation.

---

## 1. Run it (no Docker)

**Backend** — http://localhost:8000 (interactive docs at **`/docs`**)
```bash
cd backend
python -m venv .venv && .venv\Scripts\activate      # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp ../.env.example ../.env                            # then edit (see §2)
uvicorn app.main:app --reload
```

**Frontend** — http://localhost:3000
```bash
cd frontend
npm install
npm run dev
```

> Prefer one command? `docker compose up --build` starts Postgres, Redis, backend, and frontend together.

---

## 2. Credentials — what unlocks what

| Feature | Needs | Without it |
|---|---|---|
| Auth (email/password), health | nothing | ✅ works |
| **AI triage + drafting** | `ANTHROPIC_API_KEY` in `.env` | endpoints return `503` |
| Google SSO login + Gmail read | `GOOGLE_CLIENT_ID`/`SECRET` | SSO returns `503`; Gmail `409` |
| Notion knowledge base | `NOTION_API_KEY` | Notion endpoints `503` |

**Minimal demo** (recommended for a first pass): set only `ANTHROPIC_API_KEY` —
you can show auth, triage, and drafting end-to-end. Add Google/Notion for the
full integration story.

---

## 3. Two-minute smoke test (curl)

```bash
BASE=http://localhost:8000/api/v1

# Register a staff user
curl -X POST $BASE/auth/register -H 'Content-Type: application/json' \
  -d '{"email":"demo@firstmed.com","password":"supersecret1","full_name":"Demo","role":"front_office"}'

# Log in → capture the bearer token (login is a form POST; username = email)
TOKEN=$(curl -s -X POST $BASE/auth/login \
  -d 'username=demo@firstmed.com&password=supersecret1' | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# Triage an email
curl -X POST $BASE/ai/triage -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"subject":"Refill","body":"Hi, can I get my blood pressure prescription refilled?"}'

# Draft a reply (grounded in the search index; citations returned)
curl -X POST $BASE/ai/draft -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"subject":"Refill","body":"Can I get my prescription refilled?","use_context":true}'
```

> **Easiest live demo:** open **http://localhost:8000/docs**, click **Authorize**,
> paste the token, and click **Try it out** on any endpoint.

---

## 4. Key backend endpoints (all under `/api/v1`)

Most data endpoints require `Authorization: Bearer <token>`.

**Auth & health**
- `GET  /health` · `GET /health/ready` — liveness / readiness (DB + Redis)
- `POST /auth/register` · `POST /auth/login` · `GET /auth/me`
- `GET  /auth/google/login` → consent URL · `GET /auth/google/callback` — Google SSO

**Gmail (Phase 2, read-only)**
- `GET /gmail/connection` — is Google linked?
- `GET /gmail/messages?max_results=&q=` — list shared-inbox messages
- `GET /gmail/messages/{id}` — one message (headers + snippet)

**Notion (Phase 3, read-only)**
- `GET /notion/connection` · `GET /notion/search?q=`
- `GET /notion/pages/{id}` · `GET /notion/pages/{id}/content` · `GET /notion/databases/{id}/query`

**Search / retrieval (Phase 4)**
- `POST /search/reindex` — pull Gmail + Notion content into the index
- `GET  /search?q=&source=&limit=` — ranked results
- `GET  /search/stats` — index size per source

**AI (Phase 5) — the headline**
- `POST /ai/triage` — classify: intent · urgency · department (routing) · confidence
- `POST /ai/draft` — generate a draft reply + **citations**; `requires_human_review: true`
- `POST /ai/triage/gmail/{id}` · `POST /ai/draft/gmail/{id}` — triage/draft a live Gmail message
- `GET  /ai/status` — shows whether AI is configured + which model

---

## 5. Suggested demo narrative

1. **Frontend (http://localhost:3000)** — landing page shows the live **backend
   status** indicator and **"Sign in with Google"**. Clicking it starts the OAuth
   flow; the `/auth/callback` page captures the token and returns to the app.
   *(SSO needs Google creds; if unset, demo login via `/docs` instead.)*
2. **Triage** — in `/docs`, run `POST /ai/triage` on a sample email. Show it
   returns a structured intent/urgency/department with a confidence score — the
   routing signal for the front office.
3. **Grounded drafting** — run `POST /ai/draft`. Show the draft reply **plus the
   `citations`** it was grounded on, and that it refuses to invent specifics or
   give medical advice.
4. **Retrieval** — `POST /search/reindex` then `GET /search?q=...` to show the
   unified Gmail + Notion knowledge index the drafts draw from.
5. **Full loop (with creds)** — `POST /ai/draft/gmail/{id}` to triage/draft a real
   message straight from the shared inbox.

---

## 6. Talking points (safety & quality)

- **Human-in-the-loop by design** — no send path exists; every triage/draft is
  flagged `requires_human_review: true`.
- **Grounded, not guessing** — drafts are constrained to retrieved clinic
  knowledge (Notion SOPs / prior email) and cite their sources.
- **No medical advice** — clinical questions are deferred to a nurse/clinician.
- **Privacy** — PII (emails, phone numbers) is masked in logs; OAuth tokens are
  encrypted at rest.
- **Quality bar** — 96 backend tests pass; frontend type-checks and builds; CI
  runs lint + tests on every push.

---

## 7. What's next (not in this MVP)

Workflow engine, approved-template management, a full review dashboard, semantic
(embedding) retrieval, Healzz integration, analytics, and production hardening —
Phases 6–13. See [`docs/architecture/`](./docs/architecture) for per-phase notes
(`phase-1.md` … `phase-5.md`).
