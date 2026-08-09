"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { parseAuthFragment, setToken, takeReturnTo, authHeader } from "@/lib/auth";
import { API_BASE_URL } from "@/lib/api";

type Status =
  | { kind: "working" }
  | { kind: "success" }
  | { kind: "error"; message: string };

/**
 * Google OAuth landing page. The backend redirects here with the access token
 * in the URL fragment; we store it and bounce to the appropriate dashboard.
 * On error (e.g. the user denied consent) we surface the reason instead.
 */
export default function AuthCallbackPage() {
  const router = useRouter();
  const [status, setStatus] = useState<Status>({ kind: "working" });

  useEffect(() => {
    async function handleCallback() {
      try {
        const result = parseAuthFragment(window.location.hash);

        if (result === null) {
          setStatus({ kind: "error", message: "No sign-in details were returned." });
          return;
        }
        if (!result.ok) {
          setStatus({ kind: "error", message: `Google sign-in failed: ${result.error}` });
          return;
        }

        setToken(result.accessToken);
        
        // Get user info to determine correct dashboard redirect
        try {
          const userRes = await fetch(`${API_BASE_URL}/api/v1/auth/me`, {
            headers: { Authorization: `Bearer ${result.accessToken}` }
          });
          
          let redirectPath = "/";
          if (userRes.ok) {
            const user = await userRes.json();
            const role = user.role?.toUpperCase();
            
            // Role-based redirects matching backend logic
            if (role === "ADMIN") {
              redirectPath = "/admin";
            } else if (role === "FRONT_OFFICE") {
              redirectPath = "/reviews";
            } else if (role === "BOOKING_COORDINATOR" || role === "BOOKINGS") {
              redirectPath = "/bookings";
            } else {
              redirectPath = "/clinical";
            }
          } else {
            // Fallback to stored return path if user fetch fails
            redirectPath = takeReturnTo();
          }
          
          setStatus({ kind: "success" });

          // Remove the token from the address bar, then redirect
          window.history.replaceState(null, "", window.location.pathname);
          const timer = window.setTimeout(() => router.replace(redirectPath), 600);
          return () => window.clearTimeout(timer);
        } catch (apiError) {
          console.warn("Failed to get user info, using fallback redirect:", apiError);
          const fallbackPath = takeReturnTo();
          setStatus({ kind: "success" });
          window.history.replaceState(null, "", window.location.pathname);
          const timer = window.setTimeout(() => router.replace(fallbackPath), 600);
          return () => window.clearTimeout(timer);
        }
      } catch (error) {
        console.error("Auth callback error:", error);
        setStatus({
          kind: "error",
          message: `An error occurred: ${error instanceof Error ? error.message : "Unknown error"}`
        });
      }
    }

    handleCallback();
  }, [router]);

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-4 px-6 text-center">
      {status.kind === "working" && (
        <p className="text-muted-foreground">Completing sign-in…</p>
      )}
      {status.kind === "success" && (
        <p className="text-foreground">Signed in. Redirecting…</p>
      )}
      {status.kind === "error" && (
        <div className="space-y-3">
          <p className="text-destructive">{status.message}</p>
          <Link
            href="/"
            className="text-sm text-primary underline-offset-4 hover:underline"
          >
            Back to home
          </Link>
        </div>
      )}
    </main>
  );
}
