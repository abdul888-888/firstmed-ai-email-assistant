"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { parseAuthFragment, setToken, takeReturnTo } from "@/lib/auth";

type Status =
  | { kind: "working" }
  | { kind: "success" }
  | { kind: "error"; message: string };

/**
 * Google OAuth landing page. The backend redirects here with the access token
 * in the URL fragment; we store it and bounce to the home page. On error
 * (e.g. the user denied consent) we surface the reason instead.
 */
export default function AuthCallbackPage() {
  const router = useRouter();
  const [status, setStatus] = useState<Status>({ kind: "working" });

  useEffect(() => {
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
      setStatus({ kind: "success" });

      // Remove the token from the address bar, then continue to wherever the
      // user started the sign-in from (defaults to home).
      window.history.replaceState(null, "", window.location.pathname);
      const dest = takeReturnTo();
      const timer = window.setTimeout(() => router.replace(dest), 600);
      return () => window.clearTimeout(timer);
    } catch (error) {
      console.error("Auth callback error:", error);
      setStatus({
        kind: "error",
        message: `An error occurred: ${error instanceof Error ? error.message : "Unknown error"}`
      });
    }
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
