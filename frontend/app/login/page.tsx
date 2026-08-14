"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { KeyRound, Loader2, Lock, Mail, ShieldCheck, Stethoscope } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { loginWithEmailPassword, setInvitePassword, verify2FACode } from "@/lib/api";
import { setToken } from "@/lib/auth";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const inviteToken = searchParams.get("invite_token");
  const inviteEmail = searchParams.get("email") || "";

  const [isInviteFlow, setIsInviteFlow] = useState(Boolean(inviteToken));
  const [email, setEmail] = useState(inviteEmail);
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  // 2FA state
  const [requires2FA, setRequires2FA] = useState(false);
  const [challengeId, setChallengeId] = useState<string | null>(null);
  const [twoFactorCode, setTwoFactorCode] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (inviteToken) setIsInviteFlow(true);
  }, [inviteToken]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      if (isInviteFlow && inviteToken) {
        if (password.length < 8) {
          setError("Password must be at least 8 characters");
          setLoading(false);
          return;
        }
        if (password !== confirmPassword) {
          setError("Passwords do not match");
          setLoading(false);
          return;
        }
        const res = await setInvitePassword(inviteToken, password);
        setToken(res.access_token);
        router.push(res.redirect_url || "/reviews");
        return;
      }

      const res = await loginWithEmailPassword(email, password);
      if (res.requires_2fa && res.challenge_id) {
        setRequires2FA(true);
        setChallengeId(res.challenge_id);
        setLoading(false);
        return;
      }

      setToken(res.access_token);
      router.push(res.redirect_url || "/reviews");
    } catch (err) {
      // Generic error as required by §2 (standard security practice)
      setError("Invalid email or password.");
    } finally {
      setLoading(false);
    }
  };

  const handle2FAVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!challengeId || twoFactorCode.length !== 6) {
      setError("Please enter a valid 6-digit code.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await verify2FACode(challengeId, twoFactorCode);
      setToken(res.access_token);
      router.push(res.redirect_url || "/reviews");
    } catch (err) {
      setError("Invalid 2FA code. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-12">
      <div className="w-full max-w-md space-y-6">
        {/* Header Branding */}
        <div className="flex flex-col items-center text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-900 shadow-lg">
            <Stethoscope className="h-6 w-6 text-emerald-400" />
          </div>
          <h1 className="mt-4 text-2xl font-bold tracking-tight text-slate-900">FirstMed Assistant</h1>
          <p className="mt-1 text-sm text-slate-500">Clinical Inbox & AI Review Console</p>
        </div>

        <Card className="border-slate-200 shadow-xl">
          <CardHeader>
            <CardTitle>{requires2FA ? "Admin 2FA Verification" : isInviteFlow ? "Set Your Password" : "Log In"}</CardTitle>
            <CardDescription>
              {requires2FA
                ? "Enter the 6-digit verification code sent to your authenticator app."
                : isInviteFlow
                ? "Set a secure password for your invited staff account."
                : "Enter your clinic credentials to access your primary workspace."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {error && <div className="mb-4 rounded-md bg-rose-50 p-3 text-sm font-medium text-rose-700">{error}</div>}

            {requires2FA ? (
              <form onSubmit={handle2FAVerify} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="2fa-code">Verification Code</Label>
                  <div className="relative">
                    <KeyRound className="absolute left-3 top-3 h-4 w-4 text-slate-400" />
                    <Input
                      id="2fa-code"
                      type="text"
                      maxLength={6}
                      placeholder="123456"
                      value={twoFactorCode}
                      onChange={(e) => setTwoFactorCode(e.target.value)}
                      className="pl-9 text-center text-lg tracking-widest"
                      required
                      autoFocus
                    />
                  </div>
                </div>
                <Button type="submit" disabled={loading || twoFactorCode.length !== 6} className="w-full bg-emerald-600 hover:bg-emerald-700">
                  {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4 mr-2" />}
                  Verify & Log In
                </Button>
              </form>
            ) : (
              <form onSubmit={handleLogin} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="email">Email address</Label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-3 h-4 w-4 text-slate-400" />
                    <Input
                      id="email"
                      type="email"
                      placeholder="staff@firstmed.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="pl-9"
                      required
                      disabled={isInviteFlow && Boolean(inviteEmail)}
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="password">{isInviteFlow ? "New Password" : "Password"}</Label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-3 h-4 w-4 text-slate-400" />
                    <Input
                      id="password"
                      type="password"
                      placeholder="••••••••"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="pl-9"
                      required
                    />
                  </div>
                </div>

                {isInviteFlow && (
                  <div className="space-y-2">
                    <Label htmlFor="confirm-password">Confirm Password</Label>
                    <div className="relative">
                      <Lock className="absolute left-3 top-3 h-4 w-4 text-slate-400" />
                      <Input
                        id="confirm-password"
                        type="password"
                        placeholder="••••••••"
                        value={confirmPassword}
                        onChange={(e) => setConfirmPassword(e.target.value)}
                        className="pl-9"
                        required
                      />
                    </div>
                  </div>
                )}

                <Button type="submit" disabled={loading} className="w-full bg-slate-900 hover:bg-slate-800">
                  {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : isInviteFlow ? "Set Password & Enter" : "Log In"}
                </Button>

                {!isInviteFlow && (
                  <>
                    <div className="relative my-4">
                      <div className="absolute inset-0 flex items-center">
                        <span className="w-full border-t border-slate-200" />
                      </div>
                      <div className="relative flex justify-center text-xs uppercase">
                        <span className="bg-white px-2 text-slate-500">Or continue with</span>
                      </div>
                    </div>

                    <Button
                      type="button"
                      variant="outline"
                      className="w-full border-slate-300 text-slate-700 hover:bg-slate-50"
                      onClick={async () => {
                        try {
                          const res = await fetch("https://api-production-c575.up.railway.app/api/v1/auth/google/login");
                          const data = await res.json();
                          if (data.authorization_url) {
                            window.location.href = data.authorization_url;
                          }
                        } catch (e) {
                          console.error("SSO failed", e);
                        }
                      }}
                    >
                      <svg className="mr-2 h-4 w-4" viewBox="0 0 24 24">
                        <path
                          fill="currentColor"
                          d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                        />
                        <path
                          fill="currentColor"
                          d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                        />
                        <path
                          fill="currentColor"
                          d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
                        />
                        <path
                          fill="currentColor"
                          d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
                        />
                      </svg>
                      Sign in with Google SSO
                    </Button>
                  </>
                )}
              </form>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="flex min-h-screen items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>}>
      <LoginForm />
    </Suspense>
  );
}
