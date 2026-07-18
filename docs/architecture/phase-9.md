# Phase 9 — Semantic Retrieval (embeddings)

**Goal:** Rank SOP/knowledge documents by *meaning*, not keyword overlap, so
triage and drafting ground on genuinely relevant sources. This directly fixes the
Phase 4 weakness we observed live — lexical scoring with no stopword filtering
makes almost every SOP score > 0, so every draft cites all ~5 documents
(including irrelevant ones like "Post-Op Fever" on a billing question).

Slots in **behind the existing `SearchService` interface** (as promised in the
Phase 4 docstring): callers (`DraftService`, `TriageService`, `/search`) are
unchanged; only ranking improves.

---

## The two constraints that shape this phase

1. **Anthropic has no embeddings API.** Our only AI dep today is `anthropic`.
   Embeddings need a *different* provider — a local model (no key, offline) or an
   external API (OpenAI / Voyage). **This is the one decision that needs your
   input** (see § Open decision).
2. **Demo runs on SQLite; prod on PostgreSQL.** SQLite has no native vector
   search. So the vector store is dual-path behind one interface:
   - **SQLite (demo):** store the embedding as a JSON array; rank by cosine
     similarity in Python (numpy). Fine for a small SOP corpus (dozens–hundreds).
   - **PostgreSQL (prod):** `pgvector` `Vector(dim)` column + `ORDER BY embedding
     <=> :q LIMIT k` (ANN index). Same interface, DB does the work.

---

## Architecture

```
DraftService / TriageService / /search
                 │  (unchanged)
                 ▼
          SearchService.search(query)
                 │
     ┌───────────┴────────────┐
     ▼                        ▼
 lexical score          semantic score
 (Phase 4, TF)          (embeddings)
     │                        │
     └──────► fuse (RRF) ◄─────┘         ← hybrid: robust to both
                 │                          vocab overlap and paraphrase
                 ▼
        ranked docs + citations
```

### Embedding abstraction (`app/ai/embeddings.py`)
A tiny `Embedder` protocol so the provider is swappable and tests use a fake:

```python
class Embedder(Protocol):
    dim: int
    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    async def embed_query(self, text: str) -> list[float]: ...
```

Concrete impls selected by `settings.embedding_provider`. Lazy-imported (like the
Anthropic client) so the app boots without the dep/key, degrading to lexical.

### Storage (`Document.embedding` + migration `0006`)
- Add `embedding` (JSON on SQLite / `Vector(dim)` on Postgres) and
  `embedding_model` (String — which model produced it, so we can detect staleness
  and re-embed on model change).
- **Backfill**: a reindex step embeds all existing documents; the seed script and
  `/search/reindex` populate embeddings for the 6 demo SOPs.

### Retrieval (`app/services/vector_store.py`)
One interface, two backends chosen by the active dialect:
- SQLite: fetch candidate rows, cosine in Python (numpy), top-k.
- Postgres: pgvector distance operator, top-k, with an IVFFlat/HNSW index.

### SearchService — hybrid fusion
Keep lexical scoring; add semantic scoring; combine with **Reciprocal Rank
Fusion** (rank-based, no score-scale tuning). If embeddings are unconfigured or a
doc has no vector, gracefully fall back to lexical-only (Phase 4 behavior) — the
app never hard-depends on embeddings.

### Ingestion
`DocumentRepository.upsert` embeds content on write (via the ingestion path);
re-embeds when `embedding_model` changes. Embedding a query happens per search
(cheap; cacheable later).

---

## Open decision — embedding provider

The abstraction supports all three; pick one for the default. Trade-offs:

| Option | Key needed | Dep weight | Offline | Notes |
|---|---|---|---|---|
| **Local (`fastembed`)** | none | moderate (ONNX runtime + ~90 MB model, first-run download) | ✅ | Best for a self-contained demo; no external cost/keys. Default dim 384 (bge-small). |
| **OpenAI** `text-embedding-3-small` | `OPENAI_API_KEY` | light (`openai`) | ❌ | Cheap, strong quality; adds an external provider + key. `.env.example` already stubs this. |
| **Voyage AI** `voyage-3` | `VOYAGE_API_KEY` | light (`voyageai`) | ❌ | Anthropic's recommended embeddings partner; strong retrieval quality. |

**Recommendation:** **Local `fastembed`** for the demo — it keeps the project
self-contained (no new keys, works offline, no per-call cost), which matches how
the rest of the stack demos. The provider abstraction means switching to OpenAI
or Voyage later is a config change, not a rewrite.

---

## Config (`settings` + `.env.example`)
```
EMBEDDING_PROVIDER=local        # local | openai | voyage
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5   # provider-specific
EMBEDDING_DIM=384
OPENAI_API_KEY=                 # only if provider=openai
VOYAGE_API_KEY=                 # only if provider=voyage
RETRIEVAL_MODE=hybrid           # hybrid | semantic | lexical
```
`settings.embedding_configured` gates semantic retrieval; unset ⇒ lexical fallback.

---

## Testing
- Unit: cosine ranking, RRF fusion, lexical fallback when no embeddings, staleness
  re-embed trigger. Embedder is faked (deterministic vectors) — no model/network.
- API: `/search` returns semantically-ranked results; a billing query no longer
  surfaces the post-op SOP; drafts cite fewer, more relevant sources.
- Keep every existing test green (lexical path preserved).

## Migration / demo DB
`0006_document_embeddings` adds the columns. Demo SQLite: `ALTER TABLE ADD
COLUMN` + a reindex to backfill the 6 SOPs (same pattern as `0005`).

## Outcome (implemented)
Default `local` fastembed (`bge-small-en-v1.5`) with `hybrid` RRF. Verified live
on the seeded SOPs: *"renew my heart medication"* → **Prescription Refill
Protocol**; *"redness around my surgical wound"* → **Post-Op Fever Guidelines** —
both of which pure keyword search ranked poorly or missed. Building this also
surfaced the Phase 4 lexical weakness for real (common words made every SOP
match), so **stopword filtering** was added to `tokenize` — that alone fixed the
over-broad citations in lexical *and* hybrid. Providers/mode are swappable via
`EMBEDDING_PROVIDER` / `RETRIEVAL_MODE`; unset/unavailable ⇒ lexical fallback.

## Not in this phase (deliberately)
Chunking long documents, re-ranking models, query expansion, embedding caching,
per-tenant indexes, `pgvector` ANN indexes (vectors are stored as JSON and scored
in Python — fine at current scale), and swapping to a dedicated vector DB
(Pinecone/Qdrant).
