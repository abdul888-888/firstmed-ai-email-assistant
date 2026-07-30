/**
 * Phase 12 analytics API: triage volume, response time, and the
 * approve-rate accuracy proxy computed by the backend.
 */

import { API_BASE_URL } from "@/lib/api";
import { authHeader } from "@/lib/auth";

const base = `${API_BASE_URL}/api/v1/analytics`;

async function api(path: string, init?: RequestInit) {
  const res = await fetch(`${base}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...authHeader(), ...(init?.headers ?? {}) },
  });
  const data = await res.json().catch(() => ({}));
  // Always surface the status in the message so callers can detect 401 (the
  // backend's 401 body is "Could not validate credentials", with no code).
  if (!res.ok) throw new Error(`${data?.detail ?? "Request failed"} (${res.status})`);
  return data;
}

export type AnalyticsSummary = {
  total_processed: number;
  counts_by_status: Record<string, number>;
  counts_by_department: Record<string, number>;
  decided_count: number;
  rejected_count: number;
  triage_accuracy_rate: number | null;
  avg_decision_seconds: number | null;
  avg_turnaround_seconds: number | null;
};

/** `sinceDays` omitted (or 0) means all-time. */
export async function getAnalyticsSummary(sinceDays?: number): Promise<AnalyticsSummary> {
  const qs = sinceDays ? `?since_days=${sinceDays}` : "";
  return api(`/summary${qs}`);
}
