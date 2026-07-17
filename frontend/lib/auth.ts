/**
 * Client-side access-token storage + helpers for the Google SSO flow.
 *
 * The backend callback redirects to `/auth/callback#access_token=…&token_type=bearer`.
 * The token lives in the URL *fragment* (never sent to servers). We parse it on
 * the callback page and persist it to localStorage for subsequent API calls.
 */

import { API_BASE_URL } from "@/lib/api";

const TOKEN_KEY = "firstmed_access_token";
const RETURN_KEY = "firstmed_return_to";

export type FragmentAuth =
  | { ok: true; accessToken: string; tokenType: string }
  | { ok: false; error: string };

/** Parse `#access_token=…&token_type=…` (or `#error=…`) from a URL hash. */
export function parseAuthFragment(hash: string): FragmentAuth | null {
  const raw = hash.startsWith("#") ? hash.slice(1) : hash;
  if (!raw) return null;
  const params = new URLSearchParams(raw);

  const error = params.get("error");
  if (error) return { ok: false, error };

  const accessToken = params.get("access_token");
  if (accessToken) {
    return {
      ok: true,
      accessToken,
      tokenType: params.get("token_type") ?? "bearer",
    };
  }
  return null;
}

export function setToken(token: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function clearToken(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
}

/** Authorization header for authenticated backend calls, if signed in. */
export function authHeader(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * Start the Google SSO flow: ask the backend for the consent-screen URL and
 * redirect the browser. Optionally remember where to return after login so the
 * callback can bounce back to the page the user started from.
 */
export async function startGoogleSignIn(returnTo?: string): Promise<void> {
  if (returnTo && typeof window !== "undefined") {
    window.localStorage.setItem(RETURN_KEY, returnTo);
  }
  const res = await fetch(`${API_BASE_URL}/api/v1/auth/google/login`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`sign-in unavailable (${res.status})`);
  const { authorization_url } = (await res.json()) as { authorization_url: string };
  window.location.href = authorization_url;
}

/** Read and clear the post-login return path (defaults to "/"). */
export function takeReturnTo(): string {
  if (typeof window === "undefined") return "/";
  const dest = window.localStorage.getItem(RETURN_KEY);
  window.localStorage.removeItem(RETURN_KEY);
  return dest || "/";
}
