"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  Loader2,
  Mail,
  Send,
  ShieldAlert,
  ShieldCheck,
  Stethoscope,
  UserRound,
  XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { API_BASE_URL } from "@/lib/api";
import { authHeader, getToken, startGoogleSignIn } from "@/lib/auth";
import { cn } from "@/lib/utils";

type Citation = { document_id: string; source: string; title: string; url: string | null };

type Review = {
  id: string;
  sender: string;
  subject: string;
  intent: string;
  urgency: string;
  department: string;
  classification: "ADMIN_DIRECT_REPLY" | "NEEDS_PHYSICIAN_REVIEW";
  confidence: number;
  reason: string;
  draft_body: string;
  citations: Citation[];
  status: string;
  gmail_draft_id: string | null;
};

type Template = {
  id: string;
  key: string;
  title: string;
  category: string;
  body: string;
};

const base = `${API_BASE_URL}/api/v1/reviews`;

async function api(path: string, init?: RequestInit) {
  const res = await fetch(`${base}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...authHeader(), ...(init?.headers ?? {}) },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail ?? `Request failed (${res.status})`);
  return data;
}

export default function ReviewsPage() {
  const [pending, setPending] = useState<Review[]>([]);
  const [approved, setApproved] = useState<Review[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [signedIn, setSignedIn] = useState(true);
  const [toast, setToast] = useState<string | null>(null);

  const flash = (m: string) => {
    setToast(m);
    setTimeout(() => setToast(null), 5000);
  };

  const load = useCallback(async () => {
    if (!getToken()) {
      setSignedIn(false);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [p, a] = await Promise.all([
        api("/pending"),
        api("?status=approved"),
      ]);
      setPending(p.reviews ?? []);
      setApproved(a.reviews ?? []);
      // Canned-response templates for the draft editor (best-effort).
      const t = await fetch(`${API_BASE_URL}/api/v1/templates`, { headers: { ...authHeader() } });
      if (t.ok) setTemplates((await t.json()).templates ?? []);
    } catch (e) {
      if (e instanceof Error && e.message.includes("401")) setSignedIn(false);
      else setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function saveEdit(id: string, body: string) {
    const updated = (await api(`/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ draft_body: body }),
    })) as Review;
    setPending((rs) => rs.map((r) => (r.id === id ? { ...r, draft_body: updated.draft_body } : r)));
    flash("Draft saved.");
  }

  async function approve(id: string, body: string) {
    const current = pending.find((r) => r.id === id);
    if (current && body !== current.draft_body) {
      await api(`/${id}`, { method: "PATCH", body: JSON.stringify({ draft_body: body }) });
    }
    const updated = (await api(`/${id}/approve`, { method: "POST" })) as Review;
    setPending((rs) => rs.filter((r) => r.id !== id));
    setApproved((rs) => [updated, ...rs]);
    flash("Approved — draft is in Gmail Drafts. Send it when ready.");
  }

  async function reject(id: string) {
    const reason = window.prompt("Reason for rejecting this draft?") ?? "";
    if (reason === null) return;
    await api(`/${id}/reject`, { method: "POST", body: JSON.stringify({ reason }) });
    setPending((rs) => rs.filter((r) => r.id !== id));
    flash("Rejected.");
  }

  async function send(id: string) {
    if (!window.confirm("Send this reply to the patient now? This delivers a real email.")) return;
    await api(`/${id}/send`, { method: "POST" });
    setApproved((rs) => rs.filter((r) => r.id !== id));
    flash("Sent ✓ The reply was delivered.");
  }

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
              <p className="text-xs text-slate-500">Review Dashboard</p>
            </div>
          </div>
          <Link href="/" className="text-sm text-slate-500 transition-colors hover:text-slate-900">
            Home
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Review queue</h1>
            <p className="mt-1.5 max-w-2xl text-slate-500">
              Edit, approve, reject, and send AI-prepared drafts. Approving puts a draft in Gmail;
              sending is a separate, explicit step.
            </p>
          </div>
          {signedIn && (
            <Button variant="outline" onClick={() => void load()} disabled={loading}>
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Refresh"}
            </Button>
          )}
        </div>

        {toast && (
          <div className="mb-4 flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
            <CheckCircle2 className="h-4 w-4" />
            {toast}
          </div>
        )}
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
        ) : (
          <div className="space-y-8">
            <Section title="Awaiting approval" count={pending.length}>
              {pending.length === 0 ? (
                <EmptyRow text="No drafts awaiting approval." />
              ) : (
                pending.map((r) => (
                  <PendingCard
                    key={r.id}
                    review={r}
                    templates={templates}
                    onSave={(body) => saveEdit(r.id, body)}
                    onApprove={(body) => approve(r.id, body)}
                    onReject={() => reject(r.id)}
                  />
                ))
              )}
            </Section>

            <Section title="Approved — ready to send" count={approved.length}>
              {approved.length === 0 ? (
                <EmptyRow text="Nothing approved yet." />
              ) : (
                approved.map((r) => (
                  <ApprovedCard key={r.id} review={r} onSend={() => send(r.id)} />
                ))
              )}
            </Section>
          </div>
        )}
      </main>
    </div>
  );
}

/* ── Cards ─────────────────────────────────────────── */

function ClassificationBadge({ review }: { review: Review }) {
  const needsReview = review.classification === "NEEDS_PHYSICIAN_REVIEW";
  return (
    <Badge
      className={cn(
        "shrink-0",
        needsReview
          ? "border-amber-200 bg-amber-50 text-amber-700"
          : "border-emerald-200 bg-emerald-50 text-emerald-700",
      )}
    >
      {needsReview ? <ShieldAlert className="h-3.5 w-3.5" /> : <ShieldCheck className="h-3.5 w-3.5" />}
      {needsReview ? "Needs physician review" : "Admin direct reply"}
    </Badge>
  );
}

function MetaRow({ review }: { review: Review }) {
  const pct = Math.round((review.confidence ?? 0) * 100);
  const confColor = pct >= 80 ? "bg-emerald-500" : pct >= 55 ? "bg-amber-500" : "bg-red-500";
  return (
    <>
      <div className="flex flex-wrap gap-2">
        <Badge className="border-blue-200 bg-blue-50 text-blue-700">
          <UserRound className="h-3.5 w-3.5" />
          {review.department}
        </Badge>
        <Badge>{review.intent}</Badge>
        <Badge>{review.urgency} priority</Badge>
      </div>
      <div>
        <div className="mb-1.5 flex items-center justify-between text-xs">
          <span className="font-medium text-slate-500">Confidence</span>
          <span className="font-semibold text-slate-900">{pct}%</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
          <div className={cn("h-full rounded-full", confColor)} style={{ width: `${pct}%` }} />
        </div>
        <p className="mt-2 text-xs italic text-slate-500">{review.reason}</p>
      </div>
    </>
  );
}

function CardHead({ review }: { review: Review }) {
  return (
    <CardHeader className="flex-row items-start justify-between gap-4">
      <div className="min-w-0">
        <CardTitle className="flex items-center gap-2 text-base">
          <Mail className="h-4 w-4 shrink-0 text-blue-600" />
          <span className="truncate">{review.subject || "(no subject)"}</span>
        </CardTitle>
        <p className="mt-1 truncate text-sm text-slate-500">from {review.sender}</p>
      </div>
      <ClassificationBadge review={review} />
    </CardHeader>
  );
}

function PendingCard({
  review,
  templates,
  onSave,
  onApprove,
  onReject,
}: {
  review: Review;
  templates: Template[];
  onSave: (body: string) => Promise<void>;
  onApprove: (body: string) => Promise<void>;
  onReject: () => Promise<void>;
}) {
  const [body, setBody] = useState(review.draft_body);
  const [busy, setBusy] = useState<null | "save" | "approve" | "reject">(null);
  const dirty = body !== review.draft_body;

  function insertTemplate(id: string) {
    const tpl = templates.find((t) => t.id === id);
    if (!tpl) return;
    setBody((b) => (b.trimEnd() ? `${b.trimEnd()}\n\n${tpl.body}` : tpl.body));
  }

  const run = (kind: "save" | "approve" | "reject", fn: () => Promise<void>) => async () => {
    setBusy(kind);
    try {
      await fn();
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card>
      <CardHead review={review} />
      <CardContent className="space-y-4">
        <MetaRow review={review} />
        <div>
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
              Draft reply {dirty && <span className="text-amber-600">· edited (unsaved)</span>}
            </p>
            {templates.length > 0 && (
              <select
                value=""
                onChange={(e) => {
                  insertTemplate(e.target.value);
                  e.currentTarget.value = "";
                }}
                className="max-w-[220px] rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs text-slate-600 shadow-sm focus:border-blue-500 focus:outline-none"
                aria-label="Insert a canned-response template"
              >
                <option value="">+ Insert template…</option>
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.title}
                  </option>
                ))}
              </select>
            )}
          </div>
          <Textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            className="min-h-[180px] font-normal"
          />
        </div>
        {review.citations.length > 0 && <Citations citations={review.citations} />}
        <div className="flex flex-wrap items-center justify-end gap-2 border-t border-slate-100 pt-4">
          <Button variant="outline" onClick={run("reject", onReject)} disabled={busy !== null}>
            {busy === "reject" ? <Loader2 className="h-4 w-4 animate-spin" /> : <XCircle className="h-4 w-4" />}
            Reject
          </Button>
          <Button
            variant="outline"
            onClick={run("save", () => onSave(body))}
            disabled={!dirty || busy !== null}
          >
            {busy === "save" ? <Loader2 className="h-4 w-4 animate-spin" /> : "Save edits"}
          </Button>
          <Button
            onClick={run("approve", () => onApprove(body))}
            disabled={busy !== null}
            className="bg-blue-600 text-white hover:bg-blue-700"
          >
            {busy === "approve" ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <ClipboardCheck className="h-4 w-4" />
            )}
            Approve → Gmail Drafts
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function ApprovedCard({ review, onSend }: { review: Review; onSend: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  return (
    <Card>
      <CardHead review={review} />
      <CardContent className="space-y-4">
        <div className="whitespace-pre-line rounded-lg border border-slate-200 bg-white p-4 text-sm leading-relaxed text-slate-800 shadow-inner">
          {review.draft_body}
        </div>
        <div className="flex items-center justify-between gap-2 border-t border-slate-100 pt-4">
          <span className="text-xs text-slate-400">In Gmail Drafts · not yet sent</span>
          <Button
            onClick={async () => {
              setBusy(true);
              try {
                await onSend();
              } finally {
                setBusy(false);
              }
            }}
            disabled={busy}
            className="bg-emerald-600 text-white hover:bg-emerald-700"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            Send reply
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function Citations({ citations }: { citations: Citation[] }) {
  return (
    <div className="flex flex-wrap gap-2">
      {citations.map((c) => (
        <span
          key={c.document_id}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-600"
        >
          <span className="font-medium text-slate-500">{c.source}</span>
          <span className="text-slate-300">·</span>
          <span className="truncate">{c.title}</span>
        </span>
      ))}
    </div>
  );
}

/* ── Layout bits ───────────────────────────────────── */

function Section({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-4">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
        {title} <span className="ml-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs">{count}</span>
      </h2>
      {children}
    </section>
  );
}

function EmptyRow({ text }: { text: string }) {
  return (
    <Card className="border-dashed">
      <CardContent className="py-8 text-center text-sm text-slate-500">{text}</CardContent>
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
          <p className="font-medium text-slate-700">Sign in to review drafts</p>
          <p className="mt-1 text-sm text-slate-500">
            Sign in with your clinic Google account to see the review queue.
          </p>
        </div>
        <Button
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await startGoogleSignIn("/reviews");
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
    <div className="space-y-4">
      {[0, 1].map((i) => (
        <Card key={i}>
          <CardHeader>
            <Skeleton className="h-5 w-64" />
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-2">
              <Skeleton className="h-6 w-24 rounded-full" />
              <Skeleton className="h-6 w-24 rounded-full" />
            </div>
            <Skeleton className="h-2 w-full rounded-full" />
            <Skeleton className="h-28 w-full" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
