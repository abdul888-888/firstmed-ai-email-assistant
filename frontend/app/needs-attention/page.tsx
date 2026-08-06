"use client";

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Archive,
  ArrowRight,
  Bell,
  Check,
  CheckCircle2,
  Clock,
  HelpCircle,
  Loader2,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  Zap,
} from "lucide-react";

import { DashboardLayout } from "@/components/dashboard-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  getKnowledgeGaps,
  getStalledItems,
  getTriageItems,
  performTriageAction,
  sendNudge,
  type KnowledgeGap,
  type StalledItem,
  type TriageItem,
} from "@/lib/api";

export default function NeedsAttentionPage() {
  const [gaps, setGaps] = useState<KnowledgeGap[]>([]);
  const [stalled, setStalled] = useState<StalledItem[]>([]);
  const [triage, setTriage] = useState<TriageItem[]>([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState<Record<string, boolean>>({});
  const [messages, setMessages] = useState<Record<string, string>>({});

  const loadAll = async () => {
    setLoading(true);
    setError(null);
    try {
      const [gapsRes, stalledRes, triageRes] = await Promise.all([
        getKnowledgeGaps(),
        getStalledItems(),
        getTriageItems(),
      ]);
      setGaps(gapsRes.gaps);
      setStalled(stalledRes.stalled);
      setTriage(triageRes.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load Needs Attention workspace.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadAll();
  }, []);

  const handleNudge = async (item: StalledItem) => {
    setActionBusy((prev) => ({ ...prev, [item.id]: true }));
    try {
      const res = await sendNudge(item.id);
      setMessages((prev) => ({ ...prev, [item.id]: res.message }));
      setStalled((prev) =>
        prev.map((s) => (s.id === item.id ? { ...s, nudge_sent: true } : s))
      );
    } catch (err) {
      setMessages((prev) => ({ ...prev, [item.id]: "Failed to send nudge" }));
    } finally {
      setActionBusy((prev) => ({ ...prev, [item.id]: false }));
    }
  };

  const handleTriageAction = async (itemId: string, action: "accept" | "reject") => {
    setActionBusy((prev) => ({ ...prev, [itemId]: true }));
    try {
      await performTriageAction(itemId, action);
      setTriage((prev) => prev.filter((t) => t.id !== itemId));
    } catch (err) {
      setMessages((prev) => ({ ...prev, [itemId]: "Triage action failed" }));
    } finally {
      setActionBusy((prev) => ({ ...prev, [itemId]: false }));
    }
  };

  return (
    <DashboardLayout>
      <div className="min-h-screen bg-slate-50 p-6 md:p-10">
        <div className="mx-auto max-w-6xl space-y-10">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-slate-200 pb-5">
            <div>
              <div className="flex items-center gap-2">
                <ShieldAlert className="h-7 w-7 text-amber-600" />
                <h1 className="text-2xl font-bold tracking-tight text-slate-900">Needs Attention</h1>
              </div>
              <p className="mt-1 text-sm text-slate-500">System gaps, stalled workflows, and quick triage items.</p>
            </div>
            <Button variant="outline" size="sm" onClick={() => void loadAll()} disabled={loading}>
              <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} /> Refresh Triage
            </Button>
          </div>

          {error && <div className="rounded-md bg-rose-50 p-4 text-sm text-rose-700">{error}</div>}

          {loading ? (
            <div className="py-16 text-center text-slate-500">
              <Loader2 className="mx-auto h-8 w-8 animate-spin mb-3 text-slate-400" />
              Loading Needs Attention workspace...
            </div>
          ) : (
            <div className="space-y-10">
              {/* 5.1 Recurring Knowledge Gaps */}
              <section className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <HelpCircle className="h-5 w-5 text-indigo-600" />
                    <h2 className="text-lg font-bold text-slate-900">5.1 Recurring Knowledge Gaps</h2>
                  </div>
                  <Badge className="bg-indigo-50 text-indigo-700 border-indigo-200">{gaps.length} Topics</Badge>
                </div>
                <p className="text-xs text-slate-500">Unanswered questions from Notion KB grouped by topic with auto-escalation thresholds.</p>

                <div className="grid gap-4 md:grid-cols-2">
                  {gaps.map((gap) => (
                    <Card 
                      key={gap.id} 
                      className={gap.escalated ? "border-amber-200 bg-amber-50/60 shadow-md" : "border-slate-200 shadow-sm"}
                    >
                      <CardContent className="p-5 space-y-3">
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex-1">
                            <h3 className="font-semibold text-slate-900 text-sm leading-snug">{gap.topic}</h3>
                            {gap.escalated && (
                              <p className="text-xs text-amber-700 font-medium mt-1">
                                ⚠️ Escalated to {gap.escalated_to}
                              </p>
                            )}
                          </div>
                          <Badge className={gap.escalated ? "shrink-0 bg-amber-100 border-amber-300 text-amber-900 font-bold" : "shrink-0 bg-slate-100 border-slate-200 text-slate-700 font-bold"}>
                            {gap.occurrences} asks
                          </Badge>
                        </div>
                        {gap.escalated && (
                          <div className="inline-flex items-center gap-1.5 rounded-full border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-800 ring-2 ring-amber-100">
                            <AlertTriangle className="h-3.5 w-3.5 text-amber-600" />
                            Auto-escalated — Action required
                          </div>
                        )}
                        <p className="text-[11px] text-slate-500">Last recorded query: {new Date(gap.last_asked).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</p>
                      </CardContent>
                    </Card>
                  ))}
                  {gaps.length === 0 && (
                    <div className="col-span-2 rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
                      No knowledge gaps recorded — great job keeping the KB complete!
                    </div>
                  )}
                </div>
              </section>

              {/* 5.2 Stalled Items */}
              <section className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Clock className="h-5 w-5 text-rose-600" />
                    <h2 className="text-lg font-bold text-slate-900">5.2 Stalled Items</h2>
                  </div>
                  <Badge className="bg-rose-50 text-rose-700 border-rose-200">{stalled.length} Stalled</Badge>
                </div>
                <p className="text-xs text-slate-500">Items waiting on staff response beyond SLA time limits.</p>

                <div className="space-y-3">
                  {stalled.map((item) => (
                    <Card 
                      key={item.id} 
                      className="border-rose-200 bg-rose-50/40 shadow-sm transition hover:shadow-md hover:border-rose-300"
                    >
                      <CardContent className="p-5 space-y-3">
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex-1 space-y-1">
                            <div className="flex items-center gap-2">
                              <span className="font-semibold text-slate-900 text-sm">{item.subject}</span>
                              <Badge className="bg-rose-100 text-rose-900 border-rose-300 font-bold">
                                {item.elapsed_hours}h / {item.sla_limit_hours}h SLA
                              </Badge>
                            </div>
                            <p className="text-xs text-slate-600">
                              From <span className="font-medium">{item.sender}</span> • Waiting on: <span className="font-semibold text-rose-900">{item.waiting_on}</span>
                            </p>
                            {messages[item.id] && (
                              <p className="text-xs font-semibold text-emerald-700 mt-1">✓ {messages[item.id]}</p>
                            )}
                          </div>
                          <Button
                            size="sm"
                            onClick={() => handleNudge(item)}
                            disabled={item.nudge_sent}
                            className={item.nudge_sent 
                              ? "bg-slate-200 text-slate-600 cursor-not-allowed" 
                              : "bg-rose-600 hover:bg-rose-700 text-white"
                            }
                          >
                            {item.nudge_sent ? (
                              <>
                                <Check className="mr-1.5 h-4 w-4" /> Nudge Sent
                              </>
                            ) : (
                              <>
                                <Bell className="mr-1.5 h-4 w-4" /> Send Nudge
                              </>
                            )}
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                  {stalled.length === 0 && (
                    <div className="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
                      No stalled items — all workflows are flowing smoothly!
                    </div>
                  )}
                </div>
              </section>

              {/* 5.3 Quick Triage */}
              <section className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Zap className="h-5 w-5 text-emerald-600" />
                    <h2 className="text-lg font-bold text-slate-900">5.3 Quick Triage</h2>
                  </div>
                  <Badge className="bg-emerald-50 text-emerald-700 border-emerald-200">{triage.length} Fast Review</Badge>
                </div>
                <p className="text-xs text-slate-500">Low-confidence or vendor/spam messages needing fast one-tap triage.</p>

                <div className="space-y-3">
                  {triage.map((item) => (
                    <Card 
                      key={item.id} 
                      className="border-slate-200 shadow-sm transition hover:shadow-md hover:border-slate-300"
                    >
                      <CardContent className="p-4 flex items-center justify-between gap-4">
                        <div className="flex-1 space-y-1.5">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-slate-900 text-sm">{item.subject}</span>
                            <Badge className={
                              item.confidence >= 0.7 
                                ? "bg-slate-100 text-slate-700"
                                : item.confidence >= 0.5
                                ? "bg-amber-100 text-amber-700"
                                : "bg-rose-100 text-rose-700"
                            }>
                              {Math.round(item.confidence * 100)}% Confidence
                            </Badge>
                          </div>
                          <p className="text-xs text-slate-500">From <span className="font-medium">{item.sender}</span></p>
                          <p className="text-xs text-slate-600 line-clamp-2">{item.summary}</p>
                        </div>

                        <div className="flex items-center gap-2 shrink-0">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleTriageAction(item.id, "accept")}
                            disabled={actionBusy[item.id]}
                            className="text-slate-700 border-slate-300 hover:bg-slate-100"
                          >
                            <Archive className="h-4 w-4" />
                          </Button>
                          <Button
                            size="sm"
                            onClick={() => handleTriageAction(item.id, "reject")}
                            disabled={actionBusy[item.id]}
                            className="bg-slate-900 hover:bg-slate-800"
                          >
                            <ArrowRight className="h-4 w-4" />
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                  {triage.length === 0 && (
                    <div className="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
                      ✓ No low-confidence items to triage!
                    </div>
                  )}
                </div>
              </section>
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
