# FirstMed AI Email Assistant — Executive Summary
**For Client Meeting: 2026-07-29 (1-Page Brief)**

---

## What Is It?

A **human-in-the-loop AI assistant** that reads administrative healthcare emails, intelligently categorizes them, and prepares draft responses. **Never sends email automatically.** Staff always reviews and approves before sending.

**Current Status:** Production-ready. Phases 1–9 complete. Active with real Gmail accounts and organizational knowledge bases.

---

## The Problem It Solves

| Before | After |
|--------|-------|
| Staff manually reads every admin email | AI reads emails, categorizes (appointment/billing/question/etc.) |
| Compose response from scratch | AI drafts response using organization's templates and knowledge base |
| No consistency across responses | Template-based + AI-grounded → consistent, faster |
| Clinical emails get drafted (dangerous) | Automatically escalates clinical/urgent matters to appropriate staff |
| Can't track what was sent or why | Every draft has audit trail: intent, reasoning, confidence score |

---

## Key Features

✅ **AI Triage** — understands email intent (appointment, billing, medical question, complaint)  
✅ **Smart Escalation** — automatically routes clinical/urgent/legal to staff (no draft)  
✅ **Template Library** — reusable responses for high-volume patterns (parking, clinic hours, refills)  
✅ **Knowledge Grounding** — searches organizational SOPs, pricing, insurance info (Notion databases)  
✅ **Human Review** — staff dashboard to edit, approve, or reject drafts before sending  
✅ **Specialist Collaboration** — clinical staff can review/guide escalated items  
✅ **Audit Trail** — every decision logged with reasoning and confidence  
✅ **PHI Encryption** — patient data encrypted at rest; compliant with HIPAA BAA  

---

## Technology (Quick Reference)

| Component | Technology |
|-----------|-----------|
| Backend | Python/FastAPI (async) |
| Frontend | React/Next.js |
| AI | Claude (Anthropic) |
| Database | PostgreSQL |
| Background Jobs | Celery + Redis |
| Knowledge Base | Notion (pricing, SOPs, insurance) |
| Auth | Google OAuth 2.0 (Gmail/Workspace SSO) |

---

## Workflow in 30 Seconds

1. **Staff clicks "Sync Inbox"** → Background system fetches new emails
2. **AI triages each email** → Classifies as appointment/billing/clinical/complaint/etc.
3. **Safety check runs** → Clinical/urgent items escalated (no draft); others continue
4. **System searches templates + knowledge base** → Finds relevant response patterns
5. **AI generates draft** → Personalized to email, grounded in org knowledge
6. **Staff reviews in dashboard** → Can edit, add notes, or reject
7. **Staff approves** → Gmail draft created (NOT sent automatically)
8. **Staff sends manually** → Full human control over all outbound email

---

## Current Strengths

| Strength | Impact |
|----------|--------|
| **No automatic sends** | Clinical oversight maintained; no liability |
| **Deterministic safety gates** | Clinical/legal/urgent routed consistently (not LLM-dependent) |
| **Template-first matching** | High-volume patterns (parking, clinic hours) answered instantly |
| **Incremental Gmail sync** | Efficient (only pulls new emails, not re-scanning inbox) |
| **Hybrid search (semantic + keyword)** | Finds relevant docs whether exact match or conceptual |
| **Role-based filtering** | Front office, nurses, specialists see only relevant drafts |
| **Async background processing** | Slow operations (Gmail, Claude) don't block web requests |

---

## Current Limitations

| Limitation | Workaround / Plan |
|-----------|-------------------|
| **No real-time team chat** | Specialist input routed through drafts (batch, not reactive). Phase 11 will add team messaging. |
| **Knowledge base not encrypted** | Notion SOPs stored plaintext in database (required for search). Can encrypt if retrieval architecture refactored. |
| **Requires active worker process** | Celery background tasks only run if worker process running. Production uses systemd/supervisor to daemonize. |
| **Template curation manual** | Library built by staff; requires ongoing maintenance as patterns emerge |

---

## Deployment & Operations

**Local Dev:** `docker compose up --build` (includes Postgres, Redis, backend, frontend, worker)

**Production Ready For:**
- Railway.app (+ Postgres, Redis)
- Heroku (+ Postgres add-on, Redis add-on)
- AWS ECS / Google Cloud Run (containerized)

**Health Checks:**
- Backend liveness: `GET /api/v1/health`
- Database readiness: `GET /api/v1/health/ready`
- Frontend: `GET /api/health`

---

## Security & Compliance

✅ **PHI at Rest:** Encrypted (subject, body, summary encrypted with Fernet key)  
✅ **API Auth:** JWT Bearer (Google OAuth SSO)  
✅ **Gmail Scopes:** Read-only + compose (never send)  
✅ **Audit Logging:** Every AI decision logged with reason, confidence, timestamp  
✅ **BAA Ready:** Config flag to attest Anthropic BAA/DPA signed (production startup blocks unattested usage)  
⏳ **GDPR Export:** Ready (user/review data exportable via admin API)  

---

## Success Metrics to Track

| Metric | Target | Why It Matters |
|--------|--------|----------------|
| **Processing Success Rate** | >95% | Indicates system reliability |
| **Draft Approval Rate** | >80% | Staff confidence in AI quality |
| **Escalation Accuracy** | <5% false negatives | Safety (clinical items not missed) |
| **Response Latency** | <5 sec avg | User experience |
| **Template Match Rate** | >40% | High-volume patterns well-covered |

---

## Roadmap (Next 6 Months)

| Phase | Timeline | Deliverable |
|-------|----------|-------------|
| **Phase 10** | Weeks 1–4 | Healzz appointment scheduling integration |
| **Phase 11** | Weeks 5–10 | Real-time team collaboration (internal messaging, @mentions) |
| **Phase 12** | Weeks 11–16 | Analytics dashboard (KPIs: volume, latency, accuracy) |
| **Phase 13** | Weeks 17–24 | Production hardening (rate limiting, tracing, resilience) |

---

## Next Steps for Client Meeting

1. **Confirm deployment target** (Railway, Heroku, on-prem, AWS, etc.)
2. **Identify top 5 email patterns** for template curation (e.g., parking, clinic hours, prescription refills)
3. **Discuss staff training plan** (dashboard orientation, approval workflows)
4. **Clarify compliance requirements** (BAA signature status, audit log retention, encryption scope)
5. **Plan analytics/reporting** (what KPIs matter most for leadership?)

---

## Questions the Client Might Ask

**Q: Will this replace staff?**  
A: No. This is a draft tool, not a replacement. Staff must review and approve every draft before sending. Automation is optional for high-confidence responses only.

**Q: What happens if the AI gets it wrong?**  
A: Drafts are reviewed before sending. Staff can edit, reject, or escalate. All decisions logged with reasoning for audit/improvement.

**Q: Can patients see the AI reasoning?**  
A: No. AI reasoning is internal only (for staff review). Patient-facing email is the final, human-approved draft.

**Q: What if we don't want to use Notion for the knowledge base?**  
A: Can integrate other sources: SharePoint, Confluence, custom APIs. Retrieval layer is pluggable.

**Q: What about HIPAA/GDPR compliance?**  
A: Encrypted at rest (PHI fields), audit logging, BAA-ready. See detailed docs in CLIENT_TECHNICAL_BRIEFING.md.

**Q: How much does it cost to run?**  
A: Anthropic Claude API (pay-per-token), basic cloud infra (Postgres, Redis, compute). Typical SMO clinic: ~$200–500/month API + infra, depending on volume.

**Q: Can it handle multiple clinic locations?**  
A: Yes. Each Gmail account/workspace is isolated. Multi-tenant support ready in architecture.

---

**For Detailed Information:** See `CLIENT_TECHNICAL_BRIEFING.md`

**Document Prepared:** 2026-07-28  
**Status:** Ready for presentation
