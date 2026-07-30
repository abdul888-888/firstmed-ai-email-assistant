"""Seed the retrieval index with sample clinic SOPs for the demo.

Idempotent — safe to run repeatedly (upserts by (source, source_id)). Runs
against the configured database (the demo `.env` points at SQLite).

    cd backend && .venv/Scripts/python.exe scripts/seed_demo.py
"""

from __future__ import annotations

import asyncio

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.document import DocumentSource
from app.repositories.document import DocumentRepository
from app.repositories.template import TemplateRepository

# Notion-style knowledge base + one prior Gmail thread (so both source types cite).
DOCS: list[dict] = [
    {
        "source": DocumentSource.notion.value,
        "source_id": "sop-post-op-fever",
        "title": "Post-Operative Fever & Infection Red-Flag Guidelines",
        "url": "https://www.notion.so/firstmed/Post-Op-Fever-Guidelines",
        "content": (
            "Post-operative fever, swelling, redness, or warmth around a surgical "
            "incision may indicate a wound infection and must be triaged urgently. "
            "Red-flag symptoms after surgery (including knee replacement and other "
            "orthopedic procedures): fever above 100.4F/38C, spreading redness, "
            "increasing swelling, pus or drainage, severe or worsening pain, or "
            "difficulty breathing. Action: escalate to the Nurse Station immediately "
            "and have a clinician review the same day. Advise the patient to seek "
            "emergency care for high or rising fever, chest pain, or difficulty "
            "breathing. Never provide a diagnosis by email; route clinical concerns "
            "to a nurse or the operating specialist."
        ),
    },
    {
        "source": DocumentSource.notion.value,
        "source_id": "sop-prescription-refill",
        "title": "Prescription Refill Protocol",
        "url": "https://www.notion.so/firstmed/Prescription-Refill-Protocol",
        "content": (
            "Prescription refill requests (including blood pressure medications such "
            "as lisinopril, amlodipine, and losartan) are handled by the Nurse "
            "Station. Standard refills are reviewed and sent to the patient's "
            "pharmacy within 48 hours. Collect the medication name, dosage, and "
            "preferred pharmacy. Controlled substances require a provider visit and "
            "cannot be refilled by email. Confirm to the patient once the refill has "
            "been sent to their pharmacy."
        ),
    },
    {
        "source": DocumentSource.notion.value,
        "source_id": "faq-billing-parking",
        "title": "Billing Hours & Parking Validation FAQ",
        "url": "https://www.notion.so/firstmed/Billing-Parking-FAQ",
        "content": (
            "Billing office hours: Monday to Friday, 9:00am to 5:00pm. Billing and "
            "insurance questions are handled by the Front Office. Patients can pay "
            "by phone during business hours or through the patient portal. Parking "
            "validation: bring your parking ticket to the front desk during your "
            "visit and staff will validate it for the parking garage. No validation "
            "is available for street parking."
        ),
    },
    {
        "source": DocumentSource.notion.value,
        "source_id": "sop-appointment-scheduling",
        "title": "Appointment Scheduling SOP",
        "url": "https://www.notion.so/firstmed/Appointment-Scheduling-SOP",
        "content": (
            "Appointment requests, reschedules, and cancellations are handled by the "
            "Front Office. Offer the earliest available slot and confirm the "
            "patient's preferred provider and location. Same-day clinical concerns "
            "should be routed to the Nurse Station rather than booked as a routine "
            "appointment."
        ),
    },
    {
        "source": DocumentSource.gmail.value,
        "source_id": "thread-post-op-triage-2026-05",
        "title": "Re: Post-op swelling — nurse triage response (template)",
        "url": None,
        "content": (
            "Prior handled thread: patient reported swelling and low-grade fever "
            "after knee surgery. Front office escalated to the Nurse Station the "
            "same day; nurse advised the patient to come in for a wound check and to "
            "go to the ER if the fever rose above 101F or redness spread. Outcome: "
            "seen same day, minor infection treated with antibiotics. Use this as a "
            "reference for post-operative escalation tone and next steps."
        ),
    },
    # --- Pricing "database" rows -----------------------------------------
    # These mimic what the fixed Notion database-row ingestion now produces:
    # one document per service row, with typed properties flattened to text
    # ("Service: X\nSelf-Pay Price: $Y..."). Swap the source_ids for real Notion
    # row IDs once you connect a live pricing database.
    {
        "source": DocumentSource.notion.value,
        "source_id": "price-row-consultation",
        "title": "General Consultation",
        "url": "https://www.notion.so/firstmed/Pricing",
        "content": (
            "General Consultation\n"
            "Service: General Consultation\n"
            "Self-Pay Price: $120\n"
            "Duration: 30 minutes\n"
            "Category: Primary Care\n"
            "Notes: Covered by most insurance plans after copay."
        ),
    },
    {
        "source": DocumentSource.notion.value,
        "source_id": "price-row-mri",
        "title": "MRI Scan",
        "url": "https://www.notion.so/firstmed/Pricing",
        "content": (
            "MRI Scan\n"
            "Service: MRI Scan (single region)\n"
            "Self-Pay Price: $650\n"
            "Duration: 45 minutes\n"
            "Category: Imaging\n"
            "Notes: Prior authorization required for most insurers."
        ),
    },
    {
        "source": DocumentSource.notion.value,
        "source_id": "price-row-bloodwork",
        "title": "Standard Blood Panel",
        "url": "https://www.notion.so/firstmed/Pricing",
        "content": (
            "Standard Blood Panel\n"
            "Service: Standard Blood Panel (CBC + metabolic)\n"
            "Self-Pay Price: $85\n"
            "Category: Laboratory\n"
            "Notes: Fasting required for accurate results."
        ),
    },
    # --- Insurance "database" rows ---------------------------------------
    {
        "source": DocumentSource.notion.value,
        "source_id": "insurance-accepted-plans",
        "title": "Accepted Insurance Plans",
        "url": "https://www.notion.so/firstmed/Insurance",
        "content": (
            "Accepted Insurance Plans\n"
            "FirstMed accepts the following insurance plans: Aetna, Blue Cross "
            "Blue Shield (PPO and HMO), Cigna, UnitedHealthcare, Humana, and "
            "Medicare. We are out-of-network for Kaiser Permanente. "
            "For Medicaid, only select managed-care plans are accepted — the "
            "Front Office can confirm eligibility. Patients should bring their "
            "insurance card to every visit. Copays are due at check-in."
        ),
    },
    {
        "source": "notion",
        "source_id": "sop_clinic_hours",
        "title": "General Clinic Operating Hours and Holiday Schedule",
        "url": None,
        "content":( """
        FIRSTMED CLINIC OPERATING HOURS AND SCHEDULE

        Our general clinic operating hours for walk-ins, scheduled appointments, and phone support are:
        - Monday to Friday: 8:00 AM to 8:00 PM
        - Saturday: 9:00 AM to 2:00 PM (Urgent Care and pre-scheduled appointments only)
        - Sunday: CLOSED

        Holidays:
        The clinic is closed on New Year's Day, Memorial Day, Independence Day, Labor Day, Thanksgiving, and Christmas Day. On Christmas Eve and New Year's Eve, we close early at 1:00 PM.

        After-Hours Support:
        If patients call or email outside of these hours, our automated system will triage their message. For urgent medical emergencies, patients are always advised to visit the nearest emergency room or dial 911.
        """),
   },
]

# Approved canned-response templates (Phase 7). DraftService tries these FIRST
# (see DraftService._match_template) — when one matches closely enough, its
# wording is used verbatim (only the greeting is personalized) instead of free
# LLM composition. Two of these deliberately overlap topics with docs above
# (parking, clinic hours) so you can see the template win over the KB doc.
TEMPLATES: list[dict] = [
    {
        "key": "parking-validation",
        "title": "Parking Validation",
        "category": "front_office",
        "body": (
            "We validate parking for all scheduled visits. Please bring your "
            "parking ticket to the front desk during check-in and our staff "
            "will validate it for the garage. Street parking cannot be "
            "validated."
        ),
    },
    {
        "key": "clinic-hours",
        "title": "Clinic Hours",
        "category": "front_office",
        "body": (
            "Our clinic hours are Monday to Friday, 8:00 AM to 8:00 PM, and "
            "Saturday, 9:00 AM to 2:00 PM (Urgent Care and pre-scheduled "
            "appointments only). We are closed Sundays and major holidays. "
            "For medical emergencies outside these hours, please call 911 or "
            "go to the nearest emergency room."
        ),
    },
    {
        "key": "refill-acknowledgement",
        "title": "Prescription Refill Acknowledgement",
        "category": "general",
        "body": (
            "Thank you for your prescription refill request. Our Nurse "
            "Station reviews refill requests and sends approved refills to "
            "your pharmacy within 48 hours. Please reply with your "
            "medication name, dosage, and preferred pharmacy if you haven't "
            "already, so we can process this promptly."
        ),
    },
    {
        "key": "lab-preparation-fasting",
        "title": "Lab Test Preparation (Fasting)",
        "category": "general",
        "body": (
            "For most standard blood panels, please fast (no food or drink "
            "except water) for 8-12 hours before your appointment. You may "
            "take routine medications with a small sip of water unless your "
            "provider told you otherwise. Please arrive 10 minutes early and "
            "bring a photo ID and your insurance card."
        ),
    },
    # Physio requests are always ROUTE_TO_STAFF (see app/services/safety.py) —
    # this template is NOT auto-drafted. It exists for staff to use manually
    # via the /templates picker when replying to a routed physio-without-
    # referral card, per the "informational template, not a booking attempt"
    # requirement.
    {
        "key": "physio-referral-required",
        "title": "Physiotherapy — Orthopaedic Referral Required",
        "category": "general",
        "body": (
            "Thank you for reaching out about physiotherapy. Our policy "
            "requires an orthopaedic consultation before starting "
            "physiotherapy so your treatment plan can be tailored "
            "appropriately. Please schedule an orthopaedic consult first; "
            "once that provider clears you for physiotherapy, our "
            "Physiotherapy team will contact you directly to book your "
            "sessions."
        ),
    },
]


async def main() -> None:
    async with AsyncSessionLocal() as session:
        repo = DocumentRepository(session)
        for d in DOCS:
            await repo.upsert(
                source=d["source"],
                source_id=d["source_id"],
                title=d["title"],
                content=d["content"],
                url=d["url"],
                doc_metadata={"seeded": True, "demo": True},
            )
        counts = await repo.counts_by_source()

        templates = TemplateRepository(session)
        for t in TEMPLATES:
            await templates.upsert(
                key=t["key"], title=t["title"], category=t["category"], body=t["body"]
            )

    print(f"DB: {settings.sqlalchemy_database_uri}")
    print(f"Seeded {len(DOCS)} documents. Index counts by source: {counts}")
    print(f"Seeded {len(TEMPLATES)} templates.")


if __name__ == "__main__":
    asyncio.run(main())
