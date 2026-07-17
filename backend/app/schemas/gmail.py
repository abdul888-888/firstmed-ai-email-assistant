"""Gmail API response schemas (Phase 2)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.ai import Citation


class GmailConnection(BaseModel):
    """Whether the current user has linked Google/Gmail access."""

    connected: bool
    email: str | None = None
    scopes: list[str] = Field(default_factory=list)
    mailbox: str = "me"


class GmailMessageSummary(BaseModel):
    id: str
    thread_id: str


class GmailMessageList(BaseModel):
    messages: list[GmailMessageSummary] = Field(default_factory=list)
    result_size_estimate: int = 0
    mailbox: str = "me"


class GmailMessage(BaseModel):
    id: str
    thread_id: str
    snippet: str = ""
    # Full extracted text body (text/plain preferred, HTML tag-stripped fallback).
    # Empty when the message has no inline textual part.
    body: str = ""
    subject: str = ""
    sender: str = Field(default="", alias="from")
    to: str = ""
    date: str = ""
    # RFC822 Message-ID header (for reply threading), distinct from ``id``.
    message_id_header: str = ""
    label_ids: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class GmailDraftSummary(BaseModel):
    id: str
    message_id: str = ""
    thread_id: str = ""


class GmailDraftList(BaseModel):
    drafts: list[GmailDraftSummary] = Field(default_factory=list)
    result_size_estimate: int = 0
    mailbox: str = "me"


class GmailDraftPushResult(BaseModel):
    """Result of running a Gmail message through triage + drafting and pushing
    the AI-generated reply back to the mailbox's Drafts folder."""

    source_message_id: str
    draft: str
    model: str
    citations: list[Citation] = Field(default_factory=list)
    # Human-in-the-loop guardrail — the draft is created but never sent.
    requires_human_review: bool = True
    gmail_draft_id: str
    gmail_message_id: str = ""
    gmail_thread_id: str = ""
