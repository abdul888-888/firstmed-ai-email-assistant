# PHI Encryption at Rest & Anthropic BAA/DPA Checklist

This covers two related but separate things: what patient data is encrypted
in the database, and what your organization needs to confirm with Anthropic
before real patient data goes through the API. **Read the "Not covered"
section — it matters as much as what's covered.**

## PHI encryption at rest

### What's encrypted

`DraftReview` columns, via `EncryptedText` (`app/models/types.py`, Fernet,
keyed by `PHI_ENCRYPTION_KEY`):

| Column | Why it's PHI |
|---|---|
| `subject` | The patient email's subject line |
| `draft_body` | The AI-drafted reply — built from the patient's email content |
| `summary` | A neutral paraphrase of the patient's email (still patient-identifying) |
| `specialist_input` | A clinician's free-text guidance on the patient's case |

Encryption is transparent at the ORM layer: every repository, service, and
API schema in the codebase reads/writes plain Python strings exactly as
before. Only the bytes physically stored in the database are ciphertext. The
column type in the database is unchanged (`TEXT`) — no schema migration was
needed for the type switch itself, only a one-time data backfill (see below).

### What's NOT encrypted (scope decision — revisit if needed)

- `DraftReview.sender` — the patient's email address, `reason` (safety-gate
  reasoning text), `review_note` (reject reason), and `ReviewNote.body` (staff
  collaboration notes). None of these were in the agreed scope for this pass.
- **`Document.content`** — the RAG/retrieval index, which includes **ingested
  Gmail thread text** used as grounding context for drafts. This is the
  biggest remaining gap: it's genuinely patient correspondence, stored in
  plaintext, and it's the one place where encrypting it isn't a drop-in change
  — the column is searched via SQL `ILIKE` for lexical retrieval
  (`app/repositories/document.py`), and encrypting it breaks that search
  outright unless the retrieval architecture changes (e.g. decrypt-then-search
  in application memory, or dropping Gmail-thread ingestion as a RAG source
  and keeping only Notion SOP content, which never contains patient data).
  This needs its own decision — flag if/when you want to tackle it.

### Key management

- `PHI_ENCRYPTION_KEY` is a **separate Fernet key** from `TOKEN_ENCRYPTION_KEY`
  (which protects OAuth tokens) — independent rotation, and a leak of one
  doesn't expose the other.
- Dev: leave blank — a key is deterministically derived from `SECRET_KEY`
  (salted differently from the token-key derivation, so the two never
  collide even when both fall back).
- **Production must set `PHI_ENCRYPTION_KEY` explicitly.** Enforced at
  startup by `Settings._validate_production_secrets` — the app refuses to
  start with `ENVIRONMENT=production` and no explicit key.
  ```bash
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
- **Rotation:** Fernet has no in-place re-key. To rotate, decrypt every
  affected row with the old key and re-encrypt with the new one (the same
  pattern as the backfill script below, generalized to old-key → new-key
  instead of plaintext → ciphertext). Not automated yet — build this if/when
  you actually need to rotate.
- **Losing the key is unrecoverable** — there is no way to decrypt existing
  rows without it. Back it up wherever you back up other production secrets
  (secrets manager, not a plaintext file in the repo).

### Backfill (run once, after deploying)

Any row written **before** this change is still plaintext. The ORM will now
try to Fernet-decrypt it on read and fail. Run the backfill after setting
`PHI_ENCRYPTION_KEY` and before relying on the app:

```bash
cd backend && .venv/Scripts/python.exe scripts/backfill_phi_encryption.py
```

Idempotent — each value is decrypt-tested first, so re-running is safe and
already-encrypted rows are left untouched. A fresh/empty database needs no
backfill at all.

## Anthropic BAA / DPA

**What I can and can't do here:** I can add a technical safeguard and tell you
exactly what to ask for. I cannot contact Anthropic, negotiate terms, or sign
anything — that's on your organization's legal/procurement contact.

### The technical safeguard

`ANTHROPIC_BAA_SIGNED` (default `false`) is a **self-attestation flag** — it
is not verified against anything external. In production, if
`ANTHROPIC_API_KEY` is set (i.e., the app is actually configured to send real
patient email content to Claude for triage/drafting) and
`ANTHROPIC_BAA_SIGNED` is still `false`, the app **refuses to start**
(`Settings._validate_production_secrets`). This exists to stop patient data
reaching Anthropic's API before someone has actually confirmed the
compliance paperwork is in place — it's a deployment-time reminder, not a
compliance guarantee.

Set `ANTHROPIC_BAA_SIGNED=true` only after you've completed the checklist
below, not before.

### What to actually request from Anthropic

1. **HIPAA Business Associate Agreement (BAA)** — required if FirstMed (or
   whoever operates this) is a HIPAA-covered entity or business associate
   processing PHI, which a clinic handling patient emails almost certainly
   is. Anthropic offers BAAs on qualifying commercial plans — contact
   Anthropic sales/enterprise support to request one; it is not available on
   a self-serve API key by default.
2. **Data Processing Addendum (DPA)** — required if any patient is in the EU/UK
   (GDPR) or similar jurisdictions. Ask specifically for Anthropic's standard
   DPA and confirm it covers the Claude API usage this app makes (triage +
   draft generation, i.e., patient email subject/body sent as prompt content).
3. **Data retention / training terms** — confirm in writing whether API
   inputs are retained, for how long, and whether they're used for model
   training. For a BAA-covered/enterprise arrangement this is typically
   zero-retention or a short operational window with no training use — get
   this explicitly, don't assume it from general marketing claims.
4. **Sub-processor list** — if your own compliance obligations require
   disclosing sub-processors (common under GDPR), confirm Anthropic is listed
   and review their own sub-processor chain (e.g., cloud infrastructure
   providers) if relevant to your risk assessment.
5. Once (1)–(4) are actually confirmed in writing, set
   `ANTHROPIC_BAA_SIGNED=true` in production and keep the signed
   agreement/correspondence on file — the flag itself proves nothing to an
   auditor; the paperwork does.

### If you already have a BAA/DPA in place

Tell me what's already been confirmed (retention terms, scope, effective
date) and I'll update this checklist to reflect the current state and check
whether anything in the code needs to change to match what was agreed (e.g.,
if the agreement requires a specific data-minimization step before sending
content to the API).
