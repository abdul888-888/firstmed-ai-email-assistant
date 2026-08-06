import { Review } from "@/lib/api";

export interface DepartmentTab {
  id: string;
  name: string;
  count: number;
}

export interface RoutingRule {
  id: string;
  category: string;
  targetQueue: string;
  assignedStaff: string;
  autoEscalateHours: number;
}

export interface StaffMember {
  id: string;
  name: string;
  email: string;
  role: "front_office" | "clinical_reviewer" | "booking_coordinator" | "admin";
  sendRights: boolean;
  status: "active" | "invited" | "deactivated";
  department: string;
}

export interface AuditLogEntry {
  id: string;
  timestamp: string;
  actor: string;
  action: string;
  details: string;
}

export interface KnowledgeGap {
  id: string;
  topic: string;
  occurrences: number;
  sampleQuestion: string;
  escalatedToManager: boolean;
  lastAsked: string;
}

export interface StalledItem {
  id: string;
  patientName: string;
  subject: string;
  waitingOn: string;
  waitingRole: string;
  elapsedHours: number;
  autoNudged: boolean;
}

export interface QuickTriageItem {
  id: string;
  sender: string;
  subject: string;
  snippet: string;
  confidence: number;
  reason: string;
  category: "spam" | "vendor" | "one_word_reply" | "low_confidence";
}

export const INITIAL_DEPARTMENTS: DepartmentTab[] = [
  { id: "all", name: "All", count: 12 },
  { id: "pricing", name: "Pricing & Insurance", count: 3 },
  { id: "bookings", name: "Bookings", count: 4 },
  { id: "lab", name: "Lab Results", count: 2 },
  { id: "physio", name: "Physio", count: 1 },
  { id: "specialist", name: "Specialist review", count: 2 },
  { id: "billing", name: "Billing", count: 0 },
  { id: "complaints", name: "Complaints", count: 0 },
];

export const MOCK_REVIEWS_EXTENDED: (Review & {
  sla_status: "on_time" | "at_risk" | "overdue";
  sla_elapsed: string;
  is_urgent: boolean;
  template_name?: string;
  routing_trail?: { step: number; title: string; time: string }[];
  send_rights?: string[];
  notes?: { id: string; author: string; text: string; time: string }[];
})[] = [
  {
    id: "rev-001",
    gmail_message_id: "msg-101",
    gmail_thread_id: "th-101",
    sender: "Sarah Jenkins <sarah.j@example.com>",
    subject: "URGENT: Post-surgery knee pain and swelling",
    intent: "Clinical escalation regarding post-op recovery",
    urgency: "HIGH",
    department: "Physio",
    classification: "NEEDS_PHYSICIAN_REVIEW",
    confidence: 0.94,
    summary: "Patient reports severe knee swelling 3 days post knee arthroscopy with 8/10 pain.",
    reason: "Severe pain post-surgery requires specialist opinion.",
    draft_body: "",
    citations: [
      {
        document_id: "doc-88",
        source: "Post-Op Clinical Protocol v4.2",
        title: "Knee Surgery Recovery Guidelines",
        url: "https://notion.so/firstmed/post-op-protocol",
      },
    ],
    model: "gemini-2.5-flash",
    status: "awaiting_specialist_input",
    gmail_draft_id: null,
    review_note: "Assigned to Dr. Miller (Orthopedics)",
    reviewed_at: null,
    sent_at: null,
    sent_message_id: null,
    assigned_to: "Dr. Miller (Orthopedics)",
    specialist_input: null,
    specialist_id: "spec-401",
    specialist_input_at: null,
    created_at: "2026-08-06T09:15:00Z",
    sla_status: "overdue",
    sla_elapsed: "Overdue 6.5h",
    is_urgent: true,
    routing_trail: [
      { step: 1, title: "Ingested from Gmail Inbox", time: "09:15 AM" },
      { step: 2, title: "AI Classified: NEEDS_PHYSICIAN_REVIEW", time: "09:15 AM" },
      { step: 3, title: "Routed to Orthopedics (Dr. Miller)", time: "09:16 AM" },
    ],
    send_rights: ["Front Office Lead", "Dr. Miller"],
    notes: [
      { id: "n1", author: "Jane (Front Office)", text: "Nudge sent to Dr. Miller at 11:30 AM", time: "11:30 AM" },
    ],
  },
  {
    id: "rev-002",
    gmail_message_id: "msg-102",
    gmail_thread_id: "th-102",
    sender: "David Copper <d.copper@provider.org>",
    subject: "Inquiry about MRI scan pricing with Bupa Insurance",
    intent: "Pricing and insurance coverage query",
    urgency: "MEDIUM",
    department: "Pricing & Insurance",
    classification: "ADMIN_DIRECT_REPLY",
    confidence: 0.98,
    summary: "Patient asking whether Bupa Select policy covers self-pay MRI knee imaging.",
    reason: "Matched standard Bupa pricing tier in Knowledge Base.",
    draft_body:
      "Dear David,\n\nThank you for reaching out to FirstMed Clinic.\n\nYes, Bupa Select policies directly cover lower limb MRI imaging at our clinic with zero copay upon pre-authorization. Please provide your Bupa membership number and pre-auth code so we can schedule your appointment immediately.\n\nBest regards,\nFirstMed Front Office Team",
    citations: [
      {
        document_id: "doc-12",
        source: "FirstMed Fee Schedule 2026",
        title: "Bupa Insurance Coverage Rules",
        url: "https://notion.so/firstmed/bupa-schedule",
      },
    ],
    model: "gemini-2.5-flash",
    status: "pending",
    gmail_draft_id: "draft-771",
    review_note: null,
    reviewed_at: null,
    sent_at: null,
    sent_message_id: null,
    assigned_to: null,
    specialist_input: null,
    specialist_id: null,
    specialist_input_at: null,
    created_at: "2026-08-06T10:30:00Z",
    sla_status: "on_time",
    sla_elapsed: "1.2h ago",
    is_urgent: false,
    template_name: "Insurance Coverage & Co-Pay Standard Template",
    routing_trail: [
      { step: 1, title: "Ingested from Gmail Inbox", time: "10:30 AM" },
      { step: 2, title: "AI Draft Generated (Confidence 98%)", time: "10:30 AM" },
    ],
    send_rights: ["Front Office", "Booking Coordinator"],
    notes: [],
  },
  {
    id: "rev-003",
    gmail_message_id: "msg-103",
    gmail_thread_id: "th-103",
    sender: "Elena Rostova <elena.r@techcorp.io>",
    subject: "Rescheduling Physio Therapy Appointment for Friday",
    intent: "Booking rescheduling request",
    urgency: "LOW",
    department: "Bookings",
    classification: "ROUTE_TO_STAFF",
    confidence: 0.91,
    summary: "Wants to move 3:00 PM Friday session to next Monday afternoon.",
    reason: "Escalated directly to Physio Coordinator queue.",
    draft_body: "",
    citations: [],
    model: "gemini-2.5-flash",
    status: "needs_manual_handling",
    gmail_draft_id: null,
    review_note: "Routed to Booking Coordinator: No draft generated per safety rules for direct calendar bookings.",
    reviewed_at: null,
    sent_at: null,
    sent_message_id: null,
    assigned_to: "Booking Coordinator (Physio)",
    specialist_input: null,
    specialist_id: null,
    specialist_input_at: null,
    created_at: "2026-08-06T08:00:00Z",
    sla_status: "at_risk",
    sla_elapsed: "3.9h ago",
    is_urgent: false,
    routing_trail: [
      { step: 1, title: "Ingested from Inbox", time: "08:00 AM" },
      { step: 2, title: "Routed to Booking Coordinator (Physio Calendar Excluded)", time: "08:01 AM" },
    ],
    send_rights: ["Physio Booking Coordinator"],
    notes: [{ id: "n2", author: "System", text: "Routed to Physio Queue because booking changes require calendar lock.", time: "08:01 AM" }],
  },
  {
    id: "rev-004",
    gmail_message_id: "msg-104",
    gmail_thread_id: "th-104",
    sender: "Marcus Vance <mvance@healthlink.org>",
    subject: "Fast-track Blood Test Results Request",
    intent: "Lab results expedite request",
    urgency: "HIGH",
    department: "Lab Results",
    classification: "ADMIN_DIRECT_REPLY",
    confidence: 0.96,
    summary: "Patient requests urgent lab report for lipid profile before flight tomorrow.",
    reason: "Lab result verified in pathology portal.",
    draft_body:
      "Dear Marcus,\n\nYour blood test results have been expedited and verified by our pathology lab. Attached is your official PDF report.\n\nAll parameters remain within normal baseline ranges.\n\nWarm regards,\nFirstMed Lab Desk",
    citations: [
      {
        document_id: "lab-902",
        source: "Pathology Portal Sync",
        title: "Verified Blood Chemistry Panel #902",
        url: "https://notion.so/firstmed/lab-902",
      },
    ],
    model: "gemini-2.5-flash",
    status: "approved",
    gmail_draft_id: "draft-882",
    review_note: "Approved by FO Lead",
    reviewed_at: "2026-08-06T11:00:00Z",
    sent_at: null,
    sent_message_id: null,
    assigned_to: "Front Office Lead",
    specialist_input: null,
    specialist_id: null,
    specialist_input_at: null,
    created_at: "2026-08-06T10:00:00Z",
    sla_status: "on_time",
    sla_elapsed: "1.8h ago",
    is_urgent: true,
    template_name: "Lab Report Fast-Track Verification",
    routing_trail: [{ step: 1, title: "Ingested & Matched Lab Record", time: "10:00 AM" }],
    send_rights: ["Front Office Lead"],
    notes: [],
  },
];

export const MOCK_KNOWLEDGE_GAPS: KnowledgeGap[] = [
  {
    id: "gap-1",
    topic: "Travel Vaccination Certificate Validity for Yellow Fever",
    occurrences: 14,
    sampleQuestion: "Does your clinic issue international WHO yellow fever cards valid for lifetime entry?",
    escalatedToManager: true,
    lastAsked: "20 mins ago",
  },
  {
    id: "gap-2",
    topic: "Pediatric Sedation Protocols for Dental X-Rays",
    occurrences: 8,
    sampleQuestion: "Do you offer mild nitrous oxide sedation for 5-year-old child dental checkups?",
    escalatedToManager: true,
    lastAsked: "1 hour ago",
  },
  {
    id: "gap-3",
    topic: "Ambulatory ECG Monitor Deposit Refund Methods",
    occurrences: 4,
    sampleQuestion: "How long does the 50 GBP device deposit take to credit back after returning the Holter monitor?",
    escalatedToManager: false,
    lastAsked: "3 hours ago",
  },
];

export const MOCK_STALLED_ITEMS: StalledItem[] = [
  {
    id: "stall-1",
    patientName: "Sarah Jenkins",
    subject: "Post-surgery knee pain and swelling",
    waitingOn: "Dr. Miller (Orthopedics)",
    waitingRole: "Clinical Reviewer",
    elapsedHours: 6.5,
    autoNudged: true,
  },
  {
    id: "stall-2",
    patientName: "Robert Vance",
    subject: "Custom Orthotic shoe fitting confirmation",
    waitingOn: "Claire Redfield",
    waitingRole: "Booking Coordinator",
    elapsedHours: 4.2,
    autoNudged: false,
  },
];

export const MOCK_QUICK_TRIAGE: QuickTriageItem[] = [
  {
    id: "triage-1",
    sender: "sales@medequip-direct.co.uk",
    subject: "Exclusive Discount on Disposable Syringes and Gloves!",
    snippet: "Dear Practice Manager, save 40% on bulk medical supplies this month...",
    confidence: 0.12,
    reason: "Unsolicited vendor marketing email",
    category: "vendor",
  },
  {
    id: "triage-2",
    sender: "john.doe@gmail.com",
    subject: "Re: Appointment Confirmation",
    snippet: "Thanks!",
    confidence: 0.25,
    reason: "One-word reply to closed automated confirmation",
    category: "one_word_reply",
  },
  {
    id: "triage-3",
    sender: "lottery-win@crypto-health.biz",
    subject: "Claim your 1,000 GBP health voucher now",
    snippet: "Click here to verify your identity and claim your prize...",
    confidence: 0.05,
    reason: "Malicious spam filter trigger",
    category: "spam",
  },
];

export const MOCK_STAFF: StaffMember[] = [
  {
    id: "usr-1",
    name: "Dr. Alex Vance",
    email: "alex.vance@firstmed.org",
    role: "admin",
    sendRights: true,
    status: "active",
    department: "Executive Management",
  },
  {
    id: "usr-2",
    name: "Jane Smith",
    email: "jane.smith@firstmed.org",
    role: "front_office",
    sendRights: true,
    status: "active",
    department: "Front Office Desk",
  },
  {
    id: "usr-3",
    name: "Dr. Miller",
    email: "dr.miller@firstmed.org",
    role: "clinical_reviewer",
    sendRights: false,
    status: "active",
    department: "Orthopedics & Clinical",
  },
  {
    id: "usr-4",
    name: "Claire Redfield",
    email: "claire.r@firstmed.org",
    role: "booking_coordinator",
    sendRights: true,
    status: "active",
    department: "Physio & Booking",
  },
  {
    id: "usr-5",
    name: "Dr. Rachel Green",
    email: "rachel.green@firstmed.org",
    role: "clinical_reviewer",
    sendRights: false,
    status: "invited",
    department: "Lab & Pathology",
  },
];

export const MOCK_ROUTING_RULES: RoutingRule[] = [
  {
    id: "rule-1",
    category: "Pricing & Insurance",
    targetQueue: "Front Office Console",
    assignedStaff: "Jane Smith",
    autoEscalateHours: 4,
  },
  {
    id: "rule-2",
    category: "Post-op Clinical & Symptoms",
    targetQueue: "Clinical Reviewer Queue",
    assignedStaff: "Dr. Miller",
    autoEscalateHours: 2,
  },
  {
    id: "rule-3",
    category: "Physio & Procedure Rescheduling",
    targetQueue: "Booking Coordinator Queue",
    assignedStaff: "Claire Redfield",
    autoEscalateHours: 3,
  },
  {
    id: "rule-4",
    category: "Lab & Pathology Verification",
    targetQueue: "Lab Specialist Queue",
    assignedStaff: "Dr. Rachel Green",
    autoEscalateHours: 4,
  },
];

export const MOCK_AUDIT_LOGS: AuditLogEntry[] = [
  {
    id: "aud-1",
    timestamp: "2026-08-06 11:45 AM",
    actor: "Jane Smith (Front Office)",
    action: "APPROVED & SENT",
    details: "Sent response to David Copper regarding Bupa Insurance coverage (rev-002)",
  },
  {
    id: "aud-2",
    timestamp: "2026-08-06 11:30 AM",
    actor: "Jane Smith (Front Office)",
    action: "NUDGED SPECIALIST",
    details: "Sent reminder nudge to Dr. Miller for post-op inquiry (rev-001)",
  },
  {
    id: "aud-3",
    timestamp: "2026-08-06 10:15 AM",
    actor: "Dr. Alex Vance (Admin)",
    action: "RULE UPDATED",
    details: "Updated auto-escalation threshold for Post-op Clinical category to 2 hours",
  },
  {
    id: "aud-4",
    timestamp: "2026-08-06 09:30 AM",
    actor: "Dr. Alex Vance (Admin)",
    action: "INVITED STAFF",
    details: "Sent invitation email to Dr. Rachel Green (Lab Reviewer)",
  },
];
