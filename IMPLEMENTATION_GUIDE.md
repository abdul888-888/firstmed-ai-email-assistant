# Phase 14: Specialist Collaboration & Irrelevant Email Handling

## Overview

This phase implements advanced cross-department collaboration, irrelevant email filtering, and a completely redesigned professional UI for managing patient email workflows.

## Key Features Implemented

### 1. Irrelevant Email Filtering

**Problem Solved:** Automatically replies to every email, including spam and out-of-scope messages.

**Solution:**
- Added `irrelevant` intent to the triage classification
- Emails marked as irrelevant skip draft generation entirely
- Reviews marked with `irrelevant` status are logged but don't require action

**How It Works:**
1. During triage, Claude evaluates whether an email is relevant to FirstMed
2. Marketing, spam, emails to wrong recipients → automatically marked "irrelevant"
3. No draft is generated, reducing clutter in the review queue
4. Staff can still view irrelevant emails for context but they don't block workflows

**Frontend Indicator:**
- Irrelevant emails show a gray "Irrelevant" badge
- Message: "This email was marked as irrelevant"
- No action buttons

### 2. Specialist Input Loop

**Problem Solved:** No true collaboration—escalated emails still auto-draft without specialist input.

**Solution:**
- New `awaiting_specialist_input` status for escalated reviews
- Specialists can submit clinical guidance which triggers draft revision
- Workflow waits for specialist input before finalizing response

**Status Flow:**
```
pending (routine admin)
    ↓
    [Approve] → approved → sent

pending (escalated medical content)
    ↓
    awaiting_specialist_input
        ↓
        [Specialist provides input]
        ↓
        specialist_input_received
        ↓
        [Optionally revise draft with specialist guidance]
        ↓
        [Approve] → approved → sent
```

**API Endpoints:**
- `POST /api/v1/reviews/{review_id}/specialist-input`
  - Body: `{ "specialist_input": "...", "should_revise_draft": true }`
  - Triggers draft regeneration with specialist guidance if enabled

### 3. Department Routing

**Implementation:**
- Emails automatically routed to the correct department:
  - **Front Office**: Scheduling, billing, insurance, general admin
  - **Nurse**: Prescription refills, symptom questions, symptom triage
  - **Specialist**: Complex clinical questions, specialist referrals

**Safety Gate Logic:**
- Clinical intents (medical questions, test results) → escalated to physician
- Specialist department → escalated
- High/urgent urgency → escalated
- Low confidence (< 70%) → escalated

**Awaiting Specialist Status:**
- When escalated, review enters `awaiting_specialist_input`
- UI shows "Awaiting Specialist" badge
- Specialist can view the email and provide guidance

### 4. Professional, Interactive UI

#### Dashboard Statistics
- Real-time counts by status
- Filter buttons for quick navigation

#### Status Badges
- **Pending** (blue): Ready for admin approval
- **Awaiting Specialist** (yellow): Waiting for clinical input
- **Specialist Input Received** (purple): Ready for draft revision
- **Approved** (green): Pushed to Gmail drafts
- **Sent** (gray): Delivered
- **Rejected** (red): Declined
- **Irrelevant** (slate): Out of scope

#### Interactive Review Cards
- Sender, subject, intent, urgency visible at a glance
- Department badges color-coded
- Classification level with confidence score
- Draft preview with truncation
- Specialist input shown in purple box
- Action buttons context-aware by status

#### Specialist Input Form
- Dedicated modal for providing clinical guidance
- Shows original email and current draft for context
- Optional draft regeneration toggle
- Clean, focused interface

#### Edit Interface
- Full draft editor with syntax highlighting
- Save and cancel options
- Inline editing between actions

### 5. Advanced Status Management

**New Statuses:**
- `irrelevant`: Email filtered; no action needed
- `awaiting_specialist_input`: Escalated; awaiting clinical guidance
- `specialist_input_received`: Specialist provided input; ready for draft revision
- Plus existing: `pending`, `approved`, `rejected`, `sent`

**Status Permissions:**
- Edit allowed in: `pending`, `specialist_input_received`
- Approve allowed from: `pending`, `specialist_input_received`
- Reject allowed from: `pending`, `specialist_input_received`
- Specialist input endpoint: only for `awaiting_specialist_input`

## Database Schema

**New Columns on `draft_reviews`:**
```sql
specialist_input: TEXT -- Clinical guidance from specialist
specialist_id: UUID -- Who provided the input
specialist_input_at: DATETIME -- When input was provided
```

**Migration:** Run `alembic upgrade head` to apply the 0002 migration.

## Usage Examples

### Example 1: Routine Admin Email
```
Email: "I'd like to reschedule my appointment"
→ Intent: appointment, Urgency: normal, Department: front_office
→ Status: pending (awaits admin approval)
→ Draft generated immediately
→ Admin can approve/send directly
```

### Example 2: Medical Question for Specialist
```
Email: "I've had chest pain for 3 days, should I be worried?"
→ Intent: medical_question, Urgency: high
→ Classification: NEEDS_PHYSICIAN_REVIEW
→ Status: awaiting_specialist_input
→ UI shows: "Awaiting Specialist" badge + "Provide Input" button
→ Specialist clicks button, adds guidance: "Refer to ER if sharp/persistent"
→ Status: specialist_input_received
→ System regenerates draft with specialist guidance
→ Admin reviews revised draft, approves, sends
```

### Example 3: Spam Email
```
Email: "VIAGRA FOR SALE - Best prices online!"
→ Intent: irrelevant
→ Status: irrelevant
→ No draft generated
→ UI shows: "Irrelevant email" message
→ Appears in queue for completeness but doesn't block workflows
```

## API Changes

### New Endpoint
**Submit Specialist Input:**
```http
POST /api/v1/reviews/{review_id}/specialist-input
Content-Type: application/json

{
  "specialist_input": "Patient should be referred to cardiology for EKG.",
  "should_revise_draft": true
}
```

**Response:** Updated review with `specialist_input_received` status

### Updated Endpoints
**List Reviews:**
```http
GET /api/v1/reviews?status=awaiting_specialist_input
```

Supports all statuses: `pending`, `awaiting_specialist_input`, `specialist_input_received`, `approved`, `rejected`, `sent`, `irrelevant`

**Edit Review:**
```http
PATCH /api/v1/reviews/{review_id}

{
  "draft_body": "Updated reply text"
}
```

Now also allows editing `specialist_input_received` status (not just `pending`)

**Approve/Reject:**
Both now accept reviews in `pending` OR `specialist_input_received` status

## Frontend Components

### Updated `/app/reviews/page.tsx`
- **ReviewCard Component**: Displays review with all metadata and status-aware actions
- **ActionButtons Component**: Context-aware buttons by status
- **Status Filters**: Quick navigation between statuses
- **Edit Modal**: Full-screen draft editor
- **Specialist Input Modal**: Clinical guidance interface

### Status Configuration
```typescript
const statusConfig = {
  pending: { icon: Clock, label: "Pending", color: "blue" },
  awaiting_specialist_input: { icon: Stethoscope, label: "Awaiting Specialist", color: "yellow" },
  specialist_input_received: { icon: MessageSquare, label: "Specialist Input Received", color: "purple" },
  approved: { icon: CheckCircle2, label: "Approved", color: "green" },
  rejected: { icon: XCircle, label: "Rejected", color: "red" },
  sent: { icon: Send, label: "Sent", color: "gray" },
  irrelevant: { icon: FileText, label: "Irrelevant", color: "slate" },
};
```

## Workflow Diagram

```
                     TRIAGE
                        ↓
              ┌─────────┴─────────┐
              ↓                   ↓
        IRRELEVANT        RELEVANT
          ↓                       ↓
        SKIP              SAFETY GATE
                                 ↓
                    ┌────────────┴────────────┐
                    ↓                         ↓
              ADMIN REPLY          PHYSICIAN REVIEW
                  ↓                          ↓
              PENDING            AWAITING_SPECIALIST_INPUT
                  ↓                          ↓
          [DRAFT READY]      [SPECIALIST PROVIDES INPUT]
                  ↓                          ↓
              APPROVAL             SPECIALIST_INPUT_RECEIVED
                  ↓                          ↓
              APPROVED          [DRAFT REVISED]
                  ↓                          ↓
              SEND TO GMAIL         APPROVAL
                  ↓                          ↓
              SENT                   APPROVED
                                          ↓
                                      SENT
```

## Backend Services

### WorkflowService Updates

**New Method: `receive_specialist_input()`**
- Records specialist input with timestamp
- Optionally regenerates draft with specialist guidance
- Updates status to `specialist_input_received`
- Logs action for audit trail

### TriageService Updates

**Updated Prompts:**
- Explains `irrelevant` intent with examples
- Claude trained to identify out-of-scope emails
- Maintains high accuracy on relevant classifications

### Safety Service Updates

**Classification Logic:**
```python
if intent == "irrelevant":
    return (IRRELEVANT, "email is irrelevant...")
elif clinical_intent or specialist_dept or high_urgency or low_confidence:
    return (NEEDS_PHYSICIAN_REVIEW, "reason...")
else:
    return (ADMIN_DIRECT_REPLY, "routine...")
```

## Testing Recommendations

### Unit Tests
- [ ] Irrelevant intent classification
- [ ] Specialist input API validation
- [ ] Status transition logic
- [ ] Draft regeneration with specialist guidance

### Integration Tests
- [ ] End-to-end irrelevant email workflow
- [ ] Specialist input submission and draft update
- [ ] Department routing accuracy
- [ ] Safety gate escalation triggers

### Manual Testing
- [ ] Test irrelevant email → verify skips draft generation
- [ ] Test medical question → verify awaiting_specialist_input status
- [ ] Submit specialist input → verify draft updated
- [ ] Verify UI badges display correctly for all statuses
- [ ] Test filtering by status in UI
- [ ] Test edit modal for pending and specialist_input_received

## Deployment Checklist

- [ ] Run database migration: `alembic upgrade head`
- [ ] Deploy backend changes
- [ ] Deploy frontend changes
- [ ] Test irrelevant email handling
- [ ] Test specialist input workflow
- [ ] Verify UI displays correctly
- [ ] Monitor logs for new status handling
- [ ] Confirm Gmail integration still works

## Future Enhancements

1. **Batch Specialist Assignment**: Assign multiple escalated emails to specific specialists
2. **Specialist Queue Dashboard**: Separate view for awaiting_specialist_input reviews
3. **Template Responses**: Specialist-approved templates for common issues
4. **Audit Trail**: Full history of who approved/rejected/input what
5. **Email Notifications**: Alert specialists when emails await their input
6. **Team Collaboration**: Internal notes between team members on a review
7. **Analytics**: Track specialist response times and approval rates
8. **A/B Testing**: Test irrelevant intent accuracy over time

## Configuration

No environment variables needed. The system works with existing FirstMed setup.

**Triage Confidence Threshold:** 0.70 (70%)
- Below this triggers physician review regardless of other factors
- Adjustable in `backend/app/services/safety.py`

## Support

For issues with specialist collaboration:
1. Check review status in database
2. Verify specialist_input_at timestamp
3. Review logs for workflow_service operations
4. Check triage confidence scores for false positives

---

**Commit:** feat(phase-14): specialist collaboration + irrelevant email handling
**Date:** 2026-07-21
**Phase:** 14 (Cross-Department Collaboration)
