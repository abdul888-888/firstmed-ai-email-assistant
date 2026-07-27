"""AI draft generation with retrieval context (Phase 5).

Retrieves relevant documents from the Phase 4 index (Notion SOPs / prior email),
feeds them to Claude as grounding context, and returns a DRAFT reply plus the
citations it was grounded on. Human-in-the-loop: the draft is never sent.
"""

from __future__ import annotations

import math

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import AIClient, get_ai_client
from app.ai.prompts import DRAFT_SYSTEM, TEMPLATE_SYSTEM, build_draft_user, build_template_user
from app.core.config import settings
from app.core.logging import get_logger
from app.models.document import DocumentSource
from app.models.template import Template
from app.models.user import User
from app.repositories.template import TemplateRepository
from app.services.gmail_service import GmailService
from app.services.search_service import ScoredDocument, SearchService, tokenize

logger = get_logger(__name__)

# Per-document content cap when assembling the context block, to bound prompt size.
_CONTEXT_CHARS_PER_DOC = 2000

# Conversational filler that survives search_service's general stopword list
# (which strips grammatical connectives like "the"/"a"/"is", not pleasantries)
# but carries no topical signal in a patient email — "Hi, I wanted to ask...
# Thanks!" inflates the term count with words that will never match a terse
# KB row, diluting the ratio below the relevance floor even when the actual
# topic (e.g. "MRI", "scan") is a clean match. Scoped to draft_service only —
# NOT merged into search_service's shared stopword list, since that would also
# change ranking/recall for the staff-facing document search feature, a much
# broader blast radius than the grounding-gate tuning this addresses.
_CONVERSATIONAL_FILLER = frozenset(
    {
        "hi",
        "hello",
        "hey",
        "dear",
        "thanks",
        "thank",
        "please",
        "regards",
        "sincerely",
        "wanted",
        "asking",
        "wondering",
        "kindly",
        "best",
        "ask",
    }
)

# Domain-significant vocabulary carries extra weight WHEREVER it matches
# (title or body) — these terms are the actual TOPIC of a patient's question
# (a specific service, procedure, or billing concept), unlike generic words
# ("clinic", "visit", "question") that appear in nearly every patient email
# regardless of subject.
#
# An earlier version of this weighting gave a flat bonus to any term matching
# a document/template TITLE (titles being short, curated labels). That was
# wrong: a live smoke test caught it giving a false-positive match — a chatty
# MRI-pricing email ("...at your clinic...") spuriously matched a "Clinic
# Hours" template purely because "clinic" is in that title, even though the
# email had nothing to do with hours. Weighting by domain significance instead
# of by structural position (title vs. body) avoids that: "clinic" isn't
# significant vocabulary anywhere it appears, so it can't single-handedly
# clear the floor, while "mri"/"scan" are significant and correctly do.
_SIGNIFICANT_TERMS = frozenset(
    {
        "mri", "scan", "xray", "x-ray", "ultrasound", "ct",
        "colonoscopy", "gastroscopy", "endoscopy",
        "physio", "physiotherapy", "physiotherapist",
        "price", "prices", "pricing", "cost", "costs", "fee", "fees",
        "insurance", "billing", "copay", "coinsurance",
        "refill", "prescription", "medication", "medications",
        "referral", "results", "biopsy",
        "vaccination", "vaccine", "consultation", "checkup", "bloodwork",
        "lab", "labs",
    }
)  # fmt: skip
_SIGNIFICANT_WEIGHT = 3


def _significant_terms(body: str) -> list[str]:
    """Query terms for the relevance floor / template matching: tokenized and
    stripped of conversational filler that would otherwise dilute the match
    ratio for naturally-phrased, chatty patient emails (see
    ``_CONVERSATIONAL_FILLER``)."""
    return [t for t in tokenize(body) if t not in _CONVERSATIONAL_FILLER]


def _weighted_match_score(terms: list[str], *, title: str, body: str) -> float:
    """Sum of per-term match weight: ``_SIGNIFICANT_WEIGHT`` for domain
    vocabulary (see ``_SIGNIFICANT_TERMS``) matched anywhere in title or
    body, else 1 for any other match, else 0."""
    text = f"{title}\n{body}".lower()
    score = 0.0
    for t in terms:
        if t not in text:
            continue
        score += _SIGNIFICANT_WEIGHT if t in _SIGNIFICANT_TERMS else 1.0
    return score


# Relevance floor for grounding: a hit only counts as "actually about this
# question" if its weighted match score clears a strict majority of the
# query's distinct terms. Retrieval matches on ANY single term (e.g. a
# stopword-surviving word like "offer"), so a one-term coincidence — e.g. "Do
# you offer Botox?" matching an appointment SOP that happens to say "offer the
# earliest slot" (a generic, non-significant word, weight 1) — must not count
# as grounding. A flat minimum (e.g. "always need >=2") is too strict for
# short queries: a 2-term question like "refill my prescription" can be fully
# answered by an SOP that only literally repeats "refill", not "prescription".
# Requiring a majority (ceil(n/2)) scales the floor with query length instead,
# and significant-term weighting means a clean topical match (e.g. "MRI"/
# "scan" both matching) clears that floor even when several other, less
# meaningful query terms don't match at all.
#
# The weighting alone reopened a version of the same bug it was built to
# close, caught via live re-verification: "Do you accept Aetna insurance?"
# matched a "Billing office hours" template purely because "insurance" (one
# term, weight 3) alone cleared a 2-of-3 threshold — a single incidental
# keyword hit, same failure shape as the Botox case, just laundered through a
# higher weight instead of a generic word. Weighting must never be the SOLE
# reason a lone matched term clears the floor: if the *unweighted* match count
# already meets the threshold on its own (e.g. "refill my prescription", a
# 2-term query where matching "prescription" alone always sufficed — ceil(2/2)
# == 1 — with or without weighting), that's a genuine, pre-existing pass. But
# if only the significance weight pushes a single match over the line (Aetna:
# 1 raw match, ceil(3/2) == 2, only clears it as 1*3), it needs a second
# distinct matched term as corroboration before that weight counts — exactly
# what rescues the MRI case (two matched terms, "mri" + "scan").
def _is_relevant(terms: list[str], *, title: str, body: str) -> bool:
    if not terms:
        return True
    text = f"{title}\n{body}".lower()
    matched = [t for t in terms if t in text]
    if not matched:
        return False
    threshold = math.ceil(len(terms) / 2)
    if len(matched) >= threshold:
        return True  # unweighted count alone already clears it
    if len(matched) < 2:
        return False  # a lone match needs corroboration to lean on its weight
    return _weighted_match_score(terms, title=title, body=body) >= threshold


class DraftService:
    def __init__(self, session: AsyncSession, ai: AIClient | None = None) -> None:
        self.session = session
        self.ai = ai or get_ai_client()
        self.search = SearchService(session)
        self.templates = TemplateRepository(session)

    async def _retrieve(self, subject: str, body: str, max_context: int):
        """Retrieve grounding docs, prioritising the Notion knowledge base.

        The Notion KB is the clinic's source of truth; noisier prior-email
        matches must not crowd it out of the (small) context window. We fetch the
        best KB-scoped hits first, then fill any remaining slots with the general
        (all-source) hits, de-duplicated — so an authoritative pricing/insurance
        row is always in context when it matches, while prior correspondence
        still contributes when the KB is silent.

        Hits are also filtered by a minimum term-overlap floor (see
        ``_is_relevant``): the underlying lexical search matches on ANY single
        query term, so a coincidental one-word overlap (e.g. an unrelated SOP
        that happens to contain "offer") would otherwise count as a citation and
        defeat the ungrounded-abstain guard. The relevance floor is scored
        against ``body`` terms only (not ``subject``): subject lines are often
        generic boilerplate ("Question", "Refill request") that would otherwise
        inflate the term count and push a terse, correctly-matching KB row (e.g.
        a pricing table row) below the majority threshold. The full
        subject+body still feeds the search query itself, so subject text still
        helps ranking/recall — only the relevance *gate* is body-scoped.

        A significant-term direct lookup backstops the ranked search: a chatty,
        filler-heavy patient email can share more raw lexical/semantic overlap
        with unrelated documents (e.g. "clinic"/"hours" phrasing) than with a
        terse, exact topical match (e.g. a "MRI Scan" pricing row), pushing the
        real match below the top-``max_context`` window before the relevance
        floor even gets to evaluate it — a real gap caught via live smoke
        testing. Directly fetching documents that literally contain a
        significant query term (e.g. "mri") guarantees a clean topical match
        is never lost to ranking alone.
        """
        query = f"{subject}\n{body}"
        terms = _significant_terms(body)
        kb_hits = await self.search.search(
            query, limit=max_context, sources=[DocumentSource.notion.value]
        )
        general_hits = await self.search.search(query, limit=max_context)

        candidates = list(kb_hits) + list(general_hits)
        significant = [t for t in terms if t in _SIGNIFICANT_TERMS]
        if significant:
            direct = await self.search.repo.fetch_candidates(
                significant, sources=[DocumentSource.notion.value], limit=max_context
            )
            candidates.extend(ScoredDocument(document=doc, score=0.0) for doc in direct)

        merged: dict = {}
        for hit in candidates:
            doc = hit.document
            if not _is_relevant(terms, title=doc.title, body=doc.content):
                continue
            merged.setdefault(doc.id, hit)
        return list(merged.values())[:max_context]

    async def _match_template(self, body: str) -> Template | None:
        """Return the best-matching active canned-response template, if any.

        Template-first (requirement D): an approved, staff-curated template is
        preferred over free LLM composition whenever the patient's email
        matches one closely enough. Uses the same term-overlap relevance floor
        as document retrieval (``_is_relevant``), scored against the template's
        title + body; the single highest-scoring template above the floor wins.
        """
        terms = _significant_terms(body)
        if not terms:
            return None
        candidates = await self.templates.list(active_only=True)
        best: Template | None = None
        best_score = 0.0
        for tpl in candidates:
            if not _is_relevant(terms, title=tpl.title, body=tpl.body):
                continue
            score = _weighted_match_score(terms, title=tpl.title, body=tpl.body)
            if score > best_score:
                best, best_score = tpl, score
        return best

    async def generate(
        self,
        subject: str,
        body: str,
        *,
        use_context: bool = True,
        max_context: int = 5,
        abstain_if_ungrounded: bool = False,
        extra_context: str = "",
    ) -> dict:
        """Generate a grounded draft reply.

        Template-first (requirement D): before composing anything, we look for
        an approved canned-response template that matches the email closely
        enough (``_match_template``). If one matches, the LLM's only job is to
        personalize its greeting — the approved wording is preserved, not
        regenerated — and that result is returned immediately, skipping RAG
        retrieval and free composition entirely. This never runs when
        ``extra_context`` is supplied (e.g. specialist guidance on an escalated
        review): that caller-provided override takes priority over template
        matching.

        Otherwise, falls back to RAG-grounded free composition. When
        ``abstain_if_ungrounded`` is set and there is no grounding at all (no
        template match, no retrieved documents, no ``extra_context``), the LLM
        is **not** called and an empty, ungrounded result is returned — a
        deterministic guard so the assistant never invents an answer (prices,
        hours, policy) with no backing. Callers inspect ``grounded`` and route
        ungrounded results to manual handling.

        ``extra_context`` is authoritative caller-supplied grounding (e.g. a
        specialist's guidance on an escalated email) prepended to the context
        block; it counts as grounding so the reply can be built from it.
        """
        citations: list[dict] = []
        context_parts: list[str] = []

        if extra_context.strip():
            context_parts.append(extra_context.strip())
        elif use_context:
            template = await self._match_template(body)
            if template is not None:
                draft = await self.ai.text(
                    system=TEMPLATE_SYSTEM,
                    user=build_template_user(subject, body, template.body),
                    max_tokens=settings.ai_max_tokens,
                )
                logger.info("ai.draft_from_template", template_key=template.key)
                return {
                    "draft": draft,
                    "model": self.ai.model,
                    "citations": [
                        {
                            "document_id": str(template.id),
                            "source": "template",
                            "title": template.title,
                            "url": None,
                        }
                    ],
                    "grounded": True,
                    "requires_human_review": True,
                }

        if use_context:
            hits = await self._retrieve(subject, body, max_context)
            for hit in hits:
                doc = hit.document
                snippet = doc.content[:_CONTEXT_CHARS_PER_DOC]
                context_parts.append(f"[{doc.source}] {doc.title}\n{snippet}")
                citations.append(
                    {
                        "document_id": str(doc.id),
                        "source": doc.source,
                        "title": doc.title,
                        "url": doc.url,
                    }
                )

        grounded = bool(citations) or bool(extra_context.strip())
        if abstain_if_ungrounded and use_context and not grounded:
            logger.info("ai.draft_abstained_no_context")
            return {
                "draft": "",
                "model": self.ai.model,
                "citations": [],
                "grounded": False,
                "requires_human_review": True,
            }

        draft = await self.ai.text(
            system=DRAFT_SYSTEM,
            user=build_draft_user(subject, body, "\n\n".join(context_parts)),
            max_tokens=settings.ai_max_tokens,
        )
        logger.info("ai.draft_generated", citations=len(citations))
        return {
            "draft": draft,
            "model": self.ai.model,
            "citations": citations,
            "grounded": grounded,
            "requires_human_review": True,
        }


async def push_gmail_reply(session: AsyncSession, user: User, message_id: str) -> dict:
    """End-to-end pipeline: fetch a Gmail message, generate a grounded reply
    draft, and create it in the mailbox's Drafts folder (never sends).

    Propagates domain errors for the API layer to translate:
    ``GmailNotConnectedError`` / ``GmailApiError`` (from
    :mod:`app.services.gmail_service`) and ``AIError`` / ``AINotConfiguredError``
    (from :mod:`app.ai.client`).
    """
    gmail = GmailService(session)

    # a) Fetch the incoming patient email (full body, not just the snippet).
    msg = await gmail.get_message(user, message_id)
    subject = msg.get("subject", "")
    body = msg.get("body") or msg.get("snippet", "")
    sender = msg.get("from", "")

    # b) Run it through the RAG draft pipeline.
    draft = await DraftService(session).generate(subject, body)

    # c) Push the AI-generated draft back to the user's Gmail Drafts folder.
    reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    pushed = await gmail.create_draft(
        user,
        to=sender,
        subject=reply_subject,
        body=draft["draft"],
        thread_id=msg.get("thread_id") or None,
        in_reply_to=msg.get("message_id_header") or None,
    )
    logger.info("ai.gmail_draft_pushed", message_id=message_id, draft_id=pushed["draft_id"])
    return {
        "source_message_id": message_id,
        "draft": draft["draft"],
        "model": draft["model"],
        "citations": draft["citations"],
        "requires_human_review": True,
        "gmail_draft_id": pushed["draft_id"],
        "gmail_message_id": pushed["message_id"],
        "gmail_thread_id": pushed["thread_id"],
    }
