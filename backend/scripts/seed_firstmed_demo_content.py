"""Seed fictional FirstMed content for local demonstrations only.

All amounts, locations, hours, and policies in this file are invented. Replace
them with approved clinic information before any production use.
"""

from __future__ import annotations

import asyncio

from app.core.database import AsyncSessionLocal
from app.models.document import DocumentSource
from app.repositories.document import DocumentRepository
from app.repositories.template import TemplateRepository


KNOWLEDGE = (
    (
        "demo-mri-pricing",
        "Demo MRI pricing",
        "DEMO DATA ONLY. A standard MRI scan starts at EUR 250. A contrast MRI starts at EUR 325. "
        "The final price depends on the body area and whether contrast is clinically required. "
        "Patients should contact FirstMed Front Office for a confirmed quotation.",
        "pricing",
    ),
    (
        "demo-parking",
        "Demo parking and access",
        "DEMO DATA ONLY. Visitor parking is available at the FirstMed demo clinic. Patients should bring "
        "their parking ticket to reception for validation. Accessible spaces are located near the main entrance.",
        "parking",
    ),
    (
        "demo-opening-hours",
        "Demo opening hours and contact",
        "DEMO DATA ONLY. FirstMed Front Office is open Monday to Friday, 08:00 to 18:00, and Saturday, "
        "09:00 to 13:00. The demo contact number is +00 123 456 789 and the demo email is hello@firstmed.example.",
        "contact",
    ),
    (
        "demo-services",
        "Demo service availability",
        "DEMO DATA ONLY. FirstMed offers MRI imaging, dermatology consultations, paediatric services, "
        "physiotherapy, laboratory testing, and gastroenterology consultations. Availability must be confirmed by staff.",
        "services",
    ),
    (
        "demo-insurance",
        "Demo insurance information",
        "DEMO DATA ONLY. FirstMed can review coverage from participating insurance providers. Patients should provide "
        "their insurer name, membership number, and any pre-authorisation reference. Coverage and co-payments must be confirmed individually.",
        "insurance",
    ),
    (
        "demo-lab-preparation",
        "Demo laboratory preparation",
        "DEMO DATA ONLY. For a fasting blood test, patients should avoid food for 8 hours and may drink water unless told otherwise. "
        "Patients should bring photo identification and their referral if they have one. Staff must confirm test-specific instructions.",
        "preparation",
    ),
)

TEMPLATES = (
    (
        "demo-mri-pricing",
        "Demo MRI pricing response",
        "billing",
        "Thank you for contacting FirstMed.\n\nFor this demonstration, a standard MRI scan starts at EUR 250, while a contrast MRI starts at EUR 325. The final cost depends on the body area being examined and whether contrast is required.\n\nOur Front Office team can confirm the exact quotation for your request.\n\nKind regards,\nThe FirstMed Team",
    ),
    (
        "demo-parking-information",
        "Demo parking information response",
        "front_office",
        "Thank you for contacting FirstMed.\n\nFor this demonstration, visitor parking is available at the clinic. Please bring your parking ticket to reception for validation. Accessible parking is available near the main entrance.\n\nKind regards,\nThe FirstMed Team",
    ),
    (
        "demo-opening-hours",
        "Demo opening hours response",
        "front_office",
        "Thank you for contacting FirstMed.\n\nFor this demonstration, our Front Office is open Monday to Friday from 08:00 to 18:00 and Saturday from 09:00 to 13:00.\n\nKind regards,\nThe FirstMed Team",
    ),
    (
        "demo-service-availability",
        "Demo service availability response",
        "general",
        "Thank you for contacting FirstMed.\n\nFor this demonstration, FirstMed offers MRI imaging, dermatology consultations, paediatric services, physiotherapy, laboratory testing, and gastroenterology consultations. Our team can confirm the appropriate next step for the service you need.\n\nKind regards,\nThe FirstMed Team",
    ),
    (
        "demo-insurance-information",
        "Demo insurance information response",
        "billing",
        "Thank you for contacting FirstMed.\n\nWe can review insurance coverage for participating providers. Please send us your insurer name, membership number, and any pre-authorisation reference. Coverage and any co-payment will be confirmed individually.\n\nKind regards,\nThe FirstMed Team",
    ),
    (
        "demo-lab-preparation",
        "Demo laboratory preparation response",
        "front_office",
        "Thank you for contacting FirstMed.\n\nFor this demonstration, fasting blood-test patients should avoid food for 8 hours and may drink water unless they have received different instructions. Please bring photo identification and your referral if applicable. Our staff can confirm test-specific preparation.\n\nKind regards,\nThe FirstMed Team",
    ),
)


async def main() -> None:
    async with AsyncSessionLocal() as session:
        documents = DocumentRepository(session)
        templates = TemplateRepository(session)
        for key, title, content, category in KNOWLEDGE:
            await documents.upsert(
                source=DocumentSource.firstmed.value,
                source_id=key,
                title=title,
                content=content,
                doc_metadata={"category": category, "demo": True},
            )
        for key, title, category, body in TEMPLATES:
            await templates.upsert(key=key, title=title, category=category, body=body)
    print(f"Seeded {len(KNOWLEDGE)} demo knowledge entries and {len(TEMPLATES)} demo templates.")


if __name__ == "__main__":
    asyncio.run(main())
