"use client";

import { useEffect, useState } from "react";

import { clearToken, getToken, startGoogleSignIn } from "@/lib/auth";
import { Button } from "@/components/ui/button";

/**
 * Sign-in / sign-out controls for the Google SSO flow. Starts the flow by
 * asking the backend for the consent-screen URL, then redirects the browser.
 */
export function AuthControls() {
  const [signedIn, setSignedIn] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSignedIn(getToken() !== null);
  }, []);

  async function signIn() {
    setBusy(true);
    setError(null);
    try {
      // Land users straight in the app after Google sign-in, not back here.
      await startGoogleSignIn("/reviews");
    } catch (err) {
      setError(err instanceof Error ? err.message : "sign-in failed");
      setBusy(false);
    }
  }

  function signOut() {
    clearToken();
    setSignedIn(false);
  }

  if (signedIn) {
    return (
      <div className="flex items-center gap-3">
        <span className="text-sm text-muted-foreground">Signed in</span>
        <Button variant="outline" onClick={signOut}>
          Sign out
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-start gap-2">
      <Button onClick={signIn} disabled={busy}>
        {busy ? "Redirecting…" : "Sign in with Google"}
      </Button>
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}
