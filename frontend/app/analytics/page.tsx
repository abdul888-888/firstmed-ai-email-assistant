"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  BarChart3,
  Clock,
  Inbox,
  Loader2,
  ShieldAlert,
  ShieldCheck,
  Stethoscope,
  Timer,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { type AnalyticsSummary, getAnalyticsSummary } from "@/lib/analytics";
import { getToken, startGoogleSignIn } from "@/lib/auth";
import { cn } from "@/lib/utils";

const RANGES = [
  { label: "7 days", days: 7 },
  { label: "30 days", days: 30 },
  { label: "All time", days: undefined },
] as const;

function formatDuration(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const remMinutes = minutes % 60;
  return remMinutes ? `${hours}h ${remMinutes}m` : `${hours}h`;
}

function formatPercent(rate: number | null): string {
  return rate === null ? "—" : `${Math.round(rate * 100)}%`;
}

export default function AnalyticsPage() {
  const [rangeDays, setRangeDays] = useState<number | undefined>(30);
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [signedIn, setSignedIn] = useState(true);

  const load = useCallback(async (days: number | undefined) => {
    if (!getToken()) {
      setSignedIn(false);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setSummary(await getAnalyticsSummary(days));
    } catch (e) {
      if (e instanceof Error && e.message.includes("401")) setSignedIn(false);
      else setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(rangeDays);
  }, [load, rangeDays]);

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-white text-slate-900">
      <header className="sticky top-0 z-10 border-b border-slate-200/70 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-3.5">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-blue-600 to-blue-700 shadow-sm">
              <Stethoscope className="h-5 w-5 text-white" />
            </div>
            <div className="leading-tight">
              <p className="text-sm font-semibold">FirstMed</p>
              <p className="text-xs text-slate-500">Analytics</p>
            </div>
          </div>
          <nav className="flex items-center gap-4 text-sm text-slate-500">
            <Link href="/reviews" className="transition-colors hover:text-slate-900">
              Reviews
            </Link>
            <Link href="/" className="transition-colors hover:text-slate-900">
              Home
            </Link>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-8">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Analytics</h1>
            <p className="mt-1.5 max-w-2xl text-slate-500">
              Triage volume, response time, and a proxy for triage accuracy across all staff.
            </p>
          </div>
          {signedIn && (
            <div className="flex items-center gap-2">
              <div className="flex rounded-lg border border-slate-200 bg-white p-0.5 shadow-sm">
                {RANGES.map((r) => (
                  <button
                    key={r.label}
                    onClick={() => setRangeDays(r.days)}
                    className={cn(
                      "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                      rangeDays === r.days
                        ? "bg-blue-600 text-white"
                        : "text-slate-600 hover:bg-slate-100",
                    )}
                  >
                    {r.label}
                  </button>
                ))}
              </div>
              <Button variant="outline" onClick={() => void load(rangeDays)} disabled={loading}>
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Refresh"}
              </Button>
            </div>
          )}
        </div>

        {error && (
          <div className="mb-4 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <AlertTriangle className="h-4 w-4" />
            {error}
          </div>
        )}

        {!signedIn ? (
          <SignInState onError={setError} />
        ) : loading ? (
          <LoadingState />
        ) : summary ? (
          <div className="space-y-6">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <StatTile
                icon={<Inbox className="h-4 w-4" />}
                label="Total processed"
                value={String(summary.total_processed)}
              />
              <StatTile
                icon={<ShieldCheck className="h-4 w-4" />}
                label="Triage accuracy (proxy)"
                value={formatPercent(summary.triage_accuracy_rate)}
                hint={`${summary.decided_count - summary.rejected_count}/${summary.decided_count} decided drafts not rejected`}
              />
              <StatTile
                icon={<Clock className="h-4 w-4" />}
                label="Avg. decision time"
                value={formatDuration(summary.avg_decision_seconds)}
                hint="Email received → approved/rejected"
              />
              <StatTile
                icon={<Timer className="h-4 w-4" />}
                label="Avg. turnaround"
                value={formatDuration(summary.avg_turnaround_seconds)}
                hint="Email received → sent"
              />
            </div>

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <BreakdownCard title="By status" counts={summary.counts_by_status} />
              <BreakdownCard title="By department" counts={summary.counts_by_department} />
            </div>

            <p className="flex items-center gap-1.5 text-xs text-slate-400">
              <ShieldAlert className="h-3.5 w-3.5" />
              Triage accuracy is an approximation — a rejected draft is treated as a signal the
              AI&apos;s triage needed a human correction. There is no ground-truth correction
              field to compare against directly.
            </p>
          </div>
        ) : null}
      </main>
    </div>
  );
}

function StatTile({
  icon,
  label,
  value,
  hint,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <Card>
      <CardContent className="space-y-1.5 py-5">
        <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-slate-400">
          {icon}
          {label}
        </div>
        <p className="text-2xl font-bold tracking-tight">{value}</p>
        {hint && <p className="text-xs text-slate-400">{hint}</p>}
      </CardContent>
    </Card>
  );
}

function BreakdownCard({ title, counts }: { title: string; counts: Record<string, number> }) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, n]) => n));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <BarChart3 className="h-4 w-4 text-blue-600" />
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {entries.length === 0 ? (
          <p className="text-sm text-slate-400">No data yet.</p>
        ) : (
          entries.map(([key, count]) => (
            <div key={key}>
              <div className="mb-1 flex items-center justify-between text-xs">
                <Badge className="capitalize">{key.replace(/_/g, " ")}</Badge>
                <span className="font-medium text-slate-600">{count}</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                <div
                  className="h-full rounded-full bg-blue-500"
                  style={{ width: `${(count / max) * 100}%` }}
                />
              </div>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

function SignInState({ onError }: { onError: (m: string) => void }) {
  const [busy, setBusy] = useState(false);
  return (
    <Card className="border-dashed">
      <CardContent className="flex flex-col items-center justify-center gap-3 py-16 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-100">
          <ShieldAlert className="h-6 w-6 text-slate-400" />
        </div>
        <div>
          <p className="font-medium text-slate-700">Sign in to view analytics</p>
          <p className="mt-1 text-sm text-slate-500">
            Sign in with your clinic Google account to see triage stats.
          </p>
        </div>
        <Button
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await startGoogleSignIn("/analytics");
            } catch (e) {
              onError(e instanceof Error ? e.message : "sign-in failed");
              setBusy(false);
            }
          }}
          className="bg-blue-600 text-white hover:bg-blue-700"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Sign in with Google"}
        </Button>
      </CardContent>
    </Card>
  );
}

function LoadingState() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Card key={i}>
            <CardContent className="space-y-2 py-5">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-7 w-16" />
            </CardContent>
          </Card>
        ))}
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {[0, 1].map((i) => (
          <Card key={i}>
            <CardHeader>
              <Skeleton className="h-5 w-32" />
            </CardHeader>
            <CardContent className="space-y-3">
              <Skeleton className="h-2 w-full rounded-full" />
              <Skeleton className="h-2 w-full rounded-full" />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
