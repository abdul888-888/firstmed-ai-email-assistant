"use client";

import { useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, Clock, Loader2, PhoneCall, Send, Stethoscope } from "lucide-react";

import { DashboardLayout } from "@/components/dashboard-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { listReviews, submitSpecialistInput, type Review } from "@/lib/api";
import { addReviewNote } from "@/lib/admin";

export default function ClinicalReviewerPage() {
  const [reviews, setReviews] = useState<Review[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState<Record<string, boolean>>({});
  const [messages, setMessages] = useState<Record<string, string>>({});

  const loadReviews = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listReviews("awaiting_specialist_input", 100);
      setReviews(res.reviews);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load clinical queue");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadReviews();
  }, []);

  const handleInputChange = (id: string, text: string) => {
    setInputs((prev) => ({ ...prev, [id]: text }));
  };

  const handleSendAnswer = async (id: string) => {
    const text = inputs[id]?.trim();
    if (!text) return;

    setSubmitting((prev) => ({ ...prev, [id]: true }));
    try {
      await submitSpecialistInput(id, text, true);
      setMessages((prev) => ({ ...prev, [id]: "Answer submitted to Front Office." }));
      setTimeout(() => {
        setReviews((prev) => prev.filter((r) => r.id !== id));
      }, 1200);
    } catch (err) {
      setMessages((prev) => ({ ...prev, [id]: err instanceof Error ? err.message : "Failed to submit answer" }));
    } finally {
      setSubmitting((prev) => ({ ...prev, [id]: false }));
    }
  };

  const handlePhoneEscalation = async (id: string) => {
    setSubmitting((prev) => ({ ...prev, [id]: true }));
    try {
      await addReviewNote(id, "[CLINICAL ESCALATION] Flagged for direct phone call with patient due to clinical sensitivity.");
      setMessages((prev) => ({ ...prev, [id]: "Escalated for direct phone call." }));
      setTimeout(() => {
        setReviews((prev) => prev.filter((r) => r.id !== id));
      }, 1200);
    } catch (err) {
      setMessages((prev) => ({ ...prev, [id]: "Failed to flag phone escalation" }));
    } finally {
      setSubmitting((prev) => ({ ...prev, [id]: false }));
    }
  };

  return (
    <DashboardLayout>
      <div className="min-h-screen bg-slate-50 p-6 md:p-10">
        <div className="mx-auto max-w-4xl space-y-6">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-slate-200 pb-5">
            <div>
              <div className="flex items-center gap-2">
                <Stethoscope className="h-6 w-6 text-emerald-600" />
                <h1 className="text-2xl font-bold tracking-tight text-slate-900">Questions needing your input</h1>
              </div>
              <p className="mt-1 text-sm text-slate-500">Provide medical/specialist guidance for front office response generation.</p>
            </div>
            <Badge className="bg-amber-100 text-amber-800 border-amber-200 text-sm py-1 px-3">
              {reviews.length} Pending
            </Badge>
          </div>

          {error && <div className="rounded-md bg-rose-50 p-4 text-sm text-rose-700">{error}</div>}

          {loading ? (
            <div className="py-12 text-center text-slate-500">
              <Loader2 className="mx-auto h-6 w-6 animate-spin mb-2" />
              Loading clinical queue...
            </div>
          ) : reviews.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-12 text-center">
              <CheckCircle2 className="mx-auto h-10 w-10 text-emerald-500 mb-3" />
              <h3 className="text-lg font-semibold text-slate-900">All caught up!</h3>
              <p className="mt-1 text-sm text-slate-500">There are currently no clinical questions awaiting your review.</p>
            </div>
          ) : (
            <div className="space-y-6">
              {reviews.map((item) => (
                <Card key={item.id} className="border-slate-200 shadow-sm transition hover:shadow-md">
                  <CardHeader className="bg-slate-50/70 border-b border-slate-100">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Patient Inquiry</span>
                        <CardTitle className="text-lg font-bold text-slate-900">{item.subject || "Clinical Question"}</CardTitle>
                        <p className="text-xs text-slate-500">From {item.sender || "Unknown Sender"}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge className="bg-amber-50 text-amber-700 border-amber-200">
                          <Clock className="mr-1 h-3 w-3" /> Waiting input
                        </Badge>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="p-6 space-y-4">
                    {/* Patient Question */}
                    <div className="rounded-xl border border-slate-200 bg-white p-4">
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-1">Clinical Context / Inquiry</p>
                      <p className="text-sm leading-relaxed text-slate-800">{item.summary || item.reason || "Patient requested specialist guidance."}</p>
                    </div>

                    {messages[item.id] && (
                      <div className="rounded-md bg-emerald-50 p-3 text-sm font-medium text-emerald-800">
                        {messages[item.id]}
                      </div>
                    )}

                    {/* Guidance Textbox */}
                    <div className="space-y-2">
                      <label className="text-xs font-semibold text-slate-700">Your Clinical Answer / Instructions</label>
                      <Textarea
                        rows={4}
                        placeholder="Provide medical guidance to be incorporated into the patient reply..."
                        value={inputs[item.id] || ""}
                        onChange={(e) => handleInputChange(item.id, e.target.value)}
                        className="min-h-[100px]"
                      />
                    </div>

                    {/* Action buttons */}
                    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handlePhoneEscalation(item.id)}
                        disabled={submitting[item.id]}
                        className="text-rose-700 border-rose-200 hover:bg-rose-50"
                      >
                        <PhoneCall className="mr-2 h-4 w-4 text-rose-600" />
                        Needs a phone call instead
                      </Button>

                      <Button
                        size="sm"
                        onClick={() => handleSendAnswer(item.id)}
                        disabled={submitting[item.id] || !inputs[item.id]?.trim()}
                        className="bg-emerald-600 hover:bg-emerald-700"
                      >
                        {submitting[item.id] ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}
                        Send answer to Front Office
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
