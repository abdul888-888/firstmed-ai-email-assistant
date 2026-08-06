/**
 * Backend API layer.
 *
 * Every outbound request to the FastAPI backend goes through `apiFetch`, which
 * injects `Authorization: Bearer <token>` (from the custom Google-SSO JWT stored
 * in localStorage), sets JSON headers, and normalises errors into `ApiError`.
 *
 * NOTE: this app does NOT use NextAuth. Auth is a custom Google SSO flow whose
 * JWT lives in localStorage (see `lib/auth.ts`). `apiFetch` reads that token.
 */

import { authHeader, clearToken } from "@/lib/auth";

/**
 * Backend API base URL. Injected at build/runtime via NEXT_PUBLIC_API_BASE_URL
 * (see .env.example). Falls back to the local backend port.
 */
const rawUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  "http://localhost:8000";

export const API_BASE_URL = rawUrl.replace(/\/+$/, "");

/** Versioned API prefix — every backend router lives under this. */
export const API_V1 = `${API_BASE_URL}/api/v1`;

/** Backend liveness endpoint (Phase 1). */
export const BACKEND_HEALTH_URL = `${API_V1}/health`;

/** Typed error carrying the HTTP status so callers can branch on 401/409/etc. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }

  get isUnauthorized(): boolean {
    return this.status === 401;
  }
}

type ApiFetchInit = RequestInit & {
  /** Path relative to the /api/v1 prefix, e.g. "/reviews". */
  path: string;
};

/**
 * Core authenticated fetch. Prepends the /api/v1 prefix, attaches the bearer
 * token + JSON headers, and turns non-2xx responses into `ApiError`. On 401 it
 * clears the stale token so the UI can re-trigger sign-in.
 */
export async function apiFetch<T = unknown>({
  path,
  headers,
  ...init
}: ApiFetchInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_V1}${path}`, {
      ...init,
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        ...authHeader(),
        ...headers,
      },
    });
  } catch (err) {
    // Network / CORS failure — surface as a 0-status ApiError rather than a
    // raw TypeError so callers can render a friendly "backend unreachable".
    throw new ApiError(
      err instanceof Error ? err.message : "Network request failed",
      0,
    );
  }

  if (res.status === 401) {
    clearToken();
    throw new ApiError("Your session has expired. Please sign in again.", 401);
  }

  // Some endpoints (e.g. 204) have no JSON body.
  const text = await res.text();
  const body = text ? safeJson(text) : null;

  if (!res.ok) {
    const detail =
      (body && typeof body === "object" && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : null) ?? `Request failed (HTTP ${res.status})`;
    throw new ApiError(detail, res.status);
  }

  return body as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text };
  }
}

/* --------------------------------------------------------------------------
 * Domain types (mirror backend app/schemas/review.py)
 * ----------------------------------------------------------------------- */

export type ReviewClassification =
  | "ADMIN_DIRECT_REPLY"
  | "NEEDS_PHYSICIAN_REVIEW"
  | "ROUTE_TO_STAFF"
  | "IRRELEVANT";

export type ReviewStatus =
  | "pending"
  | "awaiting_specialist_input"
  | "specialist_input_received"
  | "approved"
  | "rejected"
  | "sent"
  | "irrelevant"
  | "needs_manual_handling";

export type ReviewCitation = {
  document_id: string;
  source: string;
  title: string;
  url: string | null;
};

export type Review = {
  id: string;
  gmail_message_id: string;
  gmail_thread_id: string;
  sender: string;
  subject: string;
  intent: string;
  urgency: string;
  department: string;
  classification: ReviewClassification;
  confidence: number;
  summary: string;
  reason: string;
  draft_body: string;
  citations: ReviewCitation[];
  model: string;
  status: ReviewStatus;
  gmail_draft_id: string | null;
  review_note: string | null;
  reviewed_at: string | null;
  sent_at: string | null;
  sent_message_id: string | null;
  assigned_to: string | null;
  specialist_input: string | null;
  specialist_id: string | null;
  specialist_input_at: string | null;
  created_at: string;
};

export type ReviewList = { reviews: Review[]; count: number };

export type PullResult = {
  scanned?: number;
  created?: number;
  skipped?: number;
  failed?: number;
  [k: string]: unknown;
};

/** Mirrors Celery's task states for the background Gmail pull. */
export type PullTaskState = "PENDING" | "STARTED" | "RETRY" | "SUCCESS" | "FAILURE";

export type PullTaskEnqueued = { task_id: string; status: string };

export type PullTaskStatus = {
  task_id: string;
  state: PullTaskState;
  result?: PullResult;
  error?: string;
};

export type IndexStats = { total: number; gmail: number; notion: number };

/* --------------------------------------------------------------------------
 * Endpoint helpers
 * ----------------------------------------------------------------------- */

/** List reviews for a single status (backend defaults to `pending`). */
export function listReviews(status: ReviewStatus, limit = 100): Promise<ReviewList> {
  return apiFetch<ReviewList>({
    path: `/reviews?status=${status}&limit=${limit}`,
  });
}

export function getReview(id: string): Promise<Review> {
  return apiFetch<Review>({ path: `/reviews/${id}` });
}

export function editDraft(id: string, draft_body: string): Promise<Review> {
  return apiFetch<Review>({
    path: `/reviews/${id}`,
    method: "PATCH",
    body: JSON.stringify({ draft_body }),
  });
}

export function approveReview(id: string): Promise<Review> {
  return apiFetch<Review>({ path: `/reviews/${id}/approve`, method: "POST" });
}

export function rejectReview(id: string, reason: string): Promise<Review> {
  return apiFetch<Review>({
    path: `/reviews/${id}/reject`,
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export function sendReview(id: string): Promise<Review> {
  return apiFetch<Review>({ path: `/reviews/${id}/send`, method: "POST" });
}

export function submitSpecialistInput(
  id: string,
  specialist_input: string,
  should_revise_draft: boolean,
): Promise<Review> {
  return apiFetch<Review>({
    path: `/reviews/${id}/specialist-input`,
    method: "POST",
    body: JSON.stringify({ specialist_input, should_revise_draft }),
  });
}

/**
 * One-click Gmail ingest → triage → pending reviews, run synchronously in the
 * request (blocks until done). Superseded by `pullGmailAsync` for the "Sync
 * Inbox" button (see `use-gmail-sync.ts`); kept for direct/scripted use.
 */
export function pullGmail(maxResults = 12): Promise<PullResult> {
  return apiFetch<PullResult>({
    path: `/workflows/pull?max_results=${maxResults}`,
    method: "POST",
  });
}

/**
 * Enqueue the same ingest → triage pipeline on a Celery worker instead of
 * blocking the request — returns immediately with a task id to poll via
 * `getPullGmailStatus`. THE Gmail sync action (see `use-gmail-sync.ts`).
 * Requires a Celery worker to be running; otherwise the task just sits queued
 * until one picks it up (the polling hook surfaces this as a timeout).
 */
export function pullGmailAsync(maxResults = 12): Promise<PullTaskEnqueued> {
  return apiFetch<PullTaskEnqueued>({
    path: `/workflows/pull-async?max_results=${maxResults}`,
    method: "POST",
  });
}

/** Poll the status/result of a background Gmail pull started by `pullGmailAsync`. */
export function getPullGmailStatus(taskId: string): Promise<PullTaskStatus> {
  return apiFetch<PullTaskStatus>({ path: `/workflows/pull-async/${taskId}` });
}

export function getIndexStats(): Promise<IndexStats> {
  return apiFetch<IndexStats>({ path: `/search/stats` });
}

/* --------------------------------------------------------------------------
 * Auth & 2FA (§2 Login)
 * ----------------------------------------------------------------------- */

export type LoginResponse = {
  access_token: string;
  token_type: string;
  requires_2fa: boolean;
  challenge_id?: string | null;
  role?: string | null;
  redirect_url?: string | null;
};

export async function loginWithEmailPassword(email: string, password: string): Promise<LoginResponse> {
  const formData = new URLSearchParams();
  formData.append("username", email);
  formData.append("password", password);

  const res = await fetch(`${API_V1}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: formData.toString(),
  });

  const body = await res.json().catch(() => ({ detail: "Login failed" }));
  if (!res.ok) throw new ApiError(body?.detail || "Invalid email or password", res.status);
  return body as LoginResponse;
}

export function verify2FACode(challengeId: string, code: string): Promise<LoginResponse> {
  return apiFetch<LoginResponse>({
    path: `/auth/2fa/verify`,
    method: "POST",
    body: JSON.stringify({ challenge_id: challengeId, code }),
  });
}

export function setInvitePassword(token: string, password: string): Promise<LoginResponse> {
  return apiFetch<LoginResponse>({
    path: `/auth/invite/set-password`,
    method: "POST",
    body: JSON.stringify({ token, password }),
  });
}

/* --------------------------------------------------------------------------
 * Needs Attention Dashboard (§5)
 * ----------------------------------------------------------------------- */

export type KnowledgeGap = {
  id: string;
  topic: string;
  occurrences: number;
  escalated: boolean;
  escalated_to: string | null;
  last_asked: string;
};

export type StalledItem = {
  id: string;
  sender: string;
  subject: string;
  waiting_on: string;
  elapsed_hours: number;
  sla_limit_hours: number;
  nudge_sent: boolean;
  status: string;
};

export type TriageItem = {
  id: string;
  sender: string;
  subject: string;
  summary: string;
  confidence: number;
  suggested_action: "archive" | "queue";
};

export function getKnowledgeGaps(): Promise<{ gaps: KnowledgeGap[]; count: number }> {
  return apiFetch<{ gaps: KnowledgeGap[]; count: number }>({ path: `/workflows/knowledge-gaps` });
}

export function getStalledItems(): Promise<{ stalled: StalledItem[]; count: number }> {
  return apiFetch<{ stalled: StalledItem[]; count: number }>({ path: `/workflows/stalled-items` });
}

export function sendNudge(reviewId: string): Promise<{ success: boolean; message: string }> {
  return apiFetch<{ success: boolean; message: string }>({
    path: `/workflows/nudge/${reviewId}`,
    method: "POST",
  });
}

export function getTriageItems(): Promise<{ items: TriageItem[]; count: number }> {
  return apiFetch<{ items: TriageItem[]; count: number }>({ path: `/workflows/triage-items` });
}

export function performTriageAction(itemId: string, action: "accept" | "reject"): Promise<{ success: boolean }> {
  return apiFetch<{ success: boolean }>({
    path: `/workflows/triage-action`,
    method: "POST",
    body: JSON.stringify({ item_id: itemId, action }),
  });
}

