# Phase 5 — AI Triage & Draft Generation

**Goal:** Use Claude to (1) triage inbound patient emails (intent, urgency,
routing) and (2) generate a **draft** reply grounded in the Phase 4 retrieval
index. Strictly human-in-the-loop — the assistant prepares drafts; staff review,
edit, and send. Nothing is sent automatically.

## Provider & model
- **Anthropic Claude** via the official `anthropic` async SDK (new runtime dep,
  pinned `anthropic==0.116.0`).
- Default model **`claude-opus-4-8`** (`settings.ai_model`, override via `AI_MODEL`).
- Triage uses **structured outputs** (`output_config.format` + a JSON schema) so
  the result always maps onto `TriageResult`. Drafting uses free-form generation
  with **adaptive thinking** (`thinking: {type: "adaptive"}`).
- No sampling params or prefills (removed on Opus 4.8).

## What was built

### AI client wrapper (`app/ai/client.py`)
`AIClient` exposes two calls the services depend on: `text(...)` (generation) and
`structured(..., schema=...)` (schema-constrained JSON). The SDK is imported
lazily and the client is built only when an API key is present, so the app boots
without one. Errors are normalized to `AIError` / `AINotConfiguredError`.
Services take an injectable client, so tests use a fake and never hit the network.

### Triage (`app/services/triage_service.py`, `POST /api/v1/ai/triage`)
Classifies an email into:
- **intent** — appointment · prescription_refill · billing_insurance ·
  medical_question · test_results · referral · complaint · other
- **urgency** — low · normal · high · urgent
- **department** — front_office · nurse · specialist (routing)
- **summary**, **confidence** (0–1, clamped), **requires_human_review** (forced `true`)

### Draft generation (`app/services/draft_service.py`, `POST /api/v1/ai/draft`)
Retrieves relevant documents from the Phase 4 index (`SearchService`), feeds them
to Claude as grounding context, and returns `{ draft, model, citations[],
requires_human_review }`. The system prompt forbids fabricating specifics
(prices, dates, availability, medical advice) and defers clinical questions —
when context is missing, the draft asks for info or promises staff follow-up.
`use_context=false` skips retrieval.

### Gmail convenience variants (ties Phases 2 + 4 + 5)
- `POST /api/v1/ai/triage/gmail/{message_id}`
- `POST /api/v1/ai/draft/gmail/{message_id}`

Fetch the message via `GmailService` (Phase 2), then triage/draft it. `409` if
the user hasn't linked Google. (Phase 2 exposes headers + snippet, so the snippet
is used as the body proxy until full message-body parsing lands.)

`GET /api/v1/ai/status` reports `implemented`, `configured`, and the model.

### Error mapping
not configured → `503`; upstream/model error → `502`; Gmail not linked → `409`;
unauthenticated → `401`; empty body → `422`.

## Configuration (`.env` / `.env.example`)
```
ANTHROPIC_API_KEY=          # required to enable triage + drafting
AI_MODEL=claude-opus-4-8
AI_MAX_TOKENS=4096
```
`settings.ai_configured` gates the endpoints.

## How to verify
```bash
cd backend && pytest          # 96 tests (incl. AI client, triage, draft, AI API)
ruff check . && ruff format --check .
```
Every Claude call is mocked in tests (fake client / monkeypatched
`AIClient.text`/`structured`) — no API key or network required.

## Safety / guardrails
- **Human-in-the-loop:** every triage and draft result carries
  `requires_human_review: true`; no send path exists in this phase.
- Grounded generation: drafts are constrained to the retrieved context; the
  prompt explicitly bans inventing specifics and giving medical advice.
- PII masking in logs (Phase 1) still applies to all AI-path logging.

## Not in this phase (deliberately)
Auto-send, persisting drafts / a review-dashboard workflow, embeddings/semantic
retrieval (still lexical — Phase 4), the workflow engine, template selection,
streaming responses, and multi-message conversation threading.
