"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Archive,
  Check,
  CheckCircle2,
  ChevronDown,
  Clock3,
  FileText,
  Inbox,
  Loader2,
  Mail,
  MessageSquare,
  PanelLeftClose,
  RefreshCw,
  Send,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Stethoscope,
  UserRound,
  Users,
  X,
} from "lucide-react";

import { DashboardLayout } from "@/components/dashboard-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import {
  ApiError,
  approveReview,
  editDraft,
  getReview,
  listReviews,
  rejectReview,
  sendReview,
  submitSpecialistInput,
  type Review,
  type ReviewStatus,
} from "@/lib/api";
import {
  addReviewNote,
  assignReview,
  listReviewNotes,
  listTeamMembers,
  type ReviewNote,
  type TeamMember,
} from "@/lib/admin";
import { getToken, startGoogleSignIn } from "@/lib/auth";
import { useGmailSync } from "@/lib/use-gmail-sync";
import { cn } from "@/lib/utils";

const QUEUES: Array<{
  id: ReviewStatus;
  label: string;
  helper: string;
  icon: typeof Inbox;
  tone: string;
}> = [
  { id: "pending", label: "Ready for review", helper: "AI drafts ready for a staff decision", icon: Inbox, tone: "text-blue-600 bg-blue-50" },
  { id: "awaiting_specialist_input", label: "Needs clinical input", helper: "Escalated emails awaiting a clinician", icon: Stethoscope, tone: "text-amber-700 bg-amber-50" },
  { id: "specialist_input_received", label: "Ready after input", helper: "Specialist guidance has been received", icon: MessageSquare, tone: "text-violet-700 bg-violet-50" },
  { id: "needs_manual_handling", label: "Manual handling", helper: "No AI draft — staff must respond directly", icon: ShieldAlert, tone: "text-orange-700 bg-orange-50" },
  { id: "approved", label: "Draft saved in Gmail", helper: "Approved drafts awaiting a final send", icon: CheckCircle2, tone: "text-emerald-700 bg-emerald-50" },
  { id: "sent", label: "Sent", helper: "Completed emails", icon: Send, tone: "text-slate-600 bg-slate-100" },
  { id: "rejected", label: "Rejected", helper: "Drafts not used", icon: X, tone: "text-rose-700 bg-rose-50" },
  { id: "irrelevant", label: "No action", helper: "Noise or irrelevant messages", icon: Archive, tone: "text-slate-600 bg-slate-100" },
];

const DEPARTMENTS: Record<string, string> = {
  front_office: "Front office",
  nurse: "Nursing",
  specialist: "Specialist",
  laboratory: "Laboratory",
  gastroenterology: "Gastroenterology",
  physiotherapy: "Physiotherapy",
};

function label(value: string) {
  return DEPARTMENTS[value] ?? value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(value));
}

function classification(review: Review) {
  if (review.classification === "ADMIN_DIRECT_REPLY") return { label: "Draft eligible", tone: "text-blue-700 bg-blue-50 border-blue-200", icon: Sparkles };
  if (review.classification === "ROUTE_TO_STAFF") return { label: "Staff handling", tone: "text-orange-700 bg-orange-50 border-orange-200", icon: ShieldAlert };
  if (review.classification === "NEEDS_PHYSICIAN_REVIEW") return { label: "Clinical review", tone: "text-violet-700 bg-violet-50 border-violet-200", icon: Stethoscope };
  return { label: "No action", tone: "text-slate-700 bg-slate-100 border-slate-200", icon: FileText };
}

export default function ReviewsPage() {
  const [activeQueue, setActiveQueue] = useState<ReviewStatus>("pending");
  const [queues, setQueues] = useState<Record<string, Review[]>>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Review | null>(null);
  const selectedIdRef = useRef<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mobilePanel, setMobilePanel] = useState<"queues" | "list" | "detail">("list");

  const load = useCallback(async () => {
    if (!getToken()) {
      await startGoogleSignIn("/reviews");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const responses = await Promise.all(QUEUES.map(async (queue) => [queue.id, await listReviews(queue.id, 200)] as const));
      const next = Object.fromEntries(responses.map(([id, result]) => [id, result.reviews]));
      setQueues(next);
      const visible = next[activeQueue] ?? [];
      const currentId = selectedIdRef.current;
      const nextId = currentId && visible.some((review) => review.id === currentId) ? currentId : visible[0]?.id ?? null;
      selectedIdRef.current = nextId;
      setSelectedId(nextId);
      setSelected(nextId ? visible.find((review) => review.id === nextId) ?? null : null);
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) {
        await startGoogleSignIn("/reviews");
      } else {
        setError(err instanceof Error ? err.message : "Could not load the review workspace.");
      }
    } finally {
      setLoading(false);
    }
  }, [activeQueue]);

  useEffect(() => { void load(); }, [load]);

  const sync = useGmailSync({
    onComplete: () => void load(),
    onUnauthorized: () => void startGoogleSignIn("/reviews"),
  });
  const reviews = queues[activeQueue] ?? [];

  const select = async (id: string) => {
    selectedIdRef.current = id;
    setSelectedId(id);
    setMobilePanel("detail");
    try { setSelected(await getReview(id)); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not open this email."); }
  };

  const changeQueue = (queue: ReviewStatus) => {
    setActiveQueue(queue);
    setMobilePanel("list");
  };

  return (
    <DashboardLayout>
      <div className="min-h-screen bg-slate-50 text-slate-900">
        <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 px-4 py-3 backdrop-blur md:px-7">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-700">Shared inbox</p>
              <h1 className="text-xl font-bold tracking-tight">Review workspace</h1>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => void load()} disabled={loading} className="hidden sm:inline-flex">
                <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} /> Refresh
              </Button>
              <Button size="sm" onClick={() => void sync.sync()} disabled={sync.disabled} className="bg-emerald-600 hover:bg-emerald-700">
                {sync.syncing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                {sync.syncing ? "Syncing inbox" : "Sync inbox"}
              </Button>
            </div>
          </div>
          {(sync.error || error) && <p className="mt-2 rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{sync.error ?? error}</p>}
          {sync.lastResult && <p className="mt-2 text-xs text-slate-500">Last sync {sync.lastSyncedLabel}: {sync.lastResult.created ?? 0} added, {sync.lastResult.skipped ?? 0} already handled.</p>}
        </header>

        <main className="grid min-h-[calc(100vh-93px)] grid-cols-1 lg:grid-cols-[250px_330px_minmax(0,1fr)]">
          <QueueNav queues={queues} active={activeQueue} onChange={changeQueue} mobilePanel={mobilePanel} />
          <ReviewList reviews={reviews} selectedId={selectedId} activeQueue={activeQueue} loading={loading} onSelect={select} mobilePanel={mobilePanel} />
          <ReviewDetail review={selected} onRefresh={load} onSelectQueue={changeQueue} mobilePanel={mobilePanel} onBack={() => setMobilePanel("list")} />
        </main>
      </div>
    </DashboardLayout>
  );
}

function QueueNav({ queues, active, onChange, mobilePanel }: { queues: Record<string, Review[]>; active: ReviewStatus; onChange: (id: ReviewStatus) => void; mobilePanel: string }) {
  return <aside className={cn("border-r border-slate-200 bg-white p-3 lg:block", mobilePanel === "queues" ? "block" : "hidden")}>
    <div className="mb-3 px-2"><p className="text-sm font-semibold">Queues</p><p className="text-xs text-slate-500">Organised by safe next step</p></div>
    <nav className="space-y-1">
      {QUEUES.map((queue) => {
        const Icon = queue.icon; const count = queues[queue.id]?.length ?? 0;
        return <button key={queue.id} onClick={() => onChange(queue.id)} className={cn("flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition", active === queue.id ? "bg-slate-900 text-white shadow-sm" : "text-slate-600 hover:bg-slate-100")}>
          <span className={cn("grid h-8 w-8 place-items-center rounded-md", active === queue.id ? "bg-white/15 text-white" : queue.tone)}><Icon className="h-4 w-4" /></span>
          <span className="min-w-0 flex-1"><span className="block text-sm font-medium">{queue.label}</span></span>
          <span className={cn("min-w-5 rounded-full px-1.5 py-0.5 text-center text-xs font-bold", active === queue.id ? "bg-white/15" : "bg-slate-100 text-slate-500")}>{count}</span>
        </button>;
      })}
    </nav>
  </aside>;
}

function ReviewList({ reviews, selectedId, activeQueue, loading, onSelect, mobilePanel }: { reviews: Review[]; selectedId: string | null; activeQueue: ReviewStatus; loading: boolean; onSelect: (id: string) => void; mobilePanel: string }) {
  const queue = QUEUES.find((item) => item.id === activeQueue)!;
  return <section className={cn("border-r border-slate-200 bg-slate-50", mobilePanel === "list" ? "block" : "hidden lg:block")}>
    <div className="border-b border-slate-200 bg-white px-5 py-4"><div className="flex items-center justify-between"><div><h2 className="font-semibold">{queue.label}</h2><p className="text-xs text-slate-500">{queue.helper}</p></div><Badge>{reviews.length}</Badge></div></div>
    <div className="max-h-[calc(100vh-166px)] overflow-y-auto p-2">
      {loading ? <div className="p-6 text-center text-sm text-slate-500"><Loader2 className="mx-auto mb-2 h-5 w-5 animate-spin" />Loading inbox…</div> : reviews.length === 0 ? <EmptyQueue /> : reviews.map((review) => <button key={review.id} onClick={() => onSelect(review.id)} className={cn("mb-1 w-full rounded-lg border p-3 text-left transition", selectedId === review.id ? "border-emerald-300 bg-emerald-50 shadow-sm" : "border-transparent bg-white hover:border-slate-200 hover:bg-slate-50")}><div className="mb-1.5 flex items-center justify-between gap-3"><span className="truncate text-sm font-semibold">{review.sender || "Unknown sender"}</span><span className="shrink-0 text-[11px] text-slate-400">{formatTime(review.created_at)}</span></div><p className="line-clamp-1 text-sm font-medium text-slate-800">{review.subject || "(No subject)"}</p><p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">{review.summary || review.reason}</p><div className="mt-2 flex items-center gap-2"><span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-600">{label(review.department)}</span>{review.urgency !== "normal" && <span className="text-[11px] font-medium text-orange-700">{review.urgency} priority</span>}</div></button>)}</div>
  </section>;
}

function EmptyQueue() { return <div className="mx-3 mt-10 rounded-xl border border-dashed border-slate-300 bg-white p-7 text-center"><Inbox className="mx-auto mb-3 h-8 w-8 text-slate-300" /><p className="text-sm font-medium text-slate-700">Nothing here right now</p><p className="mt-1 text-xs leading-5 text-slate-500">Sync the inbox or choose another queue.</p></div>; }

function ReviewDetail({ review, onRefresh, onSelectQueue, mobilePanel, onBack }: { review: Review | null; onRefresh: () => Promise<void>; onSelectQueue: (status: ReviewStatus) => void; mobilePanel: string; onBack: () => void }) {
  const [editing, setEditing] = useState(false); const [draft, setDraft] = useState(""); const [specialistInput, setSpecialistInput] = useState(""); const [note, setNote] = useState(""); const [notes, setNotes] = useState<ReviewNote[]>([]); const [team, setTeam] = useState<TeamMember[]>([]); const [busy, setBusy] = useState(false); const [message, setMessage] = useState<string | null>(null);
  useEffect(() => { if (!review) return; setDraft(review.draft_body); setSpecialistInput(""); setEditing(false); setMessage(null); void Promise.all([listReviewNotes(review.id), listTeamMembers()]).then(([nextNotes, nextTeam]) => { setNotes(nextNotes); setTeam(nextTeam); }).catch(() => {}); }, [review?.id]);
  if (!review) return <section className={cn("grid place-items-center bg-white p-8", mobilePanel === "detail" ? "block" : "hidden lg:grid")}><div className="max-w-sm text-center"><div className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-emerald-50"><Mail className="h-6 w-6 text-emerald-600" /></div><h2 className="mt-4 font-semibold">Select an email to review</h2><p className="mt-1 text-sm leading-6 text-slate-500">Choose an item from a queue to see its decision, sources, collaboration history, and permitted actions.</p></div></section>;
  const decision = classification(review); const DecisionIcon = decision.icon; const isManual = review.status === "needs_manual_handling"; const canEdit = review.status === "pending" || review.status === "specialist_input_received"; const canApprove = canEdit && Boolean(review.draft_body.trim());
  const run = async (action: () => Promise<unknown>, success: string) => { setBusy(true); setMessage(null); try { await action(); setMessage(success); await onRefresh(); } catch (err) { setMessage(err instanceof Error ? err.message : "Action failed."); } finally { setBusy(false); } };
  return <section className={cn("min-w-0 bg-white", mobilePanel === "detail" ? "block" : "hidden lg:block")}><div className="max-h-[calc(100vh-93px)] overflow-y-auto"><div className="border-b border-slate-200 px-5 py-4 md:px-7"><button onClick={onBack} className="mb-3 inline-flex items-center gap-1 text-xs font-medium text-slate-500 lg:hidden"><PanelLeftClose className="h-3.5 w-3.5" /> Back to inbox</button><div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0"><div className="mb-2 flex flex-wrap gap-2"><Badge className={decision.tone}><DecisionIcon className="h-3.5 w-3.5" />{decision.label}</Badge><Badge className="bg-slate-100 text-slate-700">{label(review.department)}</Badge></div><h2 className="text-xl font-bold tracking-tight">{review.subject || "(No subject)"}</h2><p className="mt-1 text-sm text-slate-500">From <span className="font-medium text-slate-700">{review.sender || "Unknown sender"}</span> · received {formatTime(review.created_at)}</p></div><span className="rounded-lg bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600">{Math.round(review.confidence * 100)}% confidence</span></div></div>
    <div className="space-y-6 p-5 md:p-7">
      {message && <p className="rounded-md bg-slate-100 px-3 py-2 text-sm text-slate-700">{message}</p>}
      <div className="grid gap-4 xl:grid-cols-2"><Info label="AI triage" value={`${label(review.intent)} · ${review.urgency} priority`} /><Info label="Why this was routed" value={review.reason || "No reason was recorded."} /></div>
      {isManual ? <Card className="border-orange-200 bg-orange-50"><CardContent className="flex gap-3 py-5"><ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-orange-600" /><div><p className="font-semibold text-orange-900">Manual response required</p><p className="mt-1 text-sm leading-6 text-orange-800">This email intentionally has no AI draft. Handle it through your clinic’s normal process; it cannot be approved from this workspace.</p></div></CardContent></Card> : review.status === "awaiting_specialist_input" ? <SpecialistForm value={specialistInput} onChange={setSpecialistInput} disabled={busy} onSubmit={() => run(() => submitSpecialistInput(review.id, specialistInput, true), "Clinical guidance saved and draft regenerated.")} /> : <DraftEditor value={editing ? draft : review.draft_body} editable={editing} onChange={setDraft} onEdit={() => setEditing(true)} onCancel={() => { setDraft(review.draft_body); setEditing(false); }} onSave={() => run(() => editDraft(review.id, draft), "Draft saved.").then(() => setEditing(false))} disabled={busy} />}
      <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-5">{canApprove && <Button disabled={busy} onClick={() => run(() => approveReview(review.id), "Approved — a draft was saved to Gmail.")} className="bg-emerald-600 hover:bg-emerald-700"><Check className="h-4 w-4" />Approve to Gmail drafts</Button>}{canEdit && <Button variant="outline" disabled={busy} onClick={() => run(() => rejectReview(review.id, "Rejected by staff"), "Draft rejected.")}><X className="h-4 w-4" />Reject</Button>}{review.status === "approved" && <Button disabled={busy} onClick={() => run(() => sendReview(review.id), "Email sent.")} className="bg-slate-900 hover:bg-slate-800"><Send className="h-4 w-4" />Send email</Button>}</div>
      <Sources citations={review.citations} />
      <Collaboration review={review} team={team} notes={notes} note={note} setNote={setNote} busy={busy} onAssign={(user) => run(() => assignReview(review.id, user), "Assignment updated.")} onNote={() => run(async () => { const saved = await addReviewNote(review.id, note); setNotes((items) => [...items, saved]); setNote(""); }, "Note added.")} />
    </div></div></section>;
}

function Info({ label: heading, value }: { label: string; value: string }) { return <div className="rounded-lg border border-slate-200 bg-slate-50 p-3"><p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">{heading}</p><p className="mt-1 text-sm leading-5 text-slate-700">{value}</p></div>; }
function DraftEditor({ value, editable, onChange, onEdit, onCancel, onSave, disabled }: { value: string; editable: boolean; onChange: (value: string) => void; onEdit: () => void; onCancel: () => void; onSave: () => void; disabled: boolean }) { return <div><div className="mb-2 flex items-center justify-between"><div><h3 className="font-semibold">Proposed reply</h3><p className="text-xs text-slate-500">Review every message before approval.</p></div>{value && !editable && <Button variant="outline" size="sm" onClick={onEdit}>Edit draft</Button>}</div>{value ? editable ? <><Textarea value={value} onChange={(event) => onChange(event.target.value)} rows={12} className="min-h-[260px] leading-6" /><div className="mt-2 flex gap-2"><Button size="sm" disabled={disabled || !value.trim()} onClick={onSave}>Save changes</Button><Button size="sm" variant="outline" onClick={onCancel}>Cancel</Button></div></> : <div className="whitespace-pre-wrap rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm leading-7 text-slate-700">{value}</div> : <Card className="border-dashed"><CardContent className="py-8 text-center text-sm text-slate-500">No AI draft is available for this email.</CardContent></Card>}</div>; }
function SpecialistForm({ value, onChange, onSubmit, disabled }: { value: string; onChange: (value: string) => void; onSubmit: () => void; disabled: boolean }) { return <Card className="border-violet-200 bg-violet-50/50"><CardContent className="py-5"><div className="flex gap-3"><Stethoscope className="mt-0.5 h-5 w-5 text-violet-700" /><div><h3 className="font-semibold text-violet-950">Clinical guidance needed</h3><p className="mt-1 text-sm leading-6 text-violet-800">Add specialist guidance. The assistant will only use that guidance to prepare a reviewable reply.</p></div></div><Textarea value={value} onChange={(event) => onChange(event.target.value)} placeholder="Provide the approved clinical guidance for this response…" rows={7} className="mt-4 min-h-[160px]" /><Button disabled={disabled || !value.trim()} onClick={onSubmit} className="mt-3 bg-violet-700 hover:bg-violet-800">{disabled && <Loader2 className="h-4 w-4 animate-spin" />}Submit guidance</Button></CardContent></Card>; }
function Sources({ citations }: { citations: Review["citations"] }) { return <div><h3 className="mb-2 font-semibold">Grounding sources</h3>{citations.length ? <div className="flex flex-wrap gap-2">{citations.map((citation) => <a key={citation.document_id} href={citation.url ?? undefined} target="_blank" rel="noreferrer" className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600 hover:border-emerald-300 hover:text-emerald-700"><span className="font-semibold uppercase tracking-wide text-slate-400">{citation.source}</span> · {citation.title}</a>)}</div> : <p className="text-sm text-slate-500">No source was used because this item was escalated or requires manual handling.</p>}</div>; }
function Collaboration({ review, team, notes, note, setNote, busy, onAssign, onNote }: { review: Review; team: TeamMember[]; notes: ReviewNote[]; note: string; setNote: (value: string) => void; busy: boolean; onAssign: (value: string | null) => void; onNote: () => void }) { return <div className="border-t border-slate-100 pt-6"><div className="mb-3 flex items-center gap-2"><Users className="h-4 w-4 text-slate-500" /><h3 className="font-semibold">Team coordination</h3></div><div className="grid gap-5 xl:grid-cols-2"><div><label className="text-xs font-medium text-slate-500">Assigned staff member</label><div className="relative mt-1"><select value={review.assigned_to ?? ""} onChange={(event) => onAssign(event.target.value || null)} disabled={busy} className="w-full appearance-none rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700"><option value="">Unassigned</option>{team.map((member) => <option key={member.id} value={member.id}>{member.full_name || member.email} · {label(member.role)}</option>)}</select><ChevronDown className="pointer-events-none absolute right-3 top-2.5 h-4 w-4 text-slate-400" /></div></div><div><label className="text-xs font-medium text-slate-500">Internal note</label><div className="mt-1 flex gap-2"><input value={note} onChange={(event) => setNote(event.target.value)} placeholder="Add a hand-off note" className="min-w-0 flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm" /><Button size="sm" disabled={busy || !note.trim()} onClick={onNote}>Add</Button></div></div></div>{notes.length > 0 && <div className="mt-4 space-y-2">{notes.map((item) => <div key={item.id} className="rounded-lg bg-slate-50 px-3 py-2 text-sm"><span className="font-medium text-slate-700">Team note</span><span className="ml-2 text-xs text-slate-400">{formatTime(item.created_at)}</span><p className="mt-1 text-slate-600">{item.body}</p></div>)}</div>}</div>; }
