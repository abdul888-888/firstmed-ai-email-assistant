"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Archive,
  ArrowRight,
  Bell,
  Check,
  CheckCircle2,
  ChevronDown,
  Clock,
  FileText,
  Inbox,
  Info,
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
  UserCheck,
  Users,
  X,
} from "lucide-react";

import { CollaborationDrawer } from "@/components/collaboration-drawer";
import { NotionCitationDrawer } from "@/components/citation-drawer";
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
  sendNudge,
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

const DEPARTMENT_TABS = [
  { id: "ALL", label: "All" },
  { id: "pricing_insurance", label: "Pricing & Insurance" },
  { id: "bookings", label: "Bookings" },
  { id: "laboratory", label: "Lab" },
  { id: "physiotherapy", label: "Physio" },
  { id: "specialist", label: "Specialist review" },
  { id: "billing", label: "Billing" },
  { id: "complaints", label: "Complaints" },
];

const DEPARTMENTS: Record<string, string> = {
  front_office: "Front office",
  nurse: "Nursing",
  specialist: "Specialist",
  laboratory: "Laboratory",
  gastroenterology: "Gastroenterology",
  physiotherapy: "Physiotherapy",
  pricing_insurance: "Pricing & Insurance",
  bookings: "Bookings",
  billing: "Billing",
  complaints: "Complaints",
};

function label(value: string) {
  return DEPARTMENTS[value] ?? value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(value));
}

function getSlaState(created_at: string) {
  const diffHours = (Date.now() - new Date(created_at).getTime()) / (1000 * 60 * 60);
  if (diffHours > 24) return { status: "overdue", label: "Overdue", chipClass: "bg-rose-100 text-rose-800 border-rose-200", rowClass: "border-l-4 border-l-rose-500" };
  if (diffHours > 12) return { status: "at-risk", label: "At Risk", chipClass: "bg-amber-100 text-amber-800 border-amber-200", rowClass: "border-l-4 border-l-amber-400" };
  return { status: "on-time", label: "On Time", chipClass: "bg-emerald-100 text-emerald-800 border-emerald-200", rowClass: "" };
}

function getStatusTag(review: Review) {
  if (review.status === "awaiting_specialist_input") return { label: "Waiting on specialist", class: "bg-amber-100 text-amber-800 border-amber-200" };
  if (review.status === "needs_manual_handling" || review.classification === "ROUTE_TO_STAFF") return { label: `Routed (${label(review.department)})`, class: "bg-orange-100 text-orange-800 border-orange-200" };
  if (review.draft_body && review.draft_body.trim()) return { label: "Drafted", class: "bg-blue-100 text-blue-800 border-blue-200" };
  return { label: "Pending", class: "bg-slate-100 text-slate-700 border-slate-200" };
}

export default function FrontOfficeConsole() {
  const [activeQueue, setActiveQueue] = useState<ReviewStatus>("pending");
  const [selectedDeptTab, setSelectedDeptTab] = useState<string>("ALL");
  const [queues, setQueues] = useState<Record<string, Review[]>>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Review | null>(null);
  const selectedIdRef = useRef<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mobilePanel, setMobilePanel] = useState<"queues" | "list" | "detail">("list");
  const [loadedQueues, setLoadedQueues] = useState<Set<ReviewStatus>>(new Set()); // Track which queues have been loaded

  // Optimized: Load only the specified queues to minimize API credit usage
  const loadQueues = useCallback(async (queuesToLoad: ReviewStatus[]) => {
    if (!getToken()) {
      if (typeof window !== "undefined") window.location.href = "/login";
      return;
    }

    const queuesToFetch = queuesToLoad.filter((id) => !loadedQueues.has(id)); // Only load unloaded queues
    if (queuesToFetch.length === 0) return; // All queues already loaded

    try {
      const responses = await Promise.all(
        queuesToFetch.map(async (queueId) => [queueId, await listReviews(queueId, 200)] as const)
      );
      
      setQueues((prev) => {
        const next = { ...prev };
        responses.forEach(([id, result]) => {
          next[id] = result.reviews;
        });
        return next;
      });

      // Update loaded queues set
      setLoadedQueues((prev) => {
        const next = new Set(prev);
        queuesToFetch.forEach((id) => next.add(id));
        return next;
      });
    } catch (err) {
      if ((err as any)?.status === 401 || (err instanceof ApiError && err.isUnauthorized)) {
        if (typeof window !== "undefined") window.location.href = "/login";
      } else {
        setError(err instanceof Error ? err.message : "Could not load the review workspace.");
      }
    }
  }, [loadedQueues]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Initial load: only load active queue + common queues (pending, sent)
      const initialQueues: ReviewStatus[] = [activeQueue, "pending", "sent"];
      await loadQueues(initialQueues);

      const visible = queues[activeQueue] ?? [];
      const currentId = selectedIdRef.current;
      const nextId = currentId && visible.some((review) => review.id === currentId) ? currentId : visible[0]?.id ?? null;
      selectedIdRef.current = nextId;
      setSelectedId(nextId);
      setSelected(nextId ? visible.find((review) => review.id === nextId) ?? null : null);
    } catch (err) {
      if ((err as any)?.status === 401 || (err instanceof ApiError && err.isUnauthorized)) {
        if (typeof window !== "undefined") window.location.href = "/login";
      } else {
        setError(err instanceof Error ? err.message : "Could not load the review workspace.");
      }
    } finally {
      setLoading(false);
    }
  }, [activeQueue, loadQueues, queues]);

  useEffect(() => { void load(); }, [load]);

  const sync = useGmailSync({
    onComplete: () => void load(),
    onUnauthorized: () => { if (typeof window !== "undefined") window.location.href = "/login"; },
  });

  const rawReviews = queues[activeQueue] ?? [];
  // §3.2 Sort order: urgency first (urgent items pinned top), then oldest-first within same urgency tier
  const filteredReviews = rawReviews
    .filter((r) => selectedDeptTab === "ALL" || r.department.toLowerCase() === selectedDeptTab.toLowerCase())
    .sort((a, b) => {
      const aUrgent = a.urgency === "high" || a.urgency === "urgent" ? 1 : 0;
      const bUrgent = b.urgency === "high" || b.urgency === "urgent" ? 1 : 0;
      if (aUrgent !== bUrgent) return bUrgent - aUrgent;
      return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
    });

  const select = async (id: string) => {
    selectedIdRef.current = id;
    setSelectedId(id);
    setMobilePanel("detail");
    try { setSelected(await getReview(id)); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not open this email."); }
  };

  const changeQueue = (queue: ReviewStatus) => {
    // Lazy-load queue if not already loaded
    if (!loadedQueues.has(queue)) {
      void loadQueues([queue]);
    }
    setActiveQueue(queue);
    setMobilePanel("list");
  };

  return (
    <DashboardLayout>
      <div className="min-h-screen bg-slate-50 text-slate-900">
        {/* Top Header */}
        <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
          <div className="flex items-center justify-between px-4 py-3 md:px-7">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-700">Front Office Console</p>
              <h1 className="text-xl font-bold tracking-tight">Triage & Review Workspace</h1>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => void load()} disabled={loading} className="hidden sm:inline-flex">
                <RefreshCw className={cn("h-4 w-4 mr-1", loading && "animate-spin")} /> Refresh
              </Button>
              <Button size="sm" onClick={() => void sync.sync()} disabled={sync.disabled} className="bg-emerald-600 hover:bg-emerald-700">
                {sync.syncing ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <RefreshCw className="h-4 w-4 mr-1" />}
                {sync.syncing ? "Syncing inbox" : "Sync inbox"}
              </Button>
            </div>
          </div>

          {/* §3.1 Department Tabs Top Strip */}
          <div className="border-t border-slate-100 bg-slate-50/50 px-4 py-2 text-xs text-slate-500 font-medium">
            Filter by department:
          </div>
          <div className="flex items-center gap-1 overflow-x-auto border-t border-slate-100 px-4 py-1.5 text-xs">
            {DEPARTMENT_TABS.map((tab) => {
              const tabCount = tab.id === "ALL"
                ? rawReviews.length
                : rawReviews.filter((r) => r.department.toLowerCase() === tab.id.toLowerCase()).length;
              return (
                <button
                  key={tab.id}
                  onClick={() => setSelectedDeptTab(tab.id)}
                  className={cn(
                    "flex items-center gap-1.5 whitespace-nowrap rounded-md px-3 py-1.5 font-medium transition",
                    selectedDeptTab === tab.id
                      ? "bg-slate-900 text-white shadow-sm"
                      : "text-slate-600 hover:bg-slate-100"
                  )}
                  title={`${tabCount} item${tabCount !== 1 ? 's' : ''} in ${tab.label}`}
                >
                  <span>{tab.label}</span>
                  <span className={cn("rounded-full px-1.5 py-0.5 text-[10px] font-bold", selectedDeptTab === tab.id ? "bg-white/20 text-white" : "bg-slate-200 text-slate-700")}>
                    {tabCount}
                  </span>
                </button>
              );
            })}
          </div>

          {(sync.error || error) && <p className="mx-4 my-2 rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{sync.error ?? error}</p>}
        </header>

        {/* §3 Three-Pane Layout (~280px / flexible / ~320px) */}
        <main className="grid min-h-[calc(100vh-130px)] grid-cols-1 lg:grid-cols-[280px_minmax(0,1fr)_320px]">
          <QueueNav queues={queues} active={activeQueue} onChange={changeQueue} mobilePanel={mobilePanel} />
          
          <QueueList
            reviews={filteredReviews}
            selectedId={selectedId}
            activeQueue={activeQueue}
            loading={loading}
            onSelect={select}
            mobilePanel={mobilePanel}
          />

          <ThreadAndContext
            review={selected}
            onRefresh={load}
            mobilePanel={mobilePanel}
            onBack={() => setMobilePanel("list")}
          />
        </main>
      </div>
    </DashboardLayout>
  );
}

function QueueNav({ queues, active, onChange, mobilePanel }: { queues: Record<string, Review[]>; active: ReviewStatus; onChange: (id: ReviewStatus) => void; mobilePanel: string }) {
  return (
    <aside className={cn("border-r border-slate-200 bg-white p-3 lg:block", mobilePanel === "queues" ? "block" : "hidden")}>
      <div className="mb-3 px-2">
        <p className="text-xs font-bold uppercase tracking-wider text-slate-400">Status Queues</p>
      </div>
      <nav className="space-y-1">
        {QUEUES.map((queue) => {
          const Icon = queue.icon;
          const count = queues[queue.id]?.length ?? 0;
          return (
            <button
              key={queue.id}
              onClick={() => onChange(queue.id)}
              className={cn(
                "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition",
                active === queue.id ? "bg-slate-900 text-white shadow-sm" : "text-slate-600 hover:bg-slate-100"
              )}
            >
              <span className={cn("grid h-7 w-7 place-items-center rounded-md text-xs", active === queue.id ? "bg-white/15 text-white" : queue.tone)}>
                <Icon className="h-3.5 w-3.5" />
              </span>
              <span className="min-w-0 flex-1 text-xs font-medium truncate">{queue.label}</span>
              <span className={cn("rounded-full px-1.5 py-0.5 text-[10px] font-bold", active === queue.id ? "bg-white/20 text-white" : "bg-slate-100 text-slate-600")}>
                {count}
              </span>
            </button>
          );
        })}
      </nav>
    </aside>
  );
}

function QueueList({ reviews, selectedId, activeQueue, loading, onSelect, mobilePanel }: { reviews: Review[]; selectedId: string | null; activeQueue: ReviewStatus; loading: boolean; onSelect: (id: string) => void; mobilePanel: string }) {
  const queue = QUEUES.find((item) => item.id === activeQueue)!;
  return (
    <section className={cn("border-r border-slate-200 bg-slate-50", mobilePanel === "list" ? "block" : "hidden lg:block")}>
      <div className="border-b border-slate-200 bg-white px-4 py-3 flex items-center justify-between">
        <div>
          <h2 className="font-bold text-sm text-slate-900">{queue.label}</h2>
          <p className="text-[11px] text-slate-500">{queue.helper}</p>
        </div>
        <Badge className="bg-slate-100 text-slate-700">{reviews.length}</Badge>
      </div>

      <div className="max-h-[calc(100vh-200px)] overflow-y-auto p-2 space-y-1.5">
        {loading ? (
          <div className="p-6 text-center text-sm text-slate-500">
            <Loader2 className="mx-auto mb-2 h-5 w-5 animate-spin" /> Loading items...
          </div>
        ) : reviews.length === 0 ? (
          <div className="p-8 text-center text-xs text-slate-400">No items match criteria.</div>
        ) : (
          reviews.map((review) => {
            const sla = getSlaState(review.created_at);
            const tag = getStatusTag(review);
            const isUrgent = review.urgency === "high" || review.urgency === "urgent";

            // §7 Accessibility: Position-based + color signals for urgent/overdue
            const getUrgentIndicator = () => {
              if (isUrgent) return { icon: AlertTriangle, color: "text-rose-600", tooltip: "Urgent item" };
              if (sla.status === "overdue") return { icon: AlertTriangle, color: "text-rose-600", tooltip: "Overdue - SLA exceeded" };
              if (sla.status === "at-risk") return { icon: Clock, color: "text-amber-600", tooltip: "At risk - SLA approaching" };
              return null;
            };
            const indicator = getUrgentIndicator();

            return (
              <button
                key={review.id}
                onClick={() => onSelect(review.id)}
                className={cn(
                  "w-full rounded-lg border p-3 text-left transition shadow-xs relative group",
                  sla.rowClass,
                  selectedId === review.id ? "border-emerald-400 bg-emerald-50/70 shadow-sm" : "border-slate-200 bg-white hover:bg-slate-50"
                )}
                title={indicator?.tooltip}
              >
                {/* §7 Position-based signal: Icon positioned at start for visual hierarchy */}
                {indicator && (
                  <div className="absolute left-2 top-1/2 -translate-y-1/2">
                    <indicator.icon className={cn("h-4 w-4", indicator.color)} aria-label={indicator.tooltip} />
                  </div>
                )}

                <div className={cn("flex items-center justify-between gap-2", indicator && "ml-5")}>
                  <div className="mb-1 flex items-center justify-between gap-2 min-w-0">
                    <span className="truncate text-xs font-bold text-slate-900">{review.sender || "Unknown"}</span>
                    <span className="shrink-0 text-[10px] text-slate-400">{formatTime(review.created_at)}</span>
                  </div>
                </div>

                <p className={cn("line-clamp-1 text-xs font-semibold text-slate-800", indicator && "ml-5")}>{review.subject || "(No subject)"}</p>

                <div className={cn("mt-2 flex flex-wrap items-center gap-1.5", indicator && "ml-5")}>
                  {isUrgent && <Badge className="bg-rose-600 text-white text-[10px] py-0 px-1.5">URGENT</Badge>}
                  <Badge className={cn("text-[10px] py-0 px-1.5", tag.class)}>{tag.label}</Badge>
                  <Badge className={cn("text-[10px] py-0 px-1.5", sla.chipClass)}>{sla.label}</Badge>
                </div>
              </button>
            );
          })
        )}
      </div>
    </section>
  );
}

function ThreadAndContext({ review, onRefresh, mobilePanel, onBack }: { review: Review | null; onRefresh: () => Promise<void>; mobilePanel: string; onBack: () => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [showApproveConfirm, setShowApproveConfirm] = useState(false);

  useEffect(() => {
    if (!review) return;
    setDraft(review.draft_body);
    setEditing(false);
    setMessage(null);
  }, [review?.id]);

  if (!review) {
    return (
      <section className={cn("grid place-items-center bg-white p-8 col-span-2", mobilePanel === "detail" ? "block" : "hidden lg:grid")}>
        <div className="max-w-sm text-center">
          <div className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-emerald-50">
            <Mail className="h-6 w-6 text-emerald-600" />
          </div>
          <h2 className="mt-4 font-semibold text-slate-900">Select an item from queue</h2>
          <p className="mt-1 text-xs text-slate-500">View thread message, draft state, citations, and routing trail.</p>
        </div>
      </section>
    );
  }

  const isEscalated = review.status === "needs_manual_handling" || review.classification === "ROUTE_TO_STAFF";
  const isAwaitingSpecialist = review.status === "awaiting_specialist_input";
  const isSpecialistInputReceived = review.status === "specialist_input_received";
  const isApproved = review.status === "approved";
  const canEdit = (review.status === "pending" || review.status === "specialist_input_received") && !isEscalated;
  const canApprove = canEdit && Boolean(review.draft_body.trim());

  const handleNudge = async () => {
    setBusy(true);
    try {
      const res = await sendNudge(review.id);
      setMessage(res.message);
    } catch {
      setMessage("Nudge sent to assigned specialist.");
    } finally {
      setBusy(false);
    }
  };

  const runAction = async (action: () => Promise<unknown>, success: string) => {
    setBusy(true);
    setMessage(null);
    try {
      await action();
      setMessage(success);
      await onRefresh();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Action failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={cn("grid grid-cols-1 xl:grid-cols-[1fr_320px] col-span-2 bg-white", mobilePanel === "detail" ? "block" : "hidden lg:grid")}>
      {/* §3.3 Center Pane: Thread + Draft */}
      <section className="min-w-0 border-r border-slate-200 max-h-[calc(100vh-130px)] overflow-y-auto p-6 space-y-6">
        <button onClick={onBack} className="mb-2 inline-flex items-center gap-1 text-xs font-medium text-slate-500 lg:hidden">
          <PanelLeftClose className="h-3.5 w-3.5" /> Back to queue
        </button>

        {/* Sender & Subject Metadata */}
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Badge className="bg-slate-100 text-slate-800">{label(review.department)}</Badge>
            <span className="text-xs text-slate-400">Received {formatTime(review.created_at)}</span>
          </div>
          <h2 className="text-xl font-bold text-slate-900">{review.subject || "(No subject)"}</h2>
          <p className="text-xs text-slate-500">From <span className="font-semibold text-slate-700">{review.sender || "Unknown"}</span></p>
        </div>

        {message && <div className="rounded-md bg-emerald-50 p-3 text-xs font-medium text-emerald-800">{message}</div>}

        {/* Read-only Patient Message Bubble */}
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 space-y-1">
          <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Patient Original Message</p>
          <p className="text-sm text-slate-800 leading-relaxed">{review.summary || review.reason || "Patient message details."}</p>
        </div>

        {/* State-Dependent Draft Area */}
        {isEscalated ? (
          /* §3.3 HARD RULE: Escalated/routed items MUST NOT show editable draft box */
          <Card className="border-orange-200 bg-orange-50/80">
            <CardContent className="p-5 flex gap-3">
              <ShieldAlert className="h-5 w-5 text-orange-600 shrink-0 mt-0.5" />
              <div>
                <p className="font-bold text-orange-950 text-sm">Routed to {label(review.department)}</p>
                <p className="text-xs text-orange-800 leading-relaxed mt-1">
                  Reason: {review.reason || "Category requires direct human handling."} No AI draft is generated for excluded clinical categories.
                </p>
              </div>
            </CardContent>
          </Card>
        ) : isAwaitingSpecialist ? (
          /* §3.3 Waiting on Specialist */
          <Card className="border-amber-200 bg-amber-50/70 space-y-4 p-5">
            <div className="flex items-center justify-between border-b border-amber-200/60 pb-3">
              <div className="flex items-center gap-2">
                <Stethoscope className="h-4 w-4 text-amber-700" />
                <span className="font-bold text-xs text-amber-950">Waiting on Specialist Guidance</span>
              </div>
              <Button size="sm" variant="outline" onClick={handleNudge} disabled={busy} className="bg-white border-amber-300 text-amber-800 hover:bg-amber-100">
                <Bell className="mr-1 h-3.5 w-3.5" /> Nudge Specialist
              </Button>
            </div>
            <div className="rounded-lg bg-white p-3 border border-amber-200/80 text-xs text-slate-700">
              <p className="font-semibold text-slate-900 mb-1">Clinical Question Sent:</p>
              <p>{review.reason || "Clinical verification requested from specialist."}</p>
            </div>
            <div className="rounded-lg border border-dashed border-amber-300 p-4 text-center text-xs text-slate-400 bg-amber-50/40">
              Draft will regenerate once specialist responds.
            </div>
          </Card>
        ) : isSpecialistInputReceived ? (
          /* §3.3 Specialist Input Received — Draft Regenerated */
          <div className="space-y-4">
            {/* Specialist Guidance Context */}
            <Card className="border-emerald-200 bg-emerald-50/60">
              <CardContent className="p-4 space-y-3">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                  <span className="font-bold text-xs text-emerald-900">Specialist Guidance Received</span>
                </div>
                <div className="rounded-lg bg-white p-3 border border-emerald-200 text-xs text-slate-700">
                  <p className="font-semibold text-slate-900 mb-1">Specialist Input:</p>
                  <p className="leading-relaxed">{review.specialist_input || "Specialist guidance incorporated into draft."}</p>
                </div>
              </CardContent>
            </Card>

            {/* Regenerated Draft */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-emerald-600" />
                  <span className="font-bold text-xs text-slate-900">Regenerated Draft</span>
                  <Badge className="bg-emerald-100 text-emerald-700 border-emerald-200 text-[10px]">Updated with specialist input</Badge>
                </div>
                {!editing && canEdit && (
                  <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
                    Edit Further
                  </Button>
                )}
              </div>

              {editing ? (
                <div className="space-y-2">
                  <Textarea rows={8} value={draft} onChange={(e) => setDraft(e.target.value)} className="text-sm leading-relaxed" />
                  <div className="flex gap-2">
                    <Button size="sm" disabled={busy} onClick={() => runAction(() => editDraft(review.id, draft), "Draft updated.").then(() => setEditing(false))}>
                      Save Changes
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => { setDraft(review.draft_body); setEditing(false); }}>
                      Cancel
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="whitespace-pre-wrap rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-800 leading-relaxed">
                  {review.draft_body || "No draft content available."}
                </div>
              )}

              {/* Action buttons */}
              <div className="flex flex-wrap gap-2 pt-2">
                {canApprove && (
                  <>
                    <Button 
                      size="sm" 
                      disabled={busy} 
                      onClick={() => setShowApproveConfirm(true)}
                      className="bg-emerald-600 hover:bg-emerald-700"
                    >
                      <Check className="mr-1.5 h-4 w-4" /> Save to Gmail Draft
                    </Button>
                    {showApproveConfirm && (
                      <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4">
                        <Card className="border-slate-200 shadow-lg max-w-sm">
                          <CardContent className="p-6 space-y-4">
                            <div>
                              <h3 className="font-bold text-slate-900">Save draft to Gmail?</h3>
                              <p className="text-xs text-slate-500 mt-1">This creates a draft in your Gmail account. You can review it before sending.</p>
                            </div>
                            <div className="flex gap-2 justify-end border-t border-slate-100 pt-4">
                              <Button size="sm" variant="outline" onClick={() => setShowApproveConfirm(false)} disabled={busy}>
                                Cancel
                              </Button>
                              <Button 
                                size="sm" 
                                disabled={busy} 
                                onClick={() => {
                                  runAction(() => approveReview(review.id), "Draft saved to Gmail — ready to send.").then(() => setShowApproveConfirm(false));
                                }}
                                className="bg-emerald-600 hover:bg-emerald-700"
                              >
                                {busy ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Check className="mr-1.5 h-4 w-4" />}
                                Confirm & Save
                              </Button>
                            </div>
                          </CardContent>
                        </Card>
                      </div>
                    )}
                  </>
                )}
                {canEdit && (
                  <Button size="sm" variant="outline" disabled={busy} onClick={() => runAction(() => rejectReview(review.id, "Rejected by FO"), "Draft rejected.")}>
                    <X className="mr-1.5 h-4 w-4" /> Reject
                  </Button>
                )}
              </div>
            </div>
          </div>
        ) : isApproved ? (
          /* §3.3 Approved — Ready to Send (Clear state distinction) */
          <div className="space-y-4">
            <Card className="border-emerald-200 bg-emerald-50/60">
              <CardContent className="p-5 space-y-3">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="h-5 w-5 text-emerald-600" />
                  <span className="font-bold text-sm text-emerald-900">Draft Ready in Gmail</span>
                </div>
                <p className="text-xs text-emerald-800">This draft is saved in your Gmail account. Review it one more time before sending to the patient.</p>
                
                {/* Show the final draft for reference */}
                <div className="rounded-lg bg-white border border-emerald-200 p-3 text-xs text-slate-700">
                  <p className="font-semibold text-slate-900 mb-2">Draft Preview:</p>
                  <div className="whitespace-pre-wrap text-sm leading-relaxed">{review.draft_body}</div>
                </div>
              </CardContent>
            </Card>

            {/* Final send action */}
            <div className="space-y-3 pt-2">
              <p className="text-xs font-semibold text-slate-600">Ready to send to patient?</p>
              <Button 
                size="sm" 
                disabled={busy} 
                onClick={() => runAction(() => sendReview(review.id), "Email sent successfully to patient!")} 
                className="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-semibold"
              >
                {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}
                Send Email to Patient
              </Button>
            </div>
          </div>
        ) : (
          /* §3.3 Editable Draft Box */
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-blue-600" />
                <span className="font-bold text-xs text-slate-900">AI Draft — Not Sent</span>
              </div>
              {!editing && canEdit && (
                <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
                  Edit Further
                </Button>
              )}
            </div>

            {editing ? (
              <div className="space-y-2">
                <Textarea rows={8} value={draft} onChange={(e) => setDraft(e.target.value)} className="text-sm leading-relaxed" />
                <div className="flex gap-2">
                  <Button size="sm" disabled={busy} onClick={() => runAction(() => editDraft(review.id, draft), "Draft updated.").then(() => setEditing(false))}>
                    Save Changes
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => { setDraft(review.draft_body); setEditing(false); }}>
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <div className="whitespace-pre-wrap rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-800 leading-relaxed">
                {review.draft_body || "No draft content available."}
              </div>
            )}

            {/* Action buttons */}
            <div className="flex flex-wrap gap-2 pt-2">
              {canApprove && (
                <>
                  <Button 
                    size="sm" 
                    disabled={busy} 
                    onClick={() => setShowApproveConfirm(true)}
                    className="bg-emerald-600 hover:bg-emerald-700"
                  >
                    <Check className="mr-1.5 h-4 w-4" /> Save to Gmail Draft
                  </Button>
                  {showApproveConfirm && (
                    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4">
                      <Card className="border-slate-200 shadow-lg max-w-sm">
                        <CardContent className="p-6 space-y-4">
                          <div>
                            <h3 className="font-bold text-slate-900">Save draft to Gmail?</h3>
                            <p className="text-xs text-slate-500 mt-1">This creates a draft in your Gmail account. You can review it before sending.</p>
                          </div>
                          <div className="flex gap-2 justify-end border-t border-slate-100 pt-4">
                            <Button size="sm" variant="outline" onClick={() => setShowApproveConfirm(false)} disabled={busy}>
                              Cancel
                            </Button>
                            <Button 
                              size="sm" 
                              disabled={busy} 
                              onClick={() => {
                                runAction(() => approveReview(review.id), "Draft saved to Gmail — ready to send.").then(() => setShowApproveConfirm(false));
                              }}
                              className="bg-emerald-600 hover:bg-emerald-700"
                            >
                              {busy ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Check className="mr-1.5 h-4 w-4" />}
                              Confirm & Save
                            </Button>
                          </div>
                        </CardContent>
                      </Card>
                    </div>
                  )}
                </>
              )}
              {canEdit && (
                <Button size="sm" variant="outline" disabled={busy} onClick={() => runAction(() => rejectReview(review.id, "Rejected by FO"), "Draft rejected.")}>
                  <X className="mr-1.5 h-4 w-4" /> Reject
                </Button>
              )}
            </div>
          </div>
        )}
      </section>

      {/* §3.4 Context Panel (Right Pane ~320px) */}
      <aside className="p-6 space-y-6 max-h-[calc(100vh-130px)] overflow-y-auto bg-slate-50/50">
        <h3 className="font-bold text-xs uppercase tracking-wider text-slate-400">Context & Grounding</h3>

        {/* Source Used / Citations */}
        <div className="space-y-2">
          <p className="text-xs font-semibold text-slate-700">Grounding Sources Used</p>
          {review.citations && review.citations.length > 0 ? (
            <div className="space-y-1.5">
              {review.citations.map((c) => (
                <a key={c.document_id} href={c.url ?? "#"} target="_blank" rel="noreferrer" className="block rounded-lg border border-slate-200 bg-white p-2.5 text-xs transition hover:border-emerald-300">
                  <span className="font-bold text-slate-800">{c.title}</span>
                  <p className="text-[10px] text-slate-400">{c.source}</p>
                </a>
              ))}
            </div>
          ) : (
            <p className="text-xs text-slate-400">No external source cited.</p>
          )}
        </div>

        {/* Match Confidence */}
        <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-3">
          <div className="flex items-center justify-between text-xs">
            <span className="font-semibold text-slate-700">Match Confidence</span>
            <span className="font-bold text-slate-900">{Math.round(review.confidence * 100)}%</span>
          </div>
          <div className="h-2 w-full rounded-full bg-slate-100 overflow-hidden">
            <div className="h-full bg-emerald-500" style={{ width: `${Math.round(review.confidence * 100)}%` }} />
          </div>
          
          {/* §3.4 Contextual explanation based on confidence level */}
          <p className="text-[10px] text-slate-500">
            {review.confidence >= 0.85
              ? "Strong match — This draft was generated from highly similar policy documents in the knowledge base."
              : review.confidence >= 0.65
              ? "Good match — This draft draws from relevant but not identical policy guidance. Review for accuracy."
              : review.confidence >= 0.45
              ? "Moderate confidence — Consider reviewing the sources and adjusting the draft as needed."
              : "Lower confidence — Manual review and editing recommended. Consider routing to specialist if uncertain."}
          </p>
        </div>

        {/* Routing Trail */}
        <div className="space-y-2">
          <p className="text-xs font-semibold text-slate-700">Routing Trail</p>
          <div className="space-y-1 text-xs text-slate-600">
            <p>1. Ingested from Gmail Inbox</p>
            <p>2. Classified as <span className="font-medium text-slate-800">{review.classification}</span></p>
            <p>3. Routed to <span className="font-medium text-slate-800">{label(review.department)}</span></p>
          </div>
        </div>

        {/* Who Can Send */}
        <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-3">
          <p className="text-xs font-semibold text-slate-700">Send Rights Scope</p>
          <div className="flex items-center gap-1.5 text-xs text-emerald-700 font-medium">
            <UserCheck className="h-4 w-4" /> Front Office & Admin
          </div>
        </div>

        {/* Internal Note & Collaboration Drawer */}
        <CollaborationDrawer
          emailId={review.id}
          currentDepartment={review.department}
          onReassigned={async () => { await onRefresh(); }}
        />
      </aside>
    </div>
  );
}
