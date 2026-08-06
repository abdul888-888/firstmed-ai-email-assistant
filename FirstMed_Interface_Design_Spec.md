# FirstMed Reply Review — Interface Design Spec

This document specifies the frontend only: screens, layout, states, and interactions. It does not prescribe backend architecture, data models, or API implementation — each screen lists what data/actions it needs, and the backend team/agent can implement those however fits the existing system.

Reference prototypes (built and agreed during design): three-pane console, simplified role views, Needs Attention triage, Admin Dashboard, login/role-routing flow.

---

## 1. Screens Overview

| Screen | Who sees it | Purpose |
|---|---|---|
| Login | Everyone | Single entry point for all roles |
| Front Office Console | Front Office, Admin | Full queue + draft review + send |
| Clinical Reviewer View | Clinical Reviewers (nurses, specialists) | Answer assigned clinical questions |
| Booking Coordinator View | Booking Coordinators (e.g. physio, procedure scheduling) | Own and send from their scoped queue |
| Needs Attention | Front Office, Admin | Recurring gaps, stalled items, quick triage |
| Admin Dashboard | Admin only | Staff/roles, routing rules, audit log |

---

## 2. Login

**Layout:** single centered form — email, password, "Log in." No role selector; role is determined after authentication, not chosen by the user.

**States:**
- Standard login → redirect to the user's primary view based on their role.
- Admin login → after password, show a second-factor prompt (code entry) before redirecting to console access.
- Invalid credentials → inline error, no indication of whether the email or password was wrong (standard security practice).
- First-time user (arriving via invite link) → "Set your password" form instead of login, then proceeds as normal login.

**Needs from backend:** authenticate call returning role(s) and a redirect target; 2FA challenge/verify calls for admin.

---

## 3. Front Office Console

Three-pane layout, fixed proportions: queue (~280px) / thread+draft (flexible) / context panel (~320px).

### 3.1 Department tabs (top strip)
Horizontal tabs: All, Pricing & Insurance, Bookings, Lab, Physio, Specialist review, Billing, Complaints (tab set should mirror whatever routing categories are configured — not hardcoded to exactly these). Each tab shows a count. Selecting a tab filters the queue below; does not affect the other two panes until a new item is selected.

### 3.2 Queue (left pane)
- List of items, each showing: sender name, subject (truncated), time received, a status tag, and an SLA-aging chip.
- Sort order: urgency first (urgent items pinned to top regardless of arrival time), then oldest-first within the same urgency tier.
- Status tags (visually distinct, color-coded): **Drafted** (ready for review), **Routed** (escalated, no draft — shows target department), **Waiting on specialist**, **Pending** (awaiting knowledge-base match).
- SLA chip: three states — on-time (neutral/green), at-risk (amber), overdue (red) — based on time-in-queue thresholds. Overdue items also get a red left-border on the row.
- Clicking an item loads it into the center + right panes and marks it active (visually highlighted).

### 3.3 Thread + draft (center pane)
- Subject line and sender metadata at top.
- Patient's original message, shown as a read-only bubble.
- **If drafted:** an editable draft box with a clear "AI draft — not sent" label, the template it was matched to (if any), an inline-editable body, and action buttons: **Approve & send**, **Edit further**, **Reassign**.
- **If escalated/routed (no draft):** no editable draft box at all. Instead, a banner explaining why ("Routed to X because Y") and to whom. This is a hard rule — an excluded-category item must never render an editable draft field, even empty.
- **If waiting on a specialist:** a status strip showing current state and who owns/who's blocking, the question sent to the specialist shown as a bubble, and a greyed-out draft area with "Draft will regenerate once [specialist] responds." Approve & send is disabled in this state; a "Nudge" action is available instead.

### 3.4 Context panel (right pane)
- **Source used:** each citation/template the draft pulled from, with enough reference (e.g. source name) to trace it back — this is the trust/verification mechanism, not decorative.
- **Match confidence:** a simple visual indicator (bar or percentage) plus one line of explanation when confidence is not near-certain.
- **Routing trail:** for escalated items, a short numbered trail showing where the item has been and where it's going next.
- **Who can send:** explicit list of who currently has send rights on this item (important when a specialist is involved but cannot send).
- **Internal note / collaboration:** free-text area for staff notes, and a way to @-mention/assign a colleague for input without leaving the item.

---

## 4. Clinical Reviewer / Booking Coordinator View

Deliberately minimal — a list, not a console.

- Header: "Questions needing your input" (Clinical Reviewer) or "Your queue" (Booking Coordinator).
- Each item as a card: who asked, the question, an SLA/waiting-time badge, a text box, and action buttons.
- **Clinical Reviewer actions:** "Send answer to Front Office" (submits as a comment, not a send), and an escape hatch like "Needs a phone call instead" for anything too sensitive for email.
- **Booking Coordinator actions:** since they have send rights on their own queue, their equivalent action sends directly rather than routing back through Front Office.
- No department tabs, no routing-rule visibility, no other queues — if a permission check would be needed to hide something, it shouldn't be rendered in the first place (enforce this server-side, not just by omitting it from this view's design).

---

## 5. Needs Attention

Replaces a manual-only review dashboard. Three distinct sections — do not merge them, they represent different problems:

### 5.1 Recurring knowledge gaps
List of questions the system couldn't answer from the knowledge base, grouped by normalized topic, with an occurrence counter. Once a gap crosses a configurable repeat threshold, it gets a visually distinct escalation marker (e.g. "escalated to Practice Manager") — this should happen automatically, not require someone to notice it.

### 5.2 Stalled items
List of items waiting on a specific person past a time threshold, with elapsed time and an auto-nudge indicator once that threshold is crossed. Kept separate from knowledge gaps since the fix is different (a person needs to respond, not a KB entry needs to be added).

### 5.3 Quick triage
For low-confidence or likely-irrelevant items (spam, vendor mail, one-word replies to closed threads): a short list with a confidence indicator and two one-tap actions — accept (archive) or reject (send to a real queue). This should be fast enough to clear in a few seconds per item, not a chore.

---

## 6. Admin Dashboard

Grid of cards, admin-only.

- **Staff & roles:** table of staff, their assigned role(s), and send-rights scope; "add staff member" action (triggers the invite flow from §2); deactivate action per staff row.
- **Routing rules:** editable list of category → target-queue mappings; add/edit/remove without needing a deploy.
- **Audit log:** chronological feed of sends, approvals, edits, routing changes, and admin actions themselves (who changed a rule, who added/deactivated staff) — read-only here.
- (Optional secondary placement) a rollup of the knowledge-gap report for manager-level visibility alongside the operational Needs Attention view.

---

## 7. Cross-Cutting UI Rules

- **No role-gated content should render for a user without that role**, even briefly — check permission before rendering, not after, and never rely on hiding a button as the only protection (this is a design instruction to pair every gated UI element with a corresponding access check, even though the check itself is a backend concern).
- **Urgent/overdue items get a persistent visual signal** wherever they appear (queue row, tab count, Needs Attention) — color plus position, not color alone, for accessibility.
- **Every AI-generated draft is visibly labeled as such**, everywhere it appears, with its source trace one click away — never presented as if a human wrote it from scratch.
- **Escalated/no-draft items never show an editable draft field** — this is a safety-relevant UI rule, not a style preference; treat it as a hard constraint during implementation and review.
- Visual language (calm, low-saturation palette; clear status color-coding for drafted/escalated/pending/overdue) should stay consistent across all five screens so switching between roles' views doesn't feel like a different product.

---

## 8. Out of Scope for This Document

Backend logic for classification, routing decisions, Notion retrieval, send permissions enforcement, database schema, and API design are intentionally not covered here — see the separate PRD if those are needed. This document assumes those capabilities exist or will be implemented separately, and focuses only on how the interface should look, behave, and communicate state to the person using it.
