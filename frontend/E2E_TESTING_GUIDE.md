# FirstMed E2E Testing Guide

This guide covers end-to-end workflow testing for the FirstMed AI Email Assistant. All major user journeys are documented below with steps to verify each screen works correctly according to the Interface Design Spec.

## Prerequisites

- Backend running and accessible at configured API_BASE_URL
- Gmail OAuth configured for testing
- Test user accounts created with different roles:
  - Front Office staff (can review and send)
  - Clinical Reviewer (can answer specialist questions)
  - Booking Coordinator (can manage scheduling)
  - Admin (full system access)

---

## Workflow 1: Front Office Console - Complete Review & Send

### Step 1: Login
**Expected behavior:**
- Navigate to `/login`
- User sees email/password OR Google OAuth option
- 2FA prompt appears for Admin users
- After login, redirected to `/reviews` (Front Office Console)

**Verification checklist:**
- [ ] Login form renders correctly
- [ ] Invalid credentials show generic error message (no indication of email vs password)
- [ ] Admin 2FA challenge appears and can be verified
- [ ] Role-based redirect works (Front Office → `/reviews`, Clinical → `/clinical`, etc.)

### Step 2: Front Office Console - Initial State
**Expected behavior:**
- Three-pane layout visible (queue, thread+draft, context)
- Department tabs show with dynamic counts
- Queue list shows items sorted by urgency then age
- Urgent items have AlertTriangle icon + color indicator (position + color per §7)
- SLA chips show On Time / At Risk / Overdue states

**Verification checklist:**
- [ ] Three-pane layout correct proportions (~280px / flexible / ~320px)
- [ ] Urgent items pinned to top of queue with icon AND color
- [ ] Overdue items show red border on left AND red badge
- [ ] Department tabs show accurate counts that update when queue changes
- [ ] Filter label "Filter by department:" appears above tabs
- [ ] Queue items are properly sorted (urgent first, then oldest)

### Step 3: Select a Review Item
**Expected behavior:**
- Clicking item loads it in center+right panes
- Item is highlighted in queue
- Right panel shows: sources, match confidence with explanation, routing trail, send rights
- Thread shows: sender info, patient message, draft area, action buttons
- Confidence explanation is contextual based on percentage (e.g., "≥85% = strong match")

**Verification checklist:**
- [ ] Item highlights in queue when selected
- [ ] Thread pane shows sender, subject, patient message
- [ ] Match confidence bar shows percentage
- [ ] Confidence explanation matches tier (check all 4 tiers if possible: ≥85%, 65-84%, 45-64%, <45%)
- [ ] Citation sources are clickable and traceable
- [ ] "Who Can Send" shows correct staff scope
- [ ] Routing Trail is present and accurate

### Step 4: Edit Draft (Optional)
**Expected behavior:**
- "Edit Further" button available for pending items
- Clicking opens textarea with current draft
- User can modify text
- "Save Changes" commits to backend
- "Cancel" reverts to original

**Verification checklist:**
- [ ] Edit button appears for editable statuses
- [ ] Textarea opens and shows full draft
- [ ] Save works and shows success message
- [ ] Cancel reverts without saving
- [ ] Draft updates in real-time

### Step 5: Approve & Send to Gmail
**Expected behavior:**
- "Save to Gmail Draft" button shown (not "Approve & Send")
- Clicking shows confirmation modal
- Modal explains: "creates a draft in your Gmail account"
- After confirming, shows "Draft Ready in Gmail" state
- Shows draft preview for final review
- "Send Email to Patient" button now available
- Clicking sends with success message

**Verification checklist:**
- [ ] Button text is "Save to Gmail Draft" (not "Approve & Send")
- [ ] Confirmation modal appears before saving
- [ ] After approval, dedicated "Approved" state section appears
- [ ] Draft preview shows in the approved state
- [ ] "Send Email to Patient" button is prominent and available
- [ ] Send completes with success message "Email sent successfully to patient!"
- [ ] Item moves to "sent" queue after sending

### Step 6: Specialist Handling (if available)
**If a review has status "awaiting_specialist_input":**
- Shows "Waiting on Specialist" card
- "Nudge Specialist" button available
- Question sent to specialist is visible
- Draft area shows greyed-out text: "Draft will regenerate once specialist responds"
- "Approve & Send" button is disabled

**If specialist input is received (status = "specialist_input_received"):**
- Shows specialist input in highlighted context card (CheckCircle2 icon, emerald color)
- Shows "Regenerated Draft" section with "Updated with specialist input" badge
- User can edit the regenerated draft
- All approval/send workflow available

**Verification checklist:**
- [ ] Waiting state shows specialist question and nudge button
- [ ] Regenerated draft section shows after specialist responds
- [ ] Specialist input is visible and readable
- [ ] Badge clearly marks draft as "Updated with specialist input"
- [ ] User can approve and send the regenerated draft

---

## Workflow 2: Clinical Reviewer - Answer Specialist Questions

### Step 1: Login & Navigation
**Expected behavior:**
- Login as user with CLINICAL_REVIEWER role
- Dashboard shows sidebar with only appropriate views
- Can access `/clinical` (Clinical Reviewer View)
- Cannot see Front Office Console or Admin Dashboard (menu items hidden)

**Verification checklist:**
- [ ] Sidebar only shows Clinical Reviewer option for this role
- [ ] Cannot navigate to other role pages even by URL
- [ ] 401/403 errors if attempting unauthorized access

### Step 2: Clinical Reviewer Queue
**Expected behavior:**
- Minimal list view (not full console)
- Header: "Questions needing your input"
- Each item shows: who asked, the question, SLA badge, text box, action buttons
- Count badge shows "X Pending"

**Verification checklist:**
- [ ] "Questions needing your input" header visible
- [ ] Each item shows question clearly
- [ ] Text input box for clinical answer
- [ ] SLA/timing badge visible

### Step 3: Submit Clinical Answer
**Expected behavior:**
- Type answer in text box
- Click "Send answer to Front Office"
- Shows success: "Answer submitted to Front Office"
- Item removes from list after 1.2s

**Verification checklist:**
- [ ] Answer text box is functional
- [ ] Send button works
- [ ] Success message appears
- [ ] Item disappears from list

### Step 4: Phone Call Escalation Option
**Expected behavior:**
- "Needs a phone call instead" button available for each item
- Clicking flags item for phone escalation
- Shows success message
- Item removes from list

**Verification checklist:**
- [ ] Phone call button visible
- [ ] Clicking works and removes item from view

---

## Workflow 3: Booking Coordinator - Direct Send

### Step 1: Login & Navigation
**Expected behavior:**
- Login as BOOKING_COORDINATOR
- Can access `/bookings` (Booking Coordinator View)
- Header: "Your queue"
- Can only see booking/scheduling related items

**Verification checklist:**
- [ ] "Your queue" header appears
- [ ] Only booking-related items visible
- [ ] Cannot access clinical or front office views

### Step 2: Send Booking Response
**Expected behavior:**
- Each item shows: subject, patient info, AI draft, action buttons
- User can edit draft if needed
- Clicking "Send Response" sends DIRECTLY (not to Front Office for approval)
- Shows "Response sent directly to patient!"

**Verification checklist:**
- [ ] Draft is editable
- [ ] Send button sends directly (not routed)
- [ ] Success message confirms direct send
- [ ] Item disappears from queue

---

## Workflow 4: Admin Dashboard - System Configuration

### Step 1: Login & Access
**Expected behavior:**
- Login as ADMIN
- Can access all views including Admin Dashboard
- Admin Dashboard shows all cards: Staff & Roles, Routing Rules, Audit Log, Knowledge Gaps, SLA Thresholds

**Verification checklist:**
- [ ] All admin cards visible
- [ ] Can switch between different roles in testing (but role is now read-only from backend)
- [ ] Cannot modify role via UI (no role switcher)

### Step 2: Staff Management
**Expected behavior:**
- Table shows current staff with roles and send rights
- "Add Staff Member" button opens modal
- Modal allows entering email, selecting role
- Generate invite link provided

**Verification checklist:**
- [ ] Staff table displays correctly
- [ ] Invite modal works
- [ ] Invite link generates

### Step 3: Routing Rules
**Expected behavior:**
- List shows category → target queue mappings
- "Add Routing Rule" button available
- Can add new rule without deploy

**Verification checklist:**
- [ ] Rules list displays
- [ ] Add rule modal works
- [ ] Rule persists after adding

### Step 4: SLA Threshold Configuration
**Expected behavior:**
- Shows two input fields: "At-Risk Threshold" and "Overdue Threshold" (hours)
- Defaults: 12h and 24h
- Each has explanatory text
- "Save SLA Configuration" button
- Success message appears after saving

**Verification checklist:**
- [ ] Both threshold fields present with correct defaults
- [ ] Can edit thresholds
- [ ] Save button works and shows success
- [ ] Fields have helpful explanations

### Step 5: Audit Log
**Expected behavior:**
- Chronological feed showing sends, approvals, edits, routing changes, admin actions
- Read-only view

**Verification checklist:**
- [ ] Audit log displays chronologically
- [ ] Shows various action types

---

## Workflow 5: Needs Attention Dashboard

### Step 1: Access & Initial Load
**Expected behavior:**
- Navigate to `/needs-attention`
- Three distinct sections: Knowledge Gaps, Stalled Items, Quick Triage
- Each section has its own count badge

**Verification checklist:**
- [ ] All three sections visible and separated
- [ ] Section headers clear
- [ ] Count badges accurate

### Step 2: Knowledge Gaps Section
**Expected behavior:**
- Shows topics grouped by unanswered questions
- Escalated gaps have amber background + warning label
- "Auto-escalated to [Manager]" text visible
- Occurrence counter shows how many times asked

**Verification checklist:**
- [ ] Escalated items have distinct visual indicators (amber background, ring border)
- [ ] Non-escalated items have neutral styling
- [ ] Occurrence count displays
- [ ] Manager name shows for escalated items

### Step 3: Stalled Items
**Expected behavior:**
- Shows items waiting on staff past SLA
- Badge shows "Xh / Yh SLA"
- "Who it's waiting on" clear
- "Send Nudge" or "Nudge Sent" button
- After nudging, shows success checkmark

**Verification checklist:**
- [ ] SLA timer display clear
- [ ] Nudge button works
- [ ] Success message appears
- [ ] Button changes to "Nudge Sent" after action

### Step 4: Quick Triage
**Expected behavior:**
- Low-confidence items (spam, one-word replies)
- Confidence badge color-coded (green ≥70%, amber 50-69%, red <50%)
- "Accept (Archive)" and "Send to Queue" buttons
- One-tap actions clear and fast

**Verification checklist:**
- [ ] Confidence badges color-coded correctly
- [ ] Accept button works
- [ ] Reject/Send to Queue works
- [ ] Items disappear after action

---

## Workflow 6: Cross-Cutting Verification

### §3.2 Queue Sorting
- [ ] Urgent items appear at top regardless of arrival time
- [ ] Within same urgency tier, oldest appears first
- [ ] Sorting updates when queue refreshes

### §3.3 Draft State Distinction
- [ ] Pending/editable drafts show clearly as "AI Draft — Not Sent"
- [ ] Approved drafts show in dedicated section "Draft Ready in Gmail"
- [ ] Escalated/routed items NEVER show editable draft box (hard rule)
- [ ] Specialist input received state shows regenerated draft prominently

### §3.4 Context Panel Completeness
- [ ] Sources are clickable and traceable
- [ ] Match confidence has contextual explanation (not just percentage)
- [ ] Routing trail numbered and clear
- [ ] Collaboration drawer accessible

### §5 Needs Attention Details
- [ ] Knowledge gaps auto-escalate with visual marker
- [ ] Stalled items show elapsed time and SLA comparison
- [ ] Stalled items can be nudged
- [ ] Quick triage allows fast one-tap decisions

### §7 Visual & Permission Rules
- [ ] Urgent/overdue items use BOTH position (icon) AND color (no color-alone signals)
- [ ] AI-generated drafts labeled as such everywhere they appear
- [ ] Source citations one click away
- [ ] No role-gated content renders briefly then hides (permissions checked before rendering)
- [ ] Consistent visual language across all screens (calm palette, color-coding)

---

## Smoke Testing Checklist

Run these quick checks before declaring ready:

- [ ] **Login Flow**: Can login with email/password
- [ ] **Admin 2FA**: Admin login shows 2FA challenge
- [ ] **Role Routing**: After login, redirected to correct role view
- [ ] **Queue Display**: Reviews load and display with correct counts
- [ ] **Draft Edit**: Can edit and save draft
- [ ] **Approve Flow**: Can approve and see confirmation
- [ ] **Send Flow**: Can send email with success message
- [ ] **Specialist Flow**: If available, specialist answer flow works
- [ ] **Clinical Queue**: Clinical reviewer can see and answer questions
- [ ] **Booking Queue**: Booking coordinator can send directly
- [ ] **Admin Access**: Admin can see all dashboard cards
- [ ] **SLA Config**: Admin can view and edit SLA thresholds
- [ ] **Needs Attention**: All three sections load with data
- [ ] **Error Handling**: Invalid actions show appropriate errors
- [ ] **Loading States**: Loading spinners appear and disappear correctly
- [ ] **Accessibility**: Urgent items have position + color signals
- [ ] **Mobile Responsiveness**: Three-pane layout adapts on narrow screens
- [ ] **Lazy Loading**: Only active queue and common queues load initially
- [ ] **API Optimization**: Developer tools show minimal redundant API calls
- [ ] **Backend Sync**: Refresh button updates data from backend

---

## Known Limitations & Future Work

1. **SLA Threshold Persistence**: Frontend UI is ready but backend `/admin/sla-config` endpoint needs implementation
2. **Role Switcher Removed**: Client-side role simulation has been removed for security; role now comes from backend only
3. **Real-time Updates**: Currently polling-based; consider WebSocket for live notifications
4. **Mobile Polish**: Three-pane layout works but could use more mobile-first refinements
5. **Offline Mode**: No offline support; all operations require backend connectivity

---

## Test Data Setup (if needed)

To test various workflows without hitting production:

```bash
# Create test reviews in various states
POST /api/v1/reviews/test-seed
{
  "count": 20,
  "statuses": ["pending", "awaiting_specialist_input", "specialist_input_received", "approved", "sent"],
  "departments": ["bookings", "physiotherapy", "clinical"],
  "urgencies": ["normal", "high", "urgent"]
}
```

---

## Sign-Off

- [ ] All workflows tested by Front Office user
- [ ] All workflows tested by Clinical Reviewer user
- [ ] All workflows tested by Booking Coordinator user
- [ ] All workflows tested by Admin user
- [ ] No regressions found
- [ ] Performance acceptable (API calls minimized)
- [ ] Accessibility verified (position + color signals)
- [ ] Visual consistency verified across all screens
- [ ] Error cases handled gracefully
