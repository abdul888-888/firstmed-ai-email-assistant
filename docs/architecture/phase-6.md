# Phase 6 — Workflow Intelligence Engine (+ Phase 8 thin slice)

**Goal:** Turn the linear "fetch → triage → draft → push" call from Phase 5 into
an **explicit, persisted, auditable pipeline**, and give staff a **minimal
review surface** to inspect the AI's classification, confidence, and reasoning
**before** anything reaches the mailbox.

This phase deliberately couples the Phase 6 **engine** (steps + persistence) with
a **thin slice of Phase 8** (review API + a minimal dashboard page), because the
engine's whole value is producing decisions a human can act on — building it
without a place to surface those decisions would be half a loop.

Non-negotiable safety principle carried from Phase 5: **no email is ever sent
automatically, and nothing is written to Gmail until a human approves it.**

---

## What changes vs. Phase 5

| | Phase 5 (today) | Phase 6 (this phase) |
|---|---|---|
| Orchestration | One function, `push_gmail_reply`, runs triage-less draft + push inline | Explicit ordered **steps** with a typed result per step |
| Safety gating | Implicit (system prompt defers clinical questions) | Explicit **safety-check step** → classification `ADMIN_DIRECT_REPLY` vs `NEEDS_PHYSICIAN_REVIEW` |
| Persistence | None — draft goes straight to Gmail Drafts | A **`DraftReview`** row per processed email (intent, urgency, classification, confidence, citations, draft text, status) |
| Human review | Only in Gmail, after the fact | In-app **pending queue** + **approve** action; draft reaches Gmail **only on approve** |
| Gmail write timing | At draft time | Deferred to **approve** time |

---

## Pipeline steps

The engine runs four ordered steps over one inbound email. Each step is a plain
async function that takes the accumulating `WorkflowContext` and returns an
updated one; the engine records the outcome of each step. (Kept **dependency-light
and in-process**, mirroring `SearchService`'s "semantic retrieval can plug in
behind the same interface" note — a LangGraph/graph runtime can later replace the
sequencer without changing the step contracts or the persisted schema.)

```
                 ┌──────────────────────────────────────────────┐
 Gmail message → │ 1. TRIAGE      classify intent/urgency/dept    │
                 │                + confidence (Claude, structured)│
                 ├──────────────────────────────────────────────┤
                 │ 2. SAFETY CHECK derive classification:         │
                 │    clinical / urgent / low-confidence          │
                 │    → NEEDS_PHYSICIAN_REVIEW                     │
                 │    else → ADMIN_DIRECT_REPLY                    │
                 ├──────────────────────────────────────────────┤
                 │ 3. RETRIEVE    RAG over SOP index (SearchService)│
                 │                → grounding context + citations  │
                 ├──────────────────────────────────────────────┤
                 │ 4. DRAFT       generate grounded reply (Claude);│
                 │    (or ESCALATE) escalated items still get a    │
                 │                 safe "a clinician will follow   │
                 │                 up" draft, flagged for review   │
                 └──────────────────────────────────────────────┘
                                     │
                    persist DraftReview(status = pending)
                                     │
             (NO Gmail write yet — waits for human approve)
```

### Step 1 — Triage
Reuses `TriageService.classify(subject, body)` (Phase 5): intent, urgency,
department, summary, confidence. No behavior change.

### Step 2 — Safety check → classification
A pure, rules-based function (no LLM, fully testable) maps the triage result to a
binary **classification**:

- **`NEEDS_PHYSICIAN_REVIEW`** when *any* of:
  - `intent ∈ { medical_question, test_results }` (clinical interpretation), or
  - `department == specialist`, or
  - `urgency ∈ { high, urgent }`, or
  - `confidence < CONFIDENCE_THRESHOLD` (default `0.70`).
- **`ADMIN_DIRECT_REPLY`** otherwise (routine admin: scheduling, billing,
  refills handled per SOP, general questions).

The step records a human-readable **reason** string (e.g. *"intent=medical_question
→ clinical interpretation requires a clinician"*) so the dashboard can explain the
decision. Classification never *blocks* drafting — it labels the draft so staff
know a clinician must review clinical replies before sending.

### Step 3 — Retrieve
`SearchService.search(subject + body)` → grounding context + `citations[]`
(document id / source / title / url). Unchanged from Phase 5.

### Step 4 — Draft (or escalate)
`DraftService.generate(...)` produces the grounded reply. Escalated
(`NEEDS_PHYSICIAN_REVIEW`) emails still receive a **safe** draft — the Phase 5
system prompt already refuses to interpret results/advise and defers to a nurse —
but the record is flagged so it is reviewed by a clinician, not just sent.

The engine then **persists a `DraftReview`** with `status = pending`. It does
**not** call Gmail. The draft only becomes a Gmail draft when a human approves
(see Review API).

---

## Data model — `DraftReview`

New table `draft_reviews` (`app/models/draft_review.py`), migration
`0004_draft_reviews` (chains from `0003_documents`). Follows existing conventions:
`Base` + `TimestampMixin`, `Uuid` PK `default=uuid.uuid4`, string-backed enums,
`JSON` for structured blobs.

| Column | Type | Notes |
|---|---|---|
| `id` | `Uuid` PK | `default=uuid.uuid4` |
| `user_id` | `Uuid` FK→users | The staff account whose mailbox this came from |
| `gmail_message_id` | `String(128)` | Source Gmail message id (indexed) |
| `gmail_thread_id` | `String(128)` | For threaded reply on approve |
| `message_id_header` | `Text` | RFC822 Message-ID (In-Reply-To / References on approve) |
| `sender` | `Text` | Original `From` (reply recipient) |
| `subject` | `Text` | Original subject |
| `intent` | `Enum(Intent)` | From triage (Phase 5 `schemas/ai.Intent`) |
| `urgency` | `Enum(Urgency)` | From triage |
| `department` | `Enum(Department)` | Routing |
| `classification` | `Enum(ReviewClassification)` | `ADMIN_DIRECT_REPLY` / `NEEDS_PHYSICIAN_REVIEW` |
| `confidence` | `Float` | 0–1, clamped |
| `summary` | `Text` | One-line triage summary |
| `reason` | `Text` | Why this classification (safety-check output) |
| `draft_body` | `Text` | Generated reply text (pre-send) |
| `citations` | `JSON` | List of `{document_id, source, title, url}` |
| `model` | `String(64)` | Model that produced the draft |
| `status` | `Enum(ReviewStatus)` | `pending` → `approved` (→ `rejected` later) |
| `gmail_draft_id` | `String(128)` \| null | Set once approved and pushed to Gmail |
| `reviewed_by` | `Uuid` \| null | Staff who approved |
| `reviewed_at` | `DateTime(tz)` \| null | When approved |
| `created_at` / `updated_at` | `DateTime(tz)` | `TimestampMixin` |

New enums (`app/schemas/review.py` or alongside the model):

```python
class ReviewClassification(str, Enum):
    ADMIN_DIRECT_REPLY = "ADMIN_DIRECT_REPLY"
    NEEDS_PHYSICIAN_REVIEW = "NEEDS_PHYSICIAN_REVIEW"

class ReviewStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"   # reserved for the full Phase 8; not wired in the thin slice
```

Index: `gmail_message_id` (dedupe / lookup). A partial/plain index on `status`
supports the pending-queue query.

---

## Services

- **`WorkflowService`** (`app/services/workflow_service.py`) — orchestrates the
  four steps and persists the `DraftReview`. Depends on `TriageService`,
  `SearchService`, `DraftService`, `GmailService`, and a
  `DraftReviewRepository`. Each Claude-backed dependency remains injectable so
  tests use fakes (no network), consistent with Phase 5.
- **Safety check** — a pure function `classify_review(triage) ->
  (ReviewClassification, reason)` in `app/services/safety.py`. No I/O, exhaustively
  unit-tested.
- **`DraftReviewRepository`** (`app/repositories/draft_review.py`) — `create`,
  `get`, `list_pending`, `mark_approved(...)`.

---

## API surface

### Phase 6 — engine trigger (`app/api/workflows/`)
Replaces the placeholder `workflows` module.

- `POST /api/v1/workflows/gmail/{message_id}` — run the full pipeline on a Gmail
  message and create a `pending` `DraftReview`. Returns the created review.
  Errors mirror Phase 5: `503` AI not configured, `409` Gmail not linked, `502`
  upstream AI/Gmail error, `401` unauthenticated.
- `GET /api/v1/workflows/status` — module status (implemented, phase 6).

### Phase 8 — review queue (`app/api/reviews/`)
Router mounted at `/api/v1/reviews`. Lifecycle:
`pending → (edit) → approve → approved → send → sent`, or `pending → rejected`.

- `GET /api/v1/reviews/pending` — pending reviews for the current user, newest first.
- `GET /api/v1/reviews?status=<status>` — list by status (`pending`/`approved`/
  `rejected`/`sent`); powers the dashboard's "ready to send" section.
- `GET /api/v1/reviews/{id}` — full record.
- `PATCH /api/v1/reviews/{id}` `{draft_body}` — inline edit (pending only).
- `POST /api/v1/reviews/{id}/approve` — the human-in-the-loop gate: pushes the
  stored `draft_body` to Gmail Drafts via `GmailService.create_draft(...)`
  (**threaded** — thread_id + In-Reply-To/References, `Re:` subject, addressed to
  `sender`), sets `status=approved`, records `gmail_draft_id`/`reviewed_by`/
  `reviewed_at`. **Creates a draft, never sends.**
- `POST /api/v1/reviews/{id}/reject` `{reason}` — pending → `rejected`, stores the
  reason in `review_note`. No Gmail interaction.
- `POST /api/v1/reviews/{id}/send` — approved → `sent`. The **only** outward-facing
  action: sends the approved Gmail draft via `drafts.send` (covered by the
  `gmail.compose` scope — no new scope), records `sent_at`/`sent_message_id`.

Status transitions are guarded (`409` on wrong state); every endpoint is
owner-scoped (`404` on another user's review). Columns `review_note`, `sent_at`,
`sent_message_id` added in migration `0005_review_actions`.

---

## Frontend — minimal review dashboard

A single page (`/reviews`) in the existing Next.js app:

- Fetches `GET /api/v1/reviews/pending` (bearer token in header).
- Renders a table/cards: sender, subject, **classification badge**
  (`ADMIN_DIRECT_REPLY` green / `NEEDS_PHYSICIAN_REVIEW` amber), **confidence**,
  **reason**, intent/urgency/department, **citations**, and the **draft preview**.
- **Approve** button per row → `POST /api/v1/reviews/{id}/approve` → row leaves
  the pending list; a toast confirms the draft is now in Gmail Drafts.

Deliberately minimal: read the queue, inspect the AI's reasoning/confidence,
approve. Editing inline, rejecting, filtering, and auth UX are full-Phase-8 work.

---

## Testing

- **Unit** — `classify_review` truth table (each escalation trigger + the
  happy admin path + the confidence boundary), `DraftReviewRepository`
  (create / list_pending / mark_approved), `WorkflowService` end-to-end with
  fakes (fake AI client, mock Gmail transport) asserting the persisted record and
  that **no Gmail write happens before approve**.
- **API** — `POST /workflows/gmail/{id}` creates a pending review (mocked AI +
  Gmail); `GET /reviews/pending` returns it; `POST /reviews/{id}/approve` pushes a
  threaded draft and flips status; guards: `401` unauth, `404` unknown id, `409`
  approving a non-pending review, `409` Gmail not linked.
- Every Claude/Gmail call is mocked — no network, no API key needed (Phase 5
  discipline).

---

## Safety / guardrails (unchanged intent, now explicit)
- **No auto-send.** Approve writes a *draft* to Gmail; sending is manual.
- **Nothing touches the mailbox pre-approval** — the pipeline only writes a DB
  row; Gmail is called solely in the approve path.
- **Explainability** — every record carries `classification`, `confidence`, and a
  `reason`; the dashboard shows them.
- **Escalation** — clinical / urgent / low-confidence emails are labeled
  `NEEDS_PHYSICIAN_REVIEW`; their drafts still defer to a clinician (Phase 5
  prompt) and are visibly flagged before a human sends.
- PII-masking logs (Phase 1) apply to the workflow path.

---

## Not in this phase (deliberately)
Review assignment/collaboration (Phase 11), template selection (Phase 7),
semantic retrieval (Phase 9), a graph-runtime (LangGraph) swap-in, analytics on
review throughput (Phase 12), and any batch/polling ingestion of the inbox (the
trigger is per-message for now).

> **Update:** inline draft editing, the reject workflow, and a human-triggered
> send endpoint — originally deferred — were completed as part of finishing
> Phase 8 (see the review-queue API above).
