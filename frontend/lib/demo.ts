/** Shared types, presets, and display maps for the Demo Playground. */

export type Triage = {
  intent: string;
  urgency: string;
  department: string;
  summary: string;
  confidence: number;
  requires_human_review: boolean;
};

export type Citation = {
  document_id: string;
  source: string;
  title: string;
  url: string | null;
};

export type Draft = {
  draft: string;
  model: string;
  citations: Citation[];
  requires_human_review: boolean;
};

export type AnalyzeResult = {
  mode: "live" | "mock";
  triage: Triage;
  draft: Draft;
  note?: string;
};

export type Preset = {
  id: string;
  emoji: string;
  label: string;
  title: string;
  subject: string;
  body: string;
  accent: string; // tailwind ring/border tint on the button
};

export const PRESETS: Preset[] = [
  {
    id: "urgent",
    emoji: "🔴",
    label: "Urgent",
    title: "Post-op fever & swelling",
    subject: "Severe swelling and fever after knee surgery",
    body: "Hi, I had knee replacement surgery three days ago and now I have a fever of 101.5°F with severe swelling around the incision. The area is red and warm to the touch and it seems to be getting worse. Should I be worried?",
    accent: "hover:border-red-300 hover:bg-red-50",
  },
  {
    id: "routine",
    emoji: "🟡",
    label: "Routine",
    title: "Prescription refill",
    subject: "Blood pressure prescription refill",
    body: "Hello, I'm running low on my blood pressure medication (lisinopril) and would like to request a refill. My pharmacy is the CVS on Main Street. Thank you!",
    accent: "hover:border-amber-300 hover:bg-amber-50",
  },
  {
    id: "info",
    emoji: "🟢",
    label: "Billing / Info",
    title: "Parking & billing hours",
    subject: "Question about parking validation and billing hours",
    body: "Hi there, I have an appointment next week and wanted to ask two quick things: do you validate parking, and what hours is your billing office open in case I need to sort out a payment? Thanks!",
    accent: "hover:border-emerald-300 hover:bg-emerald-50",
  },
];

/** Urgency → visual tier (red = High, amber = Routine/Medium, green = Low). */
export const URGENCY: Record<
  string,
  { label: string; badge: string; dot: string }
> = {
  urgent: {
    label: "Urgent",
    badge: "bg-red-50 text-red-700 border-red-200",
    dot: "bg-red-500",
  },
  high: {
    label: "High",
    badge: "bg-red-50 text-red-700 border-red-200",
    dot: "bg-red-500",
  },
  normal: {
    label: "Routine",
    badge: "bg-amber-50 text-amber-700 border-amber-200",
    dot: "bg-amber-500",
  },
  low: {
    label: "Low",
    badge: "bg-emerald-50 text-emerald-700 border-emerald-200",
    dot: "bg-emerald-500",
  },
};

export function urgency(u: string) {
  return URGENCY[u] ?? URGENCY.normal;
}

export const DEPARTMENT: Record<string, string> = {
  front_office: "Front Office",
  nurse: "Nurse Station",
  specialist: "Specialist",
};

export const INTENT_LABEL: Record<string, string> = {
  appointment: "Appointment",
  prescription_refill: "Prescription Refill",
  billing_insurance: "Billing / Insurance",
  medical_question: "Medical Question",
  test_results: "Test Results",
  referral: "Referral",
  complaint: "Complaint",
  other: "Other",
};

export function prettify(map: Record<string, string>, key: string) {
  return map[key] ?? key.replace(/_/g, " ");
}
