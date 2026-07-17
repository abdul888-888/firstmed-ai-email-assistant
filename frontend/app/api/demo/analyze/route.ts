import { NextResponse } from "next/server";

import { API_BASE_URL } from "@/lib/api";

export const dynamic = "force-dynamic";

// Server-side only: the demo user's credentials never reach the browser.
const BACKEND = process.env.BACKEND_INTERNAL_URL || API_BASE_URL;
const DEMO_EMAIL = process.env.DEMO_EMAIL || "demo@firstmed.com";
const DEMO_PASSWORD = process.env.DEMO_PASSWORD || "supersecret1";

const TIMEOUT_AUTH = 5000;
const TIMEOUT_AI = 90000;

type EmailInput = { subject: string; body: string };

async function login(): Promise<string | null> {
  const form = new URLSearchParams({ username: DEMO_EMAIL, password: DEMO_PASSWORD });
  const res = await fetch(`${BACKEND}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: form,
    cache: "no-store",
    signal: AbortSignal.timeout(TIMEOUT_AUTH),
  });
  if (res.ok) return (await res.json()).access_token as string;
  return null;
}

async function getToken(): Promise<string | null> {
  // Try to log in; if the demo user doesn't exist yet, provision it once.
  let token = await login();
  if (token) return token;

  await fetch(`${BACKEND}/api/v1/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: DEMO_EMAIL,
      password: DEMO_PASSWORD,
      full_name: "Demo Staff",
      role: "front_office",
    }),
    cache: "no-store",
    signal: AbortSignal.timeout(TIMEOUT_AUTH),
  }).catch(() => {});

  token = await login();
  return token;
}

/** Keyword-driven mock so the demo never fails when the backend/keys are absent. */
function mockAnalyze({ subject, body }: EmailInput): { triage: unknown; draft: unknown } {
  const t = `${subject} ${body}`.toLowerCase();

  if (/fever|swelling|severe|post-?op|bleeding|chest pain|infection|emergency|worse/.test(t)) {
    return {
      triage: {
        intent: "medical_question",
        urgency: "urgent",
        department: "specialist",
        summary:
          "Possible post-operative complication (fever and swelling) that needs prompt clinical review.",
        confidence: 0.94,
        requires_human_review: true,
      },
      draft: {
        model: "demo-mock",
        requires_human_review: true,
        draft:
          "Thank you for reaching out, and I'm sorry you're feeling this way. Because you're describing a fever and significant swelling after surgery, this needs prompt clinical attention — I'm escalating your message to our nursing team now and someone will contact you shortly. If your symptoms worsen (high or rising fever, spreading redness, difficulty breathing, or severe pain), please seek emergency care right away.\n\nThe FirstMed Team",
        citations: [
          {
            document_id: "mock-notion-1",
            source: "notion",
            title: "Post-Operative Care & Red-Flag Symptoms SOP",
            url: null,
          },
          {
            document_id: "mock-gmail-1",
            source: "gmail",
            title: "Prior escalation — post-op infection triage",
            url: null,
          },
        ],
      },
    };
  }

  if (/refill|prescription|medication|lisinopril|blood pressure|pharmacy|meds/.test(t)) {
    return {
      triage: {
        intent: "prescription_refill",
        urgency: "normal",
        department: "nurse",
        summary: "Patient is requesting a refill of their blood pressure medication.",
        confidence: 0.91,
        requires_human_review: true,
      },
      draft: {
        model: "demo-mock",
        requires_human_review: true,
        draft:
          "Thank you for your message. I've forwarded your blood pressure medication refill request to our nursing team for review. Refill requests are typically processed within 48 hours, and we'll confirm once it has been sent to your pharmacy. If you need it sooner or have any questions, just let us know.\n\nThe FirstMed Team",
        citations: [
          {
            document_id: "mock-notion-2",
            source: "notion",
            title: "Prescription Refill SOP",
            url: null,
          },
        ],
      },
    };
  }

  return {
    triage: {
      intent: "billing_insurance",
      urgency: "low",
      department: "front_office",
      summary: "General administrative question about billing hours and parking validation.",
      confidence: 0.88,
      requires_human_review: true,
    },
    draft: {
      model: "demo-mock",
      requires_human_review: true,
      draft:
        "Thanks for reaching out! Our billing office is open Monday–Friday, 9:00am–5:00pm, and we're happy to help with any billing questions. We also validate parking at the front desk during your visit — just bring your ticket with you. Please let us know if there's anything else we can help with.\n\nThe FirstMed Team",
      citations: [
        {
          document_id: "mock-notion-3",
          source: "notion",
          title: "Clinic Hours & Parking FAQ",
          url: null,
        },
      ],
    },
  };
}

export async function POST(req: Request) {
  let payload: EmailInput;
  try {
    const json = await req.json();
    payload = { subject: String(json.subject ?? ""), body: String(json.body ?? "") };
  } catch {
    return NextResponse.json({ error: "invalid request body" }, { status: 400 });
  }

  if (!payload.body.trim()) {
    return NextResponse.json({ error: "email body is required" }, { status: 400 });
  }

  try {
    const token = await getToken();
    if (!token) throw new Error("could not authenticate demo user");
    const auth = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };

    const [triageRes, draftRes] = await Promise.all([
      fetch(`${BACKEND}/api/v1/ai/triage`, {
        method: "POST",
        headers: auth,
        body: JSON.stringify(payload),
        cache: "no-store",
        signal: AbortSignal.timeout(TIMEOUT_AI),
      }),
      fetch(`${BACKEND}/api/v1/ai/draft`, {
        method: "POST",
        headers: auth,
        body: JSON.stringify({ ...payload, use_context: true }),
        cache: "no-store",
        signal: AbortSignal.timeout(TIMEOUT_AI),
      }),
    ]);

    if (!triageRes.ok || !draftRes.ok) {
      throw new Error(`backend responded ${triageRes.status}/${draftRes.status}`);
    }

    return NextResponse.json({
      mode: "live",
      triage: await triageRes.json(),
      draft: await draftRes.json(),
    });
  } catch (err) {
    // Graceful fallback — the demo always renders something sensible.
    return NextResponse.json({
      mode: "mock",
      note: err instanceof Error ? err.message : "backend unavailable",
      ...mockAnalyze(payload),
    });
  }
}
