"use client";

import { useEffect, useState } from "react";
import { Calendar, CheckCircle2, Clock, Loader2, Send } from "lucide-react";

import { DashboardLayout } from "@/components/dashboard-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { editDraft, listReviews, sendReview, type Review } from "@/lib/api";

export default function BookingCoordinatorPage() {
  const [reviews, setReviews] = useState<Review[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [messages, setMessages] = useState<Record<string, string>>({});

  const loadQueue = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listReviews("pending", 100);
      // Filter for booking / scheduling related reviews
      const bookingItems = res.reviews.filter(
        (r) => r.department === "physiotherapy" || r.department === "bookings" || r.intent.includes("booking") || r.intent.includes("appointment")
      );
      setReviews(bookingItems.length ? bookingItems : res.reviews);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load booking queue");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadQueue();
  }, []);

  const handleDraftChange = (id: string, text: string) => {
    setDrafts((prev) => ({ ...prev, [id]: text }));
  };

  const handleSendResponse = async (item: Review) => {
    const customText = drafts[item.id] ?? item.draft_body;
    setBusy((prev) => ({ ...prev, [item.id]: true }));

    try {
      if (customText !== item.draft_body) {
        await editDraft(item.id, customText);
      }
      await sendReview(item.id);
      setMessages((prev) => ({ ...prev, [item.id]: "Response sent directly to patient!" }));
      setTimeout(() => {
        setReviews((prev) => prev.filter((r) => r.id !== item.id));
      }, 1200);
    } catch (err) {
      setMessages((prev) => ({ ...prev, [item.id]: err instanceof Error ? err.message : "Failed to send booking response" }));
    } finally {
      setBusy((prev) => ({ ...prev, [item.id]: false }));
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
                <Calendar className="h-6 w-6 text-teal-600" />
                <h1 className="text-2xl font-bold tracking-tight text-slate-900">Your queue</h1>
              </div>
              <p className="mt-1 text-sm text-slate-500">Manage and send direct scheduling responses to patients.</p>
            </div>
            <Badge className="bg-teal-100 text-teal-800 border-teal-200 text-sm py-1 px-3">
              {reviews.length} Booking Requests
            </Badge>
          </div>

          {error && <div className="rounded-md bg-rose-50 p-4 text-sm text-rose-700">{error}</div>}

          {loading ? (
            <div className="py-12 text-center text-slate-500">
              <Loader2 className="mx-auto h-6 w-6 animate-spin mb-2" />
              Loading booking queue...
            </div>
          ) : reviews.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-12 text-center">
              <CheckCircle2 className="mx-auto h-10 w-10 text-teal-500 mb-3" />
              <h3 className="text-lg font-semibold text-slate-900">All caught up!</h3>
              <p className="mt-1 text-sm text-slate-500">No booking requests pending in your queue.</p>
            </div>
          ) : (
            <div className="space-y-6">
              {reviews.map((item) => (
                <Card key={item.id} className="border-slate-200 shadow-sm transition hover:shadow-md">
                  <CardHeader className="bg-slate-50/70 border-b border-slate-100">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Booking Request</span>
                        <CardTitle className="text-lg font-bold text-slate-900">{item.subject || "Procedure / Slot Booking"}</CardTitle>
                        <p className="text-xs text-slate-500">From {item.sender || "Unknown Patient"}</p>
                      </div>
                      <Badge className="bg-blue-50 text-blue-700 border-blue-200">
                        <Clock className="mr-1 h-3 w-3" /> Direct Send Rights
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="p-6 space-y-4">
                    {/* Patient Request Summary */}
                    <div className="rounded-xl border border-slate-200 bg-white p-4">
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-1">Patient Request</p>
                      <p className="text-sm leading-relaxed text-slate-800">{item.summary || item.reason || "Patient requested appointment booking."}</p>
                    </div>

                    {messages[item.id] && (
                      <div className="rounded-md bg-emerald-50 p-3 text-sm font-medium text-emerald-800">
                        {messages[item.id]}
                      </div>
                    )}

                    {/* Proposed Reply Textbox */}
                    <div className="space-y-2">
                      <label className="text-xs font-semibold text-slate-700">Booking Reply to Patient</label>
                      <Textarea
                        rows={5}
                        value={drafts[item.id] ?? item.draft_body}
                        onChange={(e) => handleDraftChange(item.id, e.target.value)}
                        className="min-h-[120px]"
                      />
                    </div>

                    {/* Action button */}
                    <div className="flex justify-end border-t border-slate-100 pt-4">
                      <Button
                        size="sm"
                        onClick={() => handleSendResponse(item)}
                        disabled={busy[item.id]}
                        className="bg-teal-600 hover:bg-teal-700"
                      >
                        {busy[item.id] ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}
                        Send response directly
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
