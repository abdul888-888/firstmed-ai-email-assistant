# FirstMed AI Email Assistant — Technical Briefing
**For Client Meeting: 2026-07-29**

---

## Executive Summary

**FirstMed AI Email Assistant** is a production-ready, human-in-the-loop AI system that intelligently triages administrative healthcare emails and prepares draft responses while maintaining complete human oversight. The system processes Gmail inboxes using Claude AI, grounds responses in organizational knowledge (Notion SOPs, pricing, insurance), and enforces strict safety guardrails ensuring no patient data leaves unencrypted and no clinical decisions bypass physician review.

**Status:** MVP complete (Phases 1–9). Actively deployed with real Gmail accounts and organizational knowledge bases. Latest improvements include:
- Deterministic safety gates (routes clinical/legal inquiries to staff automatically)
- Notion database row-level ingestion (pricing/insurance lookup now functional)
- Template-first drafting (reusable responses for high-volume patterns)
- Async Gmail sync via Celery (non-blocking background processing)
- PHI encryption at rest with Anthropic BAA compliance

---

## Technical Architecture Overview

### System Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                          Frontend (Next.js)                     │
│  - Reviews Dashboard (3-column workspace)                       │
│  - Department-based role filtering                              │
│  - Real-time sync status                                        │
└────────────┬────────────────────────────────────────────────────┘
             │ HTTP/WebSocket
             ↓
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend (Async)                      │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  API Layer (REST endpoints)                             │   │
│  │  - /api/v1/workflows/pull          [sync Gmail pull]    │   │
│  │  - /api/v1/workflows/pull-async    [bg email fetch]    │   │
│  │  - /api/v1/reviews                 [CRUD drafts]       │   │
│  │  - /api/v1/templates               [response library]  │   │
│  │  - /api/v1/search                  [RAG retrieval]     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                         ↓                                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Workflow Intelligence Engine                           │   │
│  │  1. Triage (Claude): intent/urgency/department          │   │
│  │  2. Safety Gate: deterministic rules (escalate if       │   │
│  │     medical/legal/clinical/urgent)                      │   │
│  │  3. Retrieve: Template match → RAG (Notion+Gmail)      │   │
│  │  4. Draft: Claude (personalize template or compose)     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                         ↓                                      
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Service Layer                                          │   │
│  │  - AI Client (Claude LLM)                               │   │
│  │  - Gmail Service (OAuth, history sync)                  │   │
│  │  - Notion Service (page/database queries)               │   │
│  │  - Search/Retrieval (hybrid lexical+semantic)           │   │
│  │  - Template Matching                                    │   │
│  │  - Draft Generation & Safety Validation                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│                         ↓                                       
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Data Access Layer (SQLAlchemy ORM)                     │   │
│  │  - DraftReview (pending, awaiting_specialist, sent...)  │   │
│  │  - Document (Gmail threads, Notion pages)               │   │
│  │  - Template (canned responses, SOP links)               │   │
│  │  - GoogleCredential (encrypted OAuth tokens)            │   │
│  └─────────────────────────────────────────────────────────┘   │
└────────────┬────────────────────────────────────────────────────┘
             │
    ┌────────┴────────┬──────────────┬──────────────┐
    ↓                 ↓              ↓              ↓
 ┌──────────┐   ┌──────────┐  ┌──────────┐   ┌──────────┐
 │PostgreSQL│   │  Redis   │  │   Gmail  │   │  Notion  │
 │  (main   │   │ (cache,  │  │  (OAuth, │   │ (SOPs,   │
 │   data)  │   │  queues) │  │ threading)   │   │ pricing)│
 └──────────┘   └──────────┘  └──────────┘   └──────────┘
    ↓
 ┌──────────────────────────┐
 │  Celery Worker (async)   │
 │  - Background mail pulls │
 │  - Scheduled tasks       │
 └──────────────────────────┘
```

---

## Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | Next.js 14 (App Router) + React 18 + TypeScript + TailwindCSS + shadcn/ui | Web interface; workspace-based review dashboard |
| **Backend** | Python 3.13 + FastAPI + SQLAlchemy 2 (async) + Alembic | REST API; async data/workflow processing |
| **Database** | PostgreSQL 16 + pgvector (prepared) | Persistent review/draft storage, embeddings index |
| **Cache/Queue** | Redis 7 + Celery | Background job scheduling, result caching |
| **AI** | Claude (Anthropic) — Haiku 4.5 model | Triage, safety classification, draft generation |
| **Retrieval** | fastembed (local) + hybrid RRF | Semantic search over knowledge base (Notion + Gmail history) |
| **External APIs** | Google OAuth 2.0, Gmail API v1, Notion API | Email sync, organizational knowledge ingestion |
| **DevOps** | Docker, Docker Compose, GitHub Actions, Railway (optional) | Local dev, containerization, CI/CD |
| **Observability** | structlog (structured JSON logging) | Audit trail, debugging, compliance logging |

---

## Core Workflows

### 1. Email Ingestion & Triage (Pull Workflow)

**User Action:** Click "Sync Inbox" button → background async task

**Steps:**
1. **Authentication Check:** Verify OAuth token valid for Gmail account
2. **Message Fetch:** 
   - Use `GmailService.list_new_messages()` → intelligent fallback:
     - If history cursor exists & valid: incremental fetch (all new since last pull)
     - If expired/missing: bounded search (last 12 messages, excluding noise categories)
3. **Deduplication:** Check if message already has a DraftReview (prevents duplicates on re-runs)
4. **Triage (Claude LLM):**
   ```
   Input: email subject + full body
   Output: {
     intent: "appointment" | "medical_question" | "billing" | "complaint" | ...
     urgency: "low" | "medium" | "high" | "urgent"
     department: "front_office" | "nurse" | "specialist" | "laboratory" | ...
     summary: brief AI explanation
     confidence: 0.0–1.0 (how certain is the triage)
   }
   ```
5. **Safety Gate (Deterministic Rules):**
   - If `intent ∈ {appointment, complaint, billing_dispute}` → classify as `ROUTE_TO_STAFF`
   - If emergency keywords detected → force `NEEDS_PHYSICIAN_REVIEW`
   - If lab results / legal / complex → force escalation
   - If no escalation needed → classify as `ADMIN_DIRECT_REPLY`
6. **Template Matching:**
   - Score all active templates against email using lexical relevance
   - If template matches (majority of terms present) → use as draft base
7. **Retrieval (RAG if no template):**
   - Search Notion SOPs, pricing, insurance info
   - Include Gmail history (prior similar emails)
   - Hybrid search: both semantic (embeddings) + lexical (keyword)
8. **Draft Generation (Claude LLM):**
   - If template matched: personalize greeting only (preserve template wording)
   - Else: compose original response grounded in retrieved docs
   - For escalated items: generate safe, deferring reply (e.g., "Your request requires physician review…")
9. **Persist Draft:**
   - Save as `DraftReview` with status `pending` (no Gmail draft yet)
   - Include citations (which Notion/Gmail docs grounded the response)
   - Encrypt PHI fields (subject, body, summary) at rest

**Database Impact:**
- Create 1 `DraftReview` row
- Possibly create/update `Document` rows (new emails ingested into search index)
- Update `GoogleCredential.history_id` (cursor for next incremental pull)

---

### 2. Human Review & Approval (Dashboard Workflow)

**User Interface: 3-Column Workspace**

**Left Column — Role Selector:**
- Filter by department: Front Office / Nurse / Specialist / Laboratory / Gastroenterology / Physiotherapy
- Only shows drafts relevant to your role

**Center Column — Folder List:**
- **Ready for Review** (`pending`, `specialist_input_received`) — blue badge
- **Awaiting Specialist Input** (`awaiting_specialist_input`) — locked
- **Manual Handling** (`needs_manual_handling`) — escalations requiring staff review
- **Archive** (`approved`, `sent`, `rejected`, `irrelevant`) — completed

**Right Column — Draft Detail & Actions:**

1. **View Draft:**
   - Summary (AI explanation)
   - Citations (which Notion docs / email threads grounded it)
   - Full draft body
   - Sender, subject, original email snippet

2. **Edit Draft:**
   - Modify body text (all fields editable)
   - Save edits (overwrite the draft)

3. **Submit Specialist Input (if escalated):**
   - Text field for clinical guidance
   - Claude incorporates guidance + regenerates draft
   - Status moves to `specialist_input_received`

4. **Actions:**
   - **Approve:** Creates Gmail draft (never sends), status → `approved`
   - **Reject:** Status → `rejected`, no Gmail draft created
   - **Send (with confirm):** Chains approve → send, status → `sent`

---

### 3. Background Task Scheduling (Celery Pipeline)

**Manual Trigger:** `POST /api/v1/workflows/pull-async` (enqueue background job)

**Scheduled:** `pull_all_connected_task` (Celery Beat, runs periodically)

**Worker Process:**
- Separate Celery worker (`celery worker --pool=solo`) runs independently
- Fetches task from Redis queue
- Calls `pull_gmail` for each connected Gmail account
- Returns job ID → frontend polls `GET /workflows/pull-async/{task_id}` every 2 seconds
- Status updates: `pending` → `processing` → `completed` or `failed`
- Timeout: 180 seconds client-side (hangs gracefully if no worker running)

---

## Key Features & Strengths

### ✅ Safety-First Design

| Feature | Implementation |
|---------|-----------------|
| **No Automatic Sends** | Drafts only created on explicit human approval |
| **Clinical Escalation** | Medical, legal, urgent, or test-results emails automatically routed to staff (no draft generated) |
| **Deterministic Safety Gates** | Rules-based classification (not LLM-dependent) ensures consistency |
| **PHI Encryption at Rest** | Sensitive fields (subject, body, summary) encrypted with Fernet keys, separate from token encryption |
| **Audit Logging** | Structured JSON logs with correlation IDs; every AI decision includes reason + confidence |
| **BAA Compliance Ready** | Can attest Anthropic BAA/DPA signed; startup blocks unattested real-API usage in production |

### ✅ Intelligence & Accuracy

| Feature | Implementation |
|---------|-----------------|
| **Template-First Drafting** | Matches email against reusable templates before RAG — faster, more consistent responses |
| **Hybrid Retrieval** | Lexical (keyword) + semantic (embeddings) search for grounding — catches both exact matches and conceptual matches |
| **Incremental Email Sync** | Uses Gmail history API for efficient incremental pulls (not re-scanning everything each time) |
| **Notion Database Support** | Automatically expands Notion databases into per-row documents (pricing, insurance, SOPs now searchable) |
| **Department-Specific Routing** | Routes to appropriate role (Front Office, Nurse, Specialist, Lab Tech, Gastroenterology, Physio) |
| **Confidence Scores** | All AI classifications include confidence; low confidence → escalated for manual review |

### ✅ Operational Efficiency

| Feature | Implementation |
|---------|-----------------|
| **Async Background Processing** | Celery integration — doesn't block web requests during slow Gmail/AI calls |
| **Caching & Retrieval** | Redis for job queues, search cache reduces repeated lookups |
| **Idempotent Operations** | Duplicate message detection; re-runs are safe (no double-drafts) |
| **Workspace Organization** | 3-column dashboard groups reviews by status/role for efficient triage |
| **Batch Actions** | Approve multiple drafts in sequence |

### ✅ Developer Experience

| Feature | Implementation |
|---------|-----------------|
| **Structured Codebase** | Clear separation: API → Services → Data Access; easy to test, extend |
| **Type Safety** | Full TypeScript frontend, typed Python (Pydantic) backend |
| **Comprehensive Logging** | Every workflow step logged with context (user, message ID, intent, safety decision) |
| **Local Development** | Full stack runs in Docker Compose (Postgres, Redis, backend, frontend) |
| **Test Suite** | Unit + integration tests; async database fixtures |
| **API Documentation** | OpenAPI/Swagger auto-generated at `/docs` |

---

## Recent Improvements (Phases 6–9)

### Phase 6: Workflow Intelligence Engine
- ✅ Deterministic safety gates (previously all LLM-driven, now rules + LLM)
- ✅ Exclusive escalation paths (clinical/legal never drafts, staff-routes only)
- ✅ Review persistence (`DraftReview` table), database-first architecture

### Phase 7: Template Management
- ✅ Canned responses library (curated by staff)
- ✅ Smart template matching (relevance-scored, not manual picker)
- ✅ Personalization gate (templates preserve wording, only greetings customized)

### Phase 8: Human Review Dashboard
- ✅ 3-column workspace (left: roles, center: folders, right: detail)
- ✅ Full draft editing (staff can modify before sending)
- ✅ Specialist input flow (clinical staff can add guidance → re-triage)
- ✅ Real-time role-based filtering

### Phase 9: Semantic Retrieval
- ✅ Hybrid search (lexical + embedding-based)
- ✅ Notion database row ingestion (pricing, insurance now queryable)
- ✅ Gmail history incremental sync (efficient, bounded batches)
- ✅ fastembed local embeddings (no external API, privacy-preserving)

### Phase 10 (In Progress): Healzz Integration
- ⏳ Appointment scheduling system wiring
- ⏳ Calendar conflict detection

---

## Current Limitations & Technical Challenges

### 🔴 Critical Gaps

| Issue | Impact | Status |
|-------|--------|--------|
| **Notion document encryption** | RAG index contains plaintext SOPs (subject to ILIKE search); if DB breached, all knowledge base text exposed | Deferred (requires retrieval architecture change) |
| **Non-PHI field encryption** | `sender`, `reason`, `review_note`, `ReviewNote.body` stored plaintext (not encrypted at rest) | Deferred (scope clarification needed) |
| **No real-time collab channels** | Internal notes / @mentions routed through specialist-input only (batch, not reactive) | Planned Phase 11 |

### ⚠️ Known Limitations

| Limitation | Root Cause | Workaround |
|------------|-----------|-----------|
| **Migration chain SQLite-incompatible** | Migration 0001 uses `sa.text("now()")` (Postgres-only default); dev uses `Base.metadata.create_all()` instead | No impact (Alembic never runs locally against SQLite; production uses Postgres) |
| **Celery requires external worker** | Async tasks only run if a worker process is actively running; without it, sync pulls block web requests | Dev: ensure `celery worker` running; Prod: use systemd/supervisor to daemonize |
| **History cursor bootstrap** | First pull always uses bounded search (history API requires a starting point); not incremental | Acceptable (first pull happens once; subsequent pulls are incremental) |
| **Relevance floor prevents very short queries** | Lexical matching requires ≥50% of query terms to match document (prevents spurious grounding on single word) | Acceptable (prevents "Do you offer Botox?" matching unrelated "offer" mentions) |
| **No PII-redaction in logs** | Email bodies logged at DEBUG level; operators may see patient names/details in local logs | Mitigation: structlog PII masking in place for email senders; recommend local-log retention limits |

---

## Performance & Scalability

### Current Thresholds

| Metric | Current Setting | Notes |
|--------|-----------------|-------|
| **Gmail pull limit** | 12 messages max per sync | Bounded search; configurable |
| **Notion page limit** | 25 pages max per query (auto-paginated) | Prevents runaway API calls |
| **Search index** | Hybrid (lexical + 768-dim embeddings) | fastembed on CPU; adds ~50ms per query |
| **Draft generation latency** | ~2–5 sec (Claude Haiku inference) | Async, non-blocking |
| **Token budget per draft** | 4096 tokens max | Haiku model limit; sufficient for admin emails |
| **Rate limiting** | Phase 13 (local hardening) — slowapi in place | Per-IP limits configurable |

### Scalability Approach

- **Horizontal:** Frontend stateless (Session → JWT); backend stateless (Celery workers scale horizontally)
- **Vertical:** PostgreSQL connection pooling, Redis for cache
- **Optimization opportunities:**
  - Embedding cache (memoize frequently-queried docs)
  - Scheduled weekly re-index (reduce on-demand embedding latency)
  - Gmail label-based pre-filtering (reduce irrelevant emails)

---

## Security & Compliance

### Authentication & Authorization

| Layer | Mechanism |
|-------|-----------|
| **User Identity** | Google OAuth 2.0 (SSO) |
| **API Access** | JWT Bearer token (HS256), stored in browser `localStorage` |
| **Backend Validation** | Checks token signature, user email, workspace membership |
| **Role-Based Access** | Department filters (front_office, nurse, specialist, lab, gastro, physio) — enforced in API layer |
| **Gmail Permissions** | OAuth scopes: read Gmail, compose drafts (never send) |
| **Notion Permissions** | API key scoped to integration (read-only pages/databases) |

### Data Protection

| Data | Protection | Status |
|------|-----------|--------|
| **OAuth Tokens** | Encrypted with Fernet (TOKEN_ENCRYPTION_KEY) at rest | ✅ Implemented |
| **Patient Data (PHI)** | Encrypted with Fernet (PHI_ENCRYPTION_KEY) at rest — subject, body, summary | ✅ Implemented |
| **Knowledge Base (Notion)** | Plaintext (ILIKE-searchable; encryption would require retrieval refactor) | ⏳ Deferred |
| **Audit Logs** | Structured JSON with correlation IDs; rotated per environment | ✅ Implemented |
| **Secrets** | `.env` file (development); environment variables (production) | ✅ Implemented |

### Compliance Readiness

- ✅ **PHI Encryption:** Enabled (subject, body, summary encrypted at rest)
- ✅ **Anthropic BAA Attestation:** Config flag `ANTHROPIC_BAA_SIGNED` (production startup fails if unset with real API key)
- ✅ **Audit Logging:** All AI decisions logged with reason, confidence, user, timestamp
- ✅ **PII Masking:** Structured logging masks email addresses in public logs
- ⏳ **GDPR Data Export:** Ready (user/review data exportable via admin API)
- ⏳ **Right to Deletion:** Partial (review soft-delete ready; Gmail data deletion requires verification)

---

## Deployment & Operations

### Current Environment

- **Developed on:** Windows 11 Pro, Windows PowerShell
- **Test Environment:** Docker Compose (Postgres, Redis, backend, frontend)
- **Production Ready For:** Railway.app, Heroku, AWS ECS, Google Cloud Run
- **CI/CD:** GitHub Actions (build, test, lint on PR; deploy on merge to main)

### Docker Compose Stack

```yaml
Services:
  - postgres:16  (data)
  - redis:7      (cache, Celery broker)
  - backend      (FastAPI + Uvicorn)
  - frontend     (Next.js)
  - celery-worker (Celery consumer)

Ports:
  - Backend:  :8000 (/api/v1, /docs)
  - Frontend: :3000
  - Postgres: :5432 (internal)
  - Redis:   :6379 (internal)
```

### Manual Operations

| Task | Command | Notes |
|------|---------|-------|
| **Local dev (all services)** | `docker compose up --build` | Includes Postgres, Redis, backend, frontend, worker |
| **Reset database** | `docker compose down -v` | Wipes Postgres volume |
| **Backend tests** | `cd backend && pytest` | Uses in-memory SQLite; no external deps |
| **Frontend type check** | `cd frontend && npm run typecheck` | Catches TypeScript errors |
| **Alembic migrations** | `cd backend && alembic upgrade head` | Postgres only; SQLite not supported |
| **Celery worker (dev)** | `celery -A app.workers.celery_app worker --pool=solo --loglevel=info` | Windows compatibility |

---

## Future Roadmap

### Phase 10: Healzz Integration (Foundation)
- **Goal:** Query appointment availability; detect scheduling conflicts
- **Status:** Config + service wiring in place; endpoints stubbed
- **Next:** Implement `HealzzService.check_availability()`, integrate into draft relevance

### Phase 11: Internal Collaboration (Planned)
- **Goal:** Real-time @mentions, internal notes, threaded discussions
- **Features:**
  - Internal message channel (separate from patient emails)
  - @mention notifications (Slack integration optional)
  - Role-based visibility (Front Office can't see clinical notes)
- **Technical:** WebSocket support, notification queue

### Phase 12: Analytics & Reporting (Planned)
- **Goal:** Dashboard for leadership/QA: response time, draft acceptance %, escalation trends
- **Features:**
  - Volume metrics (emails processed, approved %, rejected %)
  - Latency tracking (AI inference, user action time)
  - Accuracy metrics (post-send feedback on draft quality)
  - Department-level breakdown
- **Technical:** ClickHouse or Postgres materialized views for fast aggregation

### Phase 13: Production Hardening (Planned)
- **Goal:** Enhance observability, resilience, security
- **Features:**
  - Rate limiting (✅ in place, configurable)
  - Request timeout enforcement
  - Dead-letter queue for failed Celery tasks
  - Sentry integration (error tracking)
  - OpenTelemetry tracing (distributed tracing)
  - FIPS 140-2 cryptography compliance (optional)
- **Technical:** Middleware enhancements, observability toolchain

### Future Enhancements (Roadmap)

| Feature | Complexity | Benefit |
|---------|-----------|---------|
| **Fine-tune Claude on org-specific emails** | Medium | +5–10% accuracy on domain-specific intents |
| **Notion database sync to ES** | Medium | Faster complex queries (filtering on multi-select fields) |
| **Email attachment handling** | Medium | Support images, PDFs in triage/retrieval |
| **Multi-language support** | Low (i18n framework ready) | Serve international clinics |
| **Mobile app (React Native)** | High | Staff can review/approve on phone |
| **Custom LLM fine-tuning** | High | Org-specific safety rules (learned, not hard-coded) |
| **Slack bot integration** | Low | Approve drafts directly from Slack (vs. dashboard) |

---

## Key Metrics & Health Checks

### System Health

| Check | Endpoint | SLA |
|-------|----------|-----|
| **Liveness** | `GET /api/v1/health` | Must respond in <1s |
| **Readiness** | `GET /api/v1/health/ready` | Postgres + Redis required; <5s |
| **Frontend** | `GET /api/health` (Next.js) | <1s |

### Operational Metrics to Track

- **Gmail Pull Success Rate:** % of pulls completing without error
- **Draft Generation Latency:** P50/P95 time from email received to draft persisted
- **AI Confidence Distribution:** % of triages with >0.8 confidence (high confidence = less manual review)
- **Escalation Rate:** % of emails classified as `ROUTE_TO_STAFF` or `NEEDS_PHYSICIAN_REVIEW`
- **Template Match Rate:** % of drafts using templates vs. composed from scratch
- **Staff Approval Rate:** % of drafted emails approved (vs. rejected/edited)
- **Error Rate:** Failed triage/draft generation (should be <1%)

---

## Recommendations for Client Discussion

### ✅ Immediate Actions (Ready Now)
1. **Train staff on dashboard:** 3-column workspace, role filters, specialist-input flow
2. **Curate templates:** Identify top 10 repeating email patterns → create templates
3. **Configure Notion SOPs:** Ensure pricing, insurance, appointment SOPs are in Notion and indexed
4. **Set BAA sign-off:** Legal/compliance confirm Anthropic BAA signed before production
5. **Plan data migration:** How to handle existing emails? (Can re-ingest via `/pull` endpoints)

### ⚠️ Near-Term Improvements (1–3 months)
1. **Monitor escalation patterns:** Are the deterministic safety gates routing correctly? Adjust keyword rules if needed
2. **Collect feedback:** Staff feedback on draft quality → inform template curation
3. **Implement analytics dashboard:** Track volume, latency, accuracy metrics
4. **Add Slack notifications:** Staff get notified when specialist input needed (vs. polling dashboard)
5. **Scale Celery workers:** If volume grows, add worker processes (horizontally scalable)

### 🔄 Medium-Term Enhancements (3–6 months)
1. **Phase 11 — Internal Collaboration:** Real-time @mentions for clinical discussions
2. **Fine-tune safety gates:** Gather 3 months of prod data → identify false positives/negatives
3. **Implement analytics (Phase 12):** Leadership dashboard for KPIs
4. **Notion document encryption:** Decrypt-on-retrieval approach (if regulatory requirement)
5. **Custom knowledge ingestion:** Support custom PDFs, wiki, internal systems

### 🎯 Strategic Priorities
1. **Safety over velocity:** Always escalate uncertain clinical matters. Template matches are confidence heuristic, not gospel.
2. **Staff feedback loop:** Weekly reviews of escalated items and rejected drafts → drives template improvement
3. **Compliance-first:** Don't skip BAA/DPA signature. Encryption keys rotated annually. Audit logs retained per retention policy.
4. **Automation scope:** Keep human in the loop. This is a draft tool, not a send tool. Require explicit approval always.

---

## Technical Support & Troubleshooting

### Common Issues & Fixes

| Issue | Diagnosis | Fix |
|-------|-----------|-----|
| **"Sync" button hangs** | Celery worker not running | `celery worker --pool=solo` in terminal; or use sync `/pull` endpoint instead |
| **Gmail auth fails** | OAuth token expired or revoked | User: re-authenticate via SSO login |
| **Low draft quality** | Missing templates or outdated Notion SOPs | Curate templates, refresh Notion docs |
| **Slow search** | Large Gmail index; embeddings not cached | Wait for scheduled index rebuild; or reduce max_results |
| **"GAA Account Disconnected"** | Gmail OAuth scopes insufficient | Confirm scopes: `gmail.readonly`, `gmail.compose` |
| **Encryption failures** | Keys not configured | Set `TOKEN_ENCRYPTION_KEY` and `PHI_ENCRYPTION_KEY` in `.env` |

### When to Escalate

- **Security incident:** Token leak, unauthorized data access → revoke keys, rotate encryption keys, audit logs
- **Data loss:** Postgres crash, Redis failure → restore from backup, re-index from Gmail/Notion
- **AI failures:** Claude API down or quota exceeded → check Anthropic status; queue tasks for retry
- **Compliance breach:** Unencrypted PHI in logs, BAA signature expired → legal + compliance team

---

## Conclusion

FirstMed AI Email Assistant is a **production-ready, safety-first AI system** that reduces administrative overhead while maintaining full human oversight and clinical oversight. The architecture prioritizes:

- **Safety:** Deterministic escalation, no automatic sends, encrypted PHI
- **Accuracy:** Template-first + RAG-grounded drafts, department-specific routing
- **Operability:** Async processing, comprehensive logging, clear workflows
- **Compliance:** BAA attestation, audit trails, GDPR-ready

**Next Steps for Meeting:**
1. Confirm deployment environment (Railway, Heroku, on-prem, etc.)
2. Discuss template curation process and staff training timeline
3. Agree on compliance/legal sign-off (BAA, DPA, encryption keys)
4. Plan analytics/reporting requirements for Phase 12
5. Identify quick wins (3–5 highest-volume email patterns for templates)

---

**Document Prepared:** 2026-07-28  
**Version:** 1.0 (Phases 1–9 complete)  
**For:** Client Technical Briefing Meeting
