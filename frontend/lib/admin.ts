/**
 * Phase 11 internal collaboration API: assigning reviews to staff and
 * attaching internal notes. Mirrors the fetch-wrapper convention used by the
 * reviews page (`app/reviews/page.tsx`).
 */

import { API_BASE_URL } from "@/lib/api";
import { authHeader } from "@/lib/auth";

const base = `${API_BASE_URL}/api/v1/admin`;

async function api(path: string, init?: RequestInit) {
  const res = await fetch(`${base}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...authHeader(), ...(init?.headers ?? {}) },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail ?? `Request failed (${res.status})`);
  return data;
}

export type TeamMember = {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
};

export type ReviewNote = {
  id: string;
  review_id: string;
  author_id: string;
  body: string;
  created_at: string;
};

/** Active staff eligible to be assigned a review. */
export async function listTeamMembers(): Promise<TeamMember[]> {
  const data = await api("/users");
  return data.users ?? [];
}

/** Assign a review to `assignedTo`, or clear the assignment when `null`. */
export async function assignReview(reviewId: string, assignedTo: string | null) {
  return api(`/reviews/${reviewId}/assign`, {
    method: "PATCH",
    body: JSON.stringify({ assigned_to: assignedTo }),
  });
}

export async function listReviewNotes(reviewId: string): Promise<ReviewNote[]> {
  const data = await api(`/reviews/${reviewId}/notes`);
  return data.notes ?? [];
}

export async function addReviewNote(reviewId: string, body: string): Promise<ReviewNote> {
  return api(`/reviews/${reviewId}/notes`, {
    method: "POST",
    body: JSON.stringify({ body }),
  });
}
