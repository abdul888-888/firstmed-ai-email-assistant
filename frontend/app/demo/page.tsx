"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Activity,
  AlertTriangle,
  BookOpen,
  Inbox,
  Loader2,
  Mail,
  Sparkles,
  Stethoscope,
  UserRound,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  type AnalyzeResult,
  type Citation,
  DEPARTMENT,
  INTENT_LABEL,
  PRESETS,
  prettify,
  urgency,
} from "@/lib/demo";
import { cn } from "@/lib/utils";

export default function DemoPage() {
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [active, setActive] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AnalyzeResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [runId, setRunId] = useState(0);

  function loadPreset(id: string) {
    const preset = PRESETS.find((p) => p.id === id);
    if (!preset) return;
    setActive(id);
    setSubject(preset.subject);
    setBody(preset.body);
    setResult(null);
    setError(null);
  }

  async function run() {
    if (!body.trim() || loading) return;
    setLoading(true);
    setResult(null);
    setError(null);
    try {
      const res = await fetch("/api/demo/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subject, body }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error ?? "Analysis failed");
      setResult(data as AnalyzeResult);
      setRunId((n) => n + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  const canRun = body.trim().length > 0 && !loading;

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-white text-slate-900">
      {/* Header */}
      <header className="sticky top-0 z-10 border-b border-slate-200/70 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3.5">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-blue-600 to-blue-700 shadow-sm">
              <Stethoscope className="h-5 w-5 text-white" />
            </div>
            <div className="leading-tight">
              <p className="text-sm font-semibold">FirstMed</p>
              <p className="text-xs text-slate-500">AI Email Assistant</p>
            </div>
          </div>
          <div className="flex items-center gap-4 text-sm">
            <Link href="/" className="text-slate-500 transition-colors hover:text-slate-900">
              Home
            </Link>
            <a
              href="http://localhost:8000/docs"
              target="_blank"
              rel="noreferrer"
              className="text-slate-500 transition-colors hover:text-slate-900"
            >
              API Docs
            </a>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-8">
        <div className="mb-6">
          <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700">
            <Activity className="h-3.5 w-3.5" />
            Demo Playground · Phases 1–5 MVP
          </div>
          <h1 className="text-3xl font-bold tracking-tight">AI Triage &amp; Draft Generation</h1>
          <p className="mt-1.5 max-w-2xl text-slate-500">
            Paste a patient email (or load a sample) and watch the assistant classify it, route it,
            and prepare a grounded reply — with citations, and always for human review.
          </p>
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          {/* ── Left: input ─────────────────────────────── */}
          <Card className="h-fit">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Inbox className="h-4 w-4 text-blue-600" />
                Patient Email Inbox
              </CardTitle>
              <CardDescription>Load a sample scenario or write your own.</CardDescription>
            </CardHeader>
            <CardContent>
              {/* Presets */}
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">
                Load a sample
              </p>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                {PRESETS.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => loadPreset(p.id)}
                    className={cn(
                      "rounded-lg border bg-white p-3 text-left transition-all",
                      p.accent,
                      active === p.id
                        ? "border-blue-400 ring-2 ring-blue-500/20"
                        : "border-slate-200",
                    )}
                  >
                    <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-slate-700">
                      <span aria-hidden>{p.emoji}</span>
                      {p.label}
                    </div>
                    <div className="text-xs leading-snug text-slate-500">{p.title}</div>
                  </button>
                ))}
              </div>

              {/* Divider */}
              <div className="my-5 border-t border-slate-100" />

              {/* Compose */}
              <p className="mb-3 text-xs font-medium uppercase tracking-wide text-slate-400">
                Compose
              </p>
              <div className="flex flex-col gap-4">
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-medium text-slate-600" htmlFor="subject">
                    Subject
                  </label>
                  <input
                    id="subject"
                    type="text"
                    value={subject}
                    onChange={(e) => setSubject(e.target.value)}
                    placeholder="e.g. Prescription refill request"
                    className="block w-full rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm transition-colors placeholder:text-slate-400 focus-visible:border-blue-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/40"
                  />
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-medium text-slate-600" htmlFor="body">
                    Email body
                  </label>
                  <Textarea
                    id="body"
                    value={body}
                    onChange={(e) => setBody(e.target.value)}
                    placeholder="Paste the patient's email here…"
                  />
                </div>

                <Button
                  type="button"
                  onClick={run}
                  disabled={!canRun}
                  className="mt-1 w-full bg-blue-600 text-white shadow-sm hover:bg-blue-700"
                  size="lg"
                >
                  {loading ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Analyzing…
                    </>
                  ) : (
                    <>
                      <Sparkles className="h-4 w-4" />
                      Run AI Analysis
                    </>
                  )}
                </Button>

                <p className="text-center text-xs text-slate-400">
                  Calls <code className="text-slate-500">/ai/triage</code> +{" "}
                  <code className="text-slate-500">/ai/draft</code> · falls back to demo data if the
                  backend is offline.
                </p>
              </div>
            </CardContent>
          </Card>

          {/* ── Right: output ───────────────────────────── */}
          <div className="space-y-4">
            {loading && <LoadingState />}
            {!loading && error && <ErrorState message={error} />}
            {!loading && !error && !result && <EmptyState />}
            {!loading && !error && result && (
              <div key={runId} className="space-y-4 duration-500 animate-in fade-in">
                <ModePill mode={result.mode} model={result.draft.model} />
                <TriageCard triage={result.triage} />
                <DraftCard draft={result.draft} />
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

/* ── Result subcomponents ──────────────────────────────── */

function ModePill({ mode, model }: { mode: string; model: string }) {
  const live = mode === "live";
  return (
    <div
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
        live
          ? "border-emerald-200 bg-emerald-50 text-emerald-700"
          : "border-amber-200 bg-amber-50 text-amber-700",
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", live ? "bg-emerald-500" : "bg-amber-500")} />
      {live ? `Live AI · ${model}` : "Demo data (backend offline)"}
    </div>
  );
}

function TriageCard({ triage }: { triage: AnalyzeResult["triage"] }) {
  const u = urgency(triage.urgency);
  const pct = Math.round((triage.confidence ?? 0) * 100);
  return (
    <Card className="duration-500 animate-in fade-in slide-in-from-bottom-2">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-blue-600" />
          Triage
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-2">
          <Badge className={u.badge}>
            <span className={cn("h-1.5 w-1.5 rounded-full", u.dot)} />
            {u.label} priority
          </Badge>
          <Badge className="border-blue-200 bg-blue-50 text-blue-700">
            <UserRound className="h-3.5 w-3.5" />
            {prettify(DEPARTMENT, triage.department)}
          </Badge>
          <Badge>{prettify(INTENT_LABEL, triage.intent)}</Badge>
        </div>

        <div className="rounded-lg bg-slate-50 p-3.5 text-sm leading-relaxed text-slate-700">
          {triage.summary}
        </div>

        <ConfidenceBar value={triage.confidence ?? 0} pct={pct} />
      </CardContent>
    </Card>
  );
}

function ConfidenceBar({ value, pct }: { value: number; pct: number }) {
  const [w, setW] = useState(0);
  useEffect(() => {
    const id = requestAnimationFrame(() => setW(pct));
    return () => cancelAnimationFrame(id);
  }, [pct]);
  const color = pct >= 80 ? "bg-emerald-500" : pct >= 55 ? "bg-amber-500" : "bg-red-500";
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between text-xs">
        <span className="font-medium text-slate-500">Confidence</span>
        <span className="font-semibold text-slate-900">{pct}%</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
        <div
          className={cn("h-full rounded-full transition-all duration-700 ease-out", color)}
          style={{ width: `${w}%` }}
        />
      </div>
    </div>
  );
}

function DraftCard({ draft }: { draft: AnalyzeResult["draft"] }) {
  return (
    <Card className="duration-500 animate-in fade-in slide-in-from-bottom-2">
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2">
          <Mail className="h-4 w-4 text-blue-600" />
          Suggested draft reply
        </CardTitle>
        <Badge className="border-amber-200 bg-amber-50 text-amber-700">
          <AlertTriangle className="h-3.5 w-3.5" />
          Review required
        </Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="whitespace-pre-line rounded-lg border border-slate-200 bg-white p-4 text-sm leading-relaxed text-slate-800 shadow-inner">
          {draft.draft}
        </div>

        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">
            Grounded on
          </p>
          {draft.citations.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {draft.citations.map((c) => (
                <SourceTag key={c.document_id} citation={c} />
              ))}
            </div>
          ) : (
            <p className="text-xs text-slate-400">
              No indexed sources yet — connect Notion / Gmail and run{" "}
              <code>/search/reindex</code> to ground drafts on clinic knowledge.
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function SourceTag({ citation }: { citation: Citation }) {
  const isNotion = citation.source === "notion";
  const Icon = isNotion ? BookOpen : Mail;
  const label = isNotion ? "Notion" : citation.source === "gmail" ? "Gmail" : citation.source;
  const inner = (
    <span className="inline-flex max-w-full items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-600 transition-colors hover:border-slate-300 hover:bg-white">
      <Icon className="h-3.5 w-3.5 shrink-0 text-slate-400" />
      <span className="font-medium text-slate-500">{label}</span>
      <span className="text-slate-300">·</span>
      <span className="truncate">{citation.title}</span>
    </span>
  );
  return citation.url ? (
    <a href={citation.url} target="_blank" rel="noreferrer" className="max-w-full">
      {inner}
    </a>
  ) : (
    inner
  );
}

/* ── States ────────────────────────────────────────────── */

function EmptyState() {
  return (
    <Card className="border-dashed">
      <CardContent className="flex flex-col items-center justify-center gap-3 py-16 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-100">
          <Sparkles className="h-6 w-6 text-slate-400" />
        </div>
        <div>
          <p className="font-medium text-slate-700">No analysis yet</p>
          <p className="mt-1 text-sm text-slate-500">
            Load a sample email and click <span className="font-medium">Run AI Analysis</span>.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <Card className="border-red-200 bg-red-50/50">
      <CardContent className="flex items-start gap-3 py-6">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-red-500" />
        <div>
          <p className="font-medium text-red-700">Couldn&apos;t run the analysis</p>
          <p className="mt-1 text-sm text-red-600/80">{message}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function LoadingState() {
  return (
    <>
      <Skeleton className="h-6 w-40 rounded-full" />
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-24" />
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-2">
            <Skeleton className="h-6 w-28 rounded-full" />
            <Skeleton className="h-6 w-28 rounded-full" />
            <Skeleton className="h-6 w-24 rounded-full" />
          </div>
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-2 w-full rounded-full" />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-40" />
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-6 w-52" />
        </CardContent>
      </Card>
    </>
  );
}
