# Quick Start: Using the New Collaboration Features

## Dashboard Overview

The new review dashboard is organized by status. Each email shows:

- **Status Badge**: Current stage (Pending, Awaiting Specialist, etc.)
- **Department Badge**: Assigned team (Front Office, Nurse, Specialist)
- **Email Details**: From, subject, intent, urgency
- **AI Confidence**: How sure the AI is about the classification
- **Summary**: One-line AI summary of the email
- **Draft Preview**: What the AI proposes to reply
- **Action Buttons**: Status-specific options

## Using the Status Filter

Click status buttons at the top to view emails by category:

- **All**: View every email (with counts)
- **Pending**: Routine admin emails ready for approval
- **Awaiting Specialist**: Medical emails needing clinical review
- **Specialist Input Received**: Awaiting final approval after specialist guidance
- **Approved**: Pushed to Gmail drafts (not yet sent)
- **Sent**: Delivered to patients
- **Rejected**: Declined by staff
- **Irrelevant**: Out-of-scope (no action needed)

## Workflow: Routine Admin Email

Example: "Can I reschedule my appointment?"

1. Email appears in **Pending** status (blue badge)
2. Review the AI-generated draft
3. Edit if needed (click "Edit" button)
4. Click **Approve** → draft sent to Gmail (not yet delivered)
5. Manually send from Gmail when ready

## Workflow: Medical Question Requiring Specialist

Example: "I have chest pain, is this serious?"

1. Email appears as **Awaiting Specialist** (yellow badge)
2. Specialist on staff clicks **"Provide Input"** button
3. Specialist enters clinical guidance, e.g.:
   ```
   Patient describes acute chest pain. Recommend immediate ER referral
   for cardiac workup. This is not something we can safely address via email.
   ```
4. System regenerates draft incorporating specialist guidance
5. Status changes to **Specialist Input Received** (purple badge)
6. Admin reviews the revised draft
7. Admin clicks **Approve** → draft sent to Gmail
8. Admin manually sends when ready

## Workflow: Irrelevant Email

Example: "BUY VIAGRA NOW" or "Wrong recipient"

1. Email appears as **Irrelevant** (slate badge)
2. Shows message: "This email was marked as irrelevant"
3. **No action buttons** - this email is automatically handled
4. No draft was generated
5. You can view it for completeness but don't need to respond

## Editing a Draft

Both before and after specialist input:

1. Click **"Edit"** button on any Pending or Specialist Input Received email
2. Modal opens with full draft text
3. Make your changes
4. Click **"Save Draft"** to persist
5. You can now approve or edit again

## Status-Specific Actions

### Pending
- **Edit**: Change the draft text
- **Approve**: Push draft to Gmail (not sent yet)
- **Reject**: Decline with optional reason

### Awaiting Specialist
- **Provide Input**: Specialists enter clinical guidance
  - System can auto-regenerate draft with guidance
  - Draft available for staff approval

### Specialist Input Received
- **Review & Edit Draft**: See the revised draft from specialist guidance
- **Approve**: Push to Gmail
- **Reject**: Decline the approach

### Approved
- **Send**: Deliver to patient via Gmail

## Tips & Best Practices

### For Admin Staff
1. **Start with Pending**: These are lowest priority, all routine
2. **Check Awaiting Specialist**: See if any need your action
3. **Batch approvals**: Review several drafts before approving
4. **Use Edit sparingly**: Let AI draft be a starting point
5. **Always review before sending**: Never approve without reading

### For Specialists
1. **Check Awaiting Specialist regularly**: New cases may be waiting
2. **Be specific**: Instead of "approve the draft," provide actionable guidance
3. **Consider liability**: Always err on side of escalation for serious issues
4. **Keep notes brief**: 2-3 sentences usually enough
5. **Re-check draft after edit**: Make sure the system incorporated your guidance correctly

### For Team Coordination
1. **Use status filters to distribute work**: Assign Specialists to Awaiting list
2. **Check Rejected regularly**: Reason shown in status
3. **Monitor Irrelevant**: Should be mostly spam (if too many, triage might have issues)
4. **Weekly reviews**: Check Approved/Sent for quality assurance

## Keyboard Shortcuts (Coming Soon)

- `F` - Focus search
- `R` - Load fresh emails
- `E` - Edit selected draft
- `A` - Approve selected
- `X` - Reject selected

## Common Issues

**"Email disappeared?"**
→ Filter changed or email was sent. Check "Sent" status.

**"Edit button missing?"**
→ Only available for Pending or Specialist Input Received. Approved emails need to be unapproved first.

**"Specialist input didn't update draft?"**
→ Check if "should_revise_draft" was toggled. You can manually edit the draft after.

**"Too many irrelevant emails?"**
→ Triage might need refinement. Note which ones are being marked incorrectly.

**"Email needs urgent response?"**
→ High urgency emails go to Awaiting Specialist automatically for fast routing.

## Setting Expectations

### What the System Does Well
✅ Routine appointment requests
✅ Billing inquiries
✅ Prescription refill requests
✅ Identifying medical questions that need specialist review
✅ Finding spam/irrelevant emails

### What Requires Caution
⚠️ Complex medical situations (always escalate)
⚠️ Complaints or upset patients (always review personally)
⚠️ New or unusual request types (verify with supervisor)
⚠️ Legal/liability concerns (default to escalation)

## Getting Help

1. **Check this guide**: Most answers are here
2. **Ask your team lead**: For process questions
3. **Review the Implementation Guide**: For technical details
4. **Check logs**: For system errors

---

**Remember:** The AI is a tool to speed up response, not replace judgment. Always review before sending.

Last Updated: 2026-07-21
