"""Unit tests for the AI draft service (fake AI client + seeded index)."""

from __future__ import annotations

from app.models.document import DocumentSource
from app.repositories.document import DocumentRepository
from app.repositories.template import TemplateRepository
from app.services.draft_service import DraftService


class FakeAI:
    model = "claude-test"

    def __init__(self, text_return: str = "Draft reply. The FirstMed Team") -> None:
        self._text = text_return
        self.last_kwargs: dict | None = None

    async def text(self, **kwargs):
        self.last_kwargs = kwargs
        return self._text


async def _seed(db_session):
    repo = DocumentRepository(db_session)
    await repo.upsert(
        source=DocumentSource.notion.value,
        source_id="sop1",
        title="Prescription refill SOP",
        content="Refills are processed within 48 hours by a nurse.",
        url="https://notion.so/sop1",
    )


async def test_generate_with_context_produces_citations(db_session):
    await _seed(db_session)
    fake = FakeAI()
    result = await DraftService(db_session, ai=fake).generate(
        "Refill request", "Can I get my prescription refilled?", use_context=True
    )

    assert result["draft"].startswith("Draft reply")
    assert result["model"] == "claude-test"
    assert result["requires_human_review"] is True
    assert len(result["citations"]) == 1
    cite = result["citations"][0]
    assert cite["source"] == DocumentSource.notion.value
    assert cite["title"] == "Prescription refill SOP"
    # retrieved content was injected into the prompt
    assert "48 hours" in fake.last_kwargs["user"]


async def test_generate_without_context_has_no_citations(db_session):
    await _seed(db_session)
    fake = FakeAI()
    result = await DraftService(db_session, ai=fake).generate(
        "Refill request", "Refill please", use_context=False
    )
    assert result["citations"] == []
    assert "48 hours" not in fake.last_kwargs["user"]


async def test_generate_abstains_when_ungrounded(db_session):
    # No documents match → with abstain flag set, the LLM must NOT be called and
    # the result is flagged ungrounded (deterministic no-fabrication guard).
    await _seed(db_session)
    fake = FakeAI()
    result = await DraftService(db_session, ai=fake).generate(
        "Parking", "Where can I find dinosaurs on the moon?", abstain_if_ungrounded=True
    )
    assert result["grounded"] is False
    assert result["draft"] == ""
    assert result["citations"] == []
    assert fake.last_kwargs is None  # AI client never invoked


async def test_extra_context_counts_as_grounding(db_session):
    # Specialist guidance passed as extra_context grounds the reply even with no
    # matching documents, so the draft is generated (not abstained).
    fake = FakeAI()
    result = await DraftService(db_session, ai=fake).generate(
        "Follow-up",
        "Patient asks about next steps.",
        abstain_if_ungrounded=True,
        extra_context="SPECIALIST GUIDANCE: advise the patient to rest for one week.",
    )
    assert result["grounded"] is True
    assert result["draft"].startswith("Draft reply")
    assert "rest for one week" in fake.last_kwargs["user"]


# --- template-first (requirement D) -----------------------------------------


async def _seed_template(db_session, **overrides):
    fields = {
        "key": "parking_validation",
        "title": "Parking Validation",
        "category": "front_office",
        "body": (
            "We validate parking for all scheduled visits. Bring your parking "
            "ticket to the front desk during check-in and staff will validate "
            "it for the garage. Street parking cannot be validated."
        ),
    }
    fields.update(overrides)
    return await TemplateRepository(db_session).upsert(**fields)


async def test_generate_prefers_template_over_documents(db_session):
    # Seed BOTH a matching document and a matching template — the approved
    # template must win; free RAG composition must not run for this email.
    await DocumentRepository(db_session).upsert(
        source=DocumentSource.notion.value,
        source_id="parking-sop",
        title="Parking SOP",
        content="Parking validation is available at the front desk for visits.",
        url="https://notion.so/parking-sop",
    )
    await _seed_template(db_session)
    fake = FakeAI(text_return="Hi! " + "validated at check-in. The FirstMed Team")

    result = await DraftService(db_session, ai=fake).generate(
        "Parking question", "Do you validate parking for my visit?"
    )

    assert result["grounded"] is True
    assert len(result["citations"]) == 1
    cite = result["citations"][0]
    assert cite["source"] == "template"
    assert cite["title"] == "Parking Validation"
    # The template-personalization prompt (not the free-compose prompt) was used.
    assert "APPROVED TEMPLATE" in fake.last_kwargs["user"]
    assert "validate parking for all scheduled visits" in fake.last_kwargs["user"]


async def test_generate_falls_back_to_documents_when_no_template_matches(db_session):
    # A template exists but doesn't match this email — must fall through to the
    # normal document-grounded path, not silently produce no citations.
    await _seed(db_session)
    await _seed_template(db_session)  # unrelated to the refill question below
    fake = FakeAI()

    result = await DraftService(db_session, ai=fake).generate(
        "Refill request", "Can I get my prescription refilled?"
    )

    assert result["citations"][0]["source"] == DocumentSource.notion.value


async def test_extra_context_skips_template_matching(db_session):
    # Specialist guidance (extra_context) takes priority over template
    # matching entirely — even if a template would otherwise match the body.
    await _seed_template(
        db_session,
        key="refill_ack",
        title="Refill",
        body="Can I get my prescription refilled? Yes, within 48 hours.",
    )
    fake = FakeAI()

    result = await DraftService(db_session, ai=fake).generate(
        "Follow-up",
        "Can I get my prescription refilled?",
        extra_context="SPECIALIST GUIDANCE: approve the refill.",
    )

    assert all(c["source"] != "template" for c in result["citations"])
    assert "SPECIALIST GUIDANCE" in fake.last_kwargs["user"]


# --- relevance-floor tuning: conversational filler + significance weighting -


async def _seed_mri_pricing_doc(db_session):
    await DocumentRepository(db_session).upsert(
        source=DocumentSource.notion.value,
        source_id="price-row-mri",
        title="MRI Scan",
        content=(
            "MRI Scan\nService: MRI Scan (single region)\nSelf-Pay Price: $650\n"
            "Duration: 45 minutes\nCategory: Imaging\n"
            "Notes: Prior authorization required for most insurers."
        ),
        url="https://www.notion.so/firstmed/Pricing",
    )


async def test_chatty_phrasing_still_grounds_on_clean_topical_match(db_session):
    # Regression test for a real smoke-test finding: a naturally-phrased,
    # chatty patient email (greeting + pleasantries) was diluting the term
    # ratio enough to abstain even though "MRI"/"scan" cleanly match the
    # pricing doc. Filler-stripping + significant-term weighting must fix this.
    await _seed_mri_pricing_doc(db_session)
    fake = FakeAI()

    result = await DraftService(db_session, ai=fake).generate(
        "Question about MRI pricing",
        "Hi, I wanted to ask how much an MRI scan costs at your clinic. Thanks!",
        abstain_if_ungrounded=True,
    )

    assert result["grounded"] is True
    assert result["draft"] != ""
    assert result["citations"][0]["title"] == "MRI Scan"


async def test_chatty_phrasing_does_not_spuriously_match_unrelated_title(db_session):
    # The exact false-positive a first attempt at this fix introduced: a
    # blanket "any term matching the TITLE counts extra" rule let the generic
    # word "clinic" (from "...at your clinic...") alone match a "Clinic Hours"
    # template's title, outscoring the real MRI-pricing match. Seeding both
    # here so the competition is real, not just "the only candidate happens
    # to be right".
    await _seed_mri_pricing_doc(db_session)
    await _seed_template(
        db_session,
        key="clinic-hours",
        title="Clinic Hours",
        body="Our clinic hours are Monday to Friday, 8am to 8pm.",
    )
    fake = FakeAI()

    result = await DraftService(db_session, ai=fake).generate(
        "Question about MRI pricing",
        "Hi, I wanted to ask how much an MRI scan costs at your clinic. Thanks!",
        abstain_if_ungrounded=True,
    )

    assert result["grounded"] is True
    # Must ground on the actual topical match, not the generic-word coincidence.
    assert all(c["title"] != "Clinic Hours" for c in result["citations"])
    assert result["citations"][0]["title"] == "MRI Scan"


async def test_significant_term_backstop_rescues_ranking_cutoff(db_session, monkeypatch):
    # Second real gap the same live smoke test caught, after fixing the
    # generic-title false positive above: the underlying lexical/semantic
    # SEARCH ranking (separate from the relevance floor) can rank a terse,
    # exact topical match (a "MRI Scan" pricing row) below chattier documents
    # that share more raw surface overlap with a filler-heavy patient email —
    # cutting it out of the top-N candidate window before the relevance floor
    # ever gets to evaluate it. Force the ranking to return nothing (isolating
    # the backstop mechanism from the ranking's own, harder-to-predict
    # behavior) and confirm the direct significant-term lookup still finds
    # and grounds on it.
    await _seed_mri_pricing_doc(db_session)

    async def fake_search(self, query, *, sources=None, limit=20):
        return []

    monkeypatch.setattr("app.services.search_service.SearchService.search", fake_search)
    fake = FakeAI()

    result = await DraftService(db_session, ai=fake).generate(
        "Question about MRI pricing",
        "Hi, I wanted to ask how much an MRI scan costs at your clinic. Thanks!",
        abstain_if_ungrounded=True,
    )

    assert result["grounded"] is True
    assert any(c["title"] == "MRI Scan" for c in result["citations"])


async def test_botox_false_positive_guard_still_holds(db_session):
    # Fail-safe check: the tuning must not reopen the original bug it was
    # built to close — a single incidental, non-significant match ("offer")
    # must still not count as grounding, even with the new weighting in play.
    await DocumentRepository(db_session).upsert(
        source=DocumentSource.notion.value,
        source_id="sop-appointment-scheduling",
        title="Appointment Scheduling SOP",
        content=(
            "Appointment requests, reschedules, and cancellations are handled by "
            "the Front Office. Offer the earliest available slot and confirm the "
            "patient's preferred provider and location."
        ),
        url="https://notion.so/appt-sop",
    )
    fake = FakeAI()

    result = await DraftService(db_session, ai=fake).generate(
        "Question", "Do you offer Botox injections?", abstain_if_ungrounded=True
    )

    assert result["grounded"] is False
    assert result["draft"] == ""
    assert fake.last_kwargs is None


async def test_lone_significant_term_match_needs_corroboration(db_session):
    # Real regression the weighting reopened, caught via live re-verification:
    # "Do you accept Aetna insurance?" matched a "Billing office hours"
    # template purely because "insurance" (weight 3) alone cleared the floor
    # for a 3-term query — a single incidental keyword hit, laundered through
    # weight instead of a generic word, same failure shape as the Botox case.
    # The correct grounding doc (matching all three terms) must win instead.
    await _seed_template(
        db_session,
        key="billing-hours",
        title="Billing office hours",
        body=(
            "Our billing office is available Monday-Friday, 9am to 5pm. For "
            "insurance questions, our front office team is happy to help."
        ),
    )
    await DocumentRepository(db_session).upsert(
        source=DocumentSource.notion.value,
        source_id="accepted-insurance-plans",
        title="Accepted Insurance Plans",
        content="FirstMed accepts the following insurance plans: Aetna, Blue Cross Blue Shield, Cigna.",
        url="https://notion.so/insurance-plans",
    )
    fake = FakeAI()

    result = await DraftService(db_session, ai=fake).generate(
        "Insurance question", "Do you accept Aetna insurance?", abstain_if_ungrounded=True
    )

    assert result["grounded"] is True
    assert all(c["title"] != "Billing office hours" for c in result["citations"])
    assert any(c["title"] == "Accepted Insurance Plans" for c in result["citations"])


async def test_conversational_filler_alone_does_not_ground():
    from app.services.draft_service import _significant_terms

    # Pure pleasantries strip to nothing meaningful — no false signal left over.
    # ("so" is already stripped by search_service's base stopword list.)
    assert _significant_terms("Hi, thanks so much, please, kindly, best wishes") == [
        "much",
        "wishes",
    ]


async def test_significant_terms_outweigh_missing_generic_terms():
    from app.services.draft_service import _is_relevant

    terms = ["much", "mri", "scan", "costs", "clinic"]  # 5 terms, need weight >= 3
    # "mri" and "scan" are domain-significant (3 pts each = 6) — clears the
    # floor even though "much"/"costs"/"clinic" match nothing at all.
    assert _is_relevant(
        terms,
        title="MRI Scan",
        body="Self-Pay Price: $650. Prior authorization required.",
    )


async def test_generic_word_matching_title_alone_is_not_enough():
    from app.services.draft_service import _is_relevant

    terms = ["much", "mri", "scan", "costs", "clinic"]  # same 5 terms as above
    # "clinic" is the ONLY match here, and it's generic (not in
    # _SIGNIFICANT_TERMS) — weight 1 total, must NOT clear the floor (need 3).
    # This is the exact false-positive a first attempt at this fix produced.
    assert not _is_relevant(
        terms,
        title="Clinic Hours",
        body="Our clinic hours are Monday to Friday, 8am to 8pm.",
    )
