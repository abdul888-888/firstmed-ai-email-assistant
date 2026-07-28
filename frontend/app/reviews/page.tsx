"use client";

// Force Vercel rebuild - ensure DashboardLayout is rendered
import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  FileText,
  Loader2,
  Mail,
  MessageSquare,
  Send,
  ShieldAlert,
  ShieldCheck,
  User,
  XCircle,
  RefreshCw,
  Stethoscope,
  Filter,
  ChevronRight,
  CheckCheck,
  MoreHorizontal,
  Eye,
  Edit3,
  Trash2,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { DashboardLayout } from "@/components/dashboard-layout";
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
  classification: "ADMIN_DIRECT_REPLY" | "NEEDS_PHYSICIAN_REVIEW" | "IRRELEVANT";
  confidence: number;
  reason: string;
  summary: string;
  draft_body: string;
  citations: Citation[];
  status: "pending" | "awaiting_specialist_input" | "specialist_input_received" | "approved" | "rejected" | "sent" | "irrelevant";
  gmail_draft_id: string | null;
  assigned_to: string | null;
  specialist_input: string | null;
  specialist_id: string | null;
  specialist_input_at: string | null;
  created_at: string;
};

const base = `${API_BASE_URL}/api/v1/reviews`;

class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function api(path: string, init?: RequestInit) {
  const res = await fetch(`${base}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...authHeader(), ...(init?.headers ?? {}) },
  });
  if (res.status === 401) {
    throw new ApiError("Unauthorized", 401);
  }
  const body = await res.json();
  if (!res.ok) {
    throw new ApiError(body.detail ?? `HTTP ${res.status}`, res.status);
  }
  return body;
}

async function listReviews(status?: string) {
  const query = status ? `?status=${status}` : "";
  return api(`${query}`);
}

async function approveReview(review: Review) {
  return api(`/${review.id}/approve`, { method: "POST" });
}

async function rejectReview(review: Review, reason: string) {
  return api(`/${review.id}/reject`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

async function sendReview(review: Review) {
  return api(`/${review.id}/send`, { method: "POST" });
}

async function editDraft(review: Review, draft_body: string) {
  return api(`/${review.id}`, {
    method: "PATCH",
    body: JSON.stringify({ draft_body }),
  });
}

async function submitSpecialistInput(review: Review, specialist_input: string, should_revise: boolean) {
  return api(`/${review.id}/specialist-input`, {
    method: "POST",
    body: JSON.stringify({ specialist_input, should_revise_draft: should_revise }),
  });
}

const statusConfig = {
  pending: { color: "bg-blue-100", text: "text-blue-800", icon: Clock, label: "Pending" },
  awaiting_specialist_input: { color: "bg-yellow-100", text: "text-yellow-800", icon: Stethoscope, label: "Awaiting Specialist" },
  specialist_input_received: { color: "bg-purple-100", text: "text-purple-800", icon: MessageSquare, label: "Specialist Input Received" },
  approved: { color: "bg-green-100", text: "text-green-800", icon: CheckCircle2, label: "Approved" },
  rejected: { color: "bg-red-100", text: "text-red-800", icon: XCircle, label: "Rejected" },
  sent: { color: "bg-gray-100", text: "text-gray-800", icon: Send, label: "Sent" },
  irrelevant: { color: "bg-slate-100", text: "text-slate-800", icon: FileText, label: "Irrelevant" },
};

const classificationConfig = {
  ADMIN_DIRECT_REPLY: { icon: ShieldCheck, label: "Admin Reply", color: "text-blue-600" },
  NEEDS_PHYSICIAN_REVIEW: { icon: ShieldAlert, label: "Needs Physician Review", color: "text-orange-600" },
  IRRELEVANT: { icon: AlertTriangle, label: "Irrelevant", color: "text-gray-600" },
};

const departmentConfig = {
  front_office: { label: "Front Office", color: "bg-blue-50" },
  nurse: { label: "Nurse", color: "bg-green-50" },
  specialist: { label: "Specialist", color: "bg-purple-50" },
};

function ReviewCard({ review, onAction }: { review: Review; onAction: (type: string, review: Review, data?: any) => void }) {
  const status = statusConfig[review.status as keyof typeof statusConfig];
  const classification = classificationConfig[review.classification as keyof typeof classificationConfig];
  const department = departmentConfig[review.department as keyof typeof departmentConfig];
  const StatusIcon = status?.icon || Clock;
  const ClassIcon = classification?.icon || FileText;

  return (
    <Card className="hover:shadow-lg transition-shadow">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-2">
              <Badge className={cn(status?.color, status?.text)}>
                <StatusIcon className="w-3 h-3 mr-1" />
                {status?.label}
              </Badge>
              <Badge variant="outline" className={cn(department?.color)}>
                {department?.label}
              </Badge>
            </div>
            <p className="font-semibold text-lg text-gray-900 line-clamp-2">{review.subject || "(no subject)"}</p>
            <p className="text-sm text-gray-600 mt-1">From: {review.sender}</p>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <span className="text-gray-500">Intent:</span>
            <p className="font-medium">{review.intent}</p>
          </div>
          <div>
            <span className="text-gray-500">Urgency:</span>
            <p className="font-medium">{review.urgency}</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <ClassIcon className={cn("w-4 h-4", classification?.color)} />
          <span className="text-sm">{classification?.label}</span>
          <span className="text-sm text-gray-500">• {(review.confidence * 100).toFixed(0)}% confident</span>
        </div>

        <p className="text-sm text-gray-700 bg-gray-50 p-3 rounded">{review.summary}</p>

        {review.status !== "irrelevant" && (
          <>
            {review.draft_body && (
              <div className="border-t pt-3">
                <p className="text-sm font-medium text-gray-900 mb-2">Draft Reply:</p>
                <p className="text-sm text-gray-700 bg-gray-50 p-3 rounded line-clamp-3">{review.draft_body}</p>
              </div>
            )}

            {review.specialist_input && (
              <div className="border-t pt-3 bg-purple-50 p-3 rounded">
                <p className="text-sm font-medium text-purple-900 mb-2">Specialist Input:</p>
                <p className="text-sm text-purple-800">{review.specialist_input}</p>
              </div>
            )}
          </>
        )}

        {review.citations.length > 0 && (
          <div className="border-t pt-3">
            <p className="text-xs font-medium text-gray-600 mb-2">Sources:</p>
            <div className="space-y-1">
              {review.citations.map((c) => (
                <a
                  key={c.document_id}
                  href={c.url || "#"}
                  className="text-xs text-blue-600 hover:underline block"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {c.source}: {c.title}
                </a>
              ))}
            </div>
          </div>
        )}

        <div className="border-t pt-4">
          <ActionButtons review={review} onAction={onAction} />
        </div>
      </CardContent>
    </Card>
  );
}

function ActionButtons({ review, onAction }: { review: Review; onAction: (type: string, review: Review, data?: any) => void }) {
  if (review.status === "irrelevant") {
    return (
      <div className="flex gap-2">
        <Button variant="outline" size="sm" className="w-full" disabled>
          This email was marked as irrelevant
        </Button>
      </div>
    );
  }

  if (review.status === "awaiting_specialist_input") {
    return (
      <div className="space-y-2">
        <p className="text-xs text-gray-600 font-medium">Awaiting specialist input...</p>
        <Button
          size="sm"
          className="w-full bg-purple-600 hover:bg-purple-700"
          onClick={() => onAction("specialist_input", review)}
        >
          <MessageSquare className="w-4 h-4 mr-2" />
          Provide Input
        </Button>
      </div>
    );
  }

  if (review.status === "specialist_input_received") {
    return (
      <div className="space-y-2">
        <Button size="sm" variant="outline" className="w-full" onClick={() => onAction("edit", review)}>
          <Edit3 className="w-4 h-4 mr-2" />
          Review & Edit Draft
        </Button>
        <div className="flex gap-2">
          <Button
            size="sm"
            className="flex-1"
            onClick={() => onAction("approve", review)}
          >
            <CheckCircle2 className="w-4 h-4 mr-1" />
            Approve
          </Button>
          <Button size="sm" variant="destructive" className="flex-1" onClick={() => onAction("reject", review)}>
            <XCircle className="w-4 h-4 mr-1" />
            Reject
          </Button>
        </div>
      </div>
    );
  }

  if (review.status === "approved" && !review.gmail_draft_id) {
    return (
      <Button size="sm" className="w-full" onClick={() => onAction("send", review)}>
        <Send className="w-4 h-4 mr-2" />
        Send Email
      </Button>
    );
  }

  if (review.status === "approved" || review.status === "pending") {
    return (
      <div className="flex gap-2">
        <Button
          size="sm"
          variant="outline"
          className="flex-1"
          onClick={() => onAction("edit", review)}
        >
          <Edit3 className="w-4 h-4 mr-1" />
          Edit
        </Button>
        <Button
          size="sm"
          className="flex-1"
          onClick={() => onAction("approve", review)}
        >
          <CheckCircle2 className="w-4 h-4 mr-1" />
          Approve
        </Button>
        <Button size="sm" variant="destructive" className="flex-1" onClick={() => onAction("reject", review)}>
          <XCircle className="w-4 h-4 mr-1" />
          Reject
        </Button>
      </div>
    );
  }

  return (
    <div className="text-xs text-gray-500">
      {review.status === "sent" && "Email sent ✓"}
      {review.status === "rejected" && "Email rejected"}
    </div>
  );
}

export default function ReviewsPage() {
  const [reviews, setReviews] = useState<Review[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedStatus, setSelectedStatus] = useState<string | null>(null);
  const [editingReview, setEditingReview] = useState<Review | null>(null);
  const [editingDraft, setEditingDraft] = useState<string>("");
  const [rejectReason, setRejectReason] = useState("");
  const [specialistInput, setSpecialistInput] = useState("");
  const [actionInProgress, setActionInProgress] = useState(false);

  const loadReviews = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await listReviews(selectedStatus || undefined);
      setReviews(Array.isArray(data) ? data : data.reviews || []);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          await startGoogleSignIn();
          return;
        }
        setError(err.message);
      } else {
        setError("Failed to load reviews");
      }
    } finally {
      setLoading(false);
    }
  }, [selectedStatus]);

  useEffect(() => {
    loadReviews();
  }, [loadReviews]);

  const handleAction = async (type: string, review: Review, data?: any) => {
    setActionInProgress(true);
    try {
      let result;
      switch (type) {
        case "approve":
          result = await approveReview(review);
          break;
        case "reject":
          result = await rejectReview(review, rejectReason || "No reason provided");
          setRejectReason("");
          break;
        case "send":
          result = await sendReview(review);
          break;
        case "edit":
          setEditingReview(review);
          setEditingDraft(review.draft_body);
          return;
        case "specialist_input":
          setEditingReview(review);
          setSpecialistInput("");
          return;
        case "save_draft":
          result = await editDraft(review, editingDraft);
          setEditingReview(null);
          break;
        case "submit_specialist_input":
          result = await submitSpecialistInput(review, specialistInput, true);
          setEditingReview(null);
          setSpecialistInput("");
          break;
        default:
          return;
      }
      await loadReviews();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setActionInProgress(false);
    }
  };

  const statuses = Object.entries(statusConfig).map(([key, val]) => ({
    key,
    label: val.label,
  }));

  const filteredReviews = selectedStatus
    ? reviews.filter((r) => r.status === selectedStatus)
    : reviews;

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Email Reviews</h1>
            <p className="text-gray-600 mt-1">Manage and respond to patient emails</p>
          </div>
          <Button onClick={loadReviews} disabled={loading} variant="outline">
            <RefreshCw className={cn("w-4 h-4 mr-2", loading && "animate-spin")} />
            Refresh
          </Button>
        </div>

        {/* Status Filter */}
        <div className="flex gap-2 flex-wrap">
          <Button
            variant={selectedStatus === null ? "default" : "outline"}
            size="sm"
            onClick={() => setSelectedStatus(null)}
          >
            <Filter className="w-4 h-4 mr-2" />
            All ({reviews.length})
          </Button>
          {statuses.map((s) => {
            const count = reviews.filter((r) => r.status === s.key).length;
            return (
              <Button
                key={s.key}
                variant={selectedStatus === s.key ? "default" : "outline"}
                size="sm"
                onClick={() => setSelectedStatus(s.key)}
              >
                {s.label} ({count})
              </Button>
            );
          })}
        </div>

        {/* Error Message */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-800">
            {error}
          </div>
        )}

        {/* Edit Modal */}
        {editingReview && editingReview.status !== "awaiting_specialist_input" && (
          <Card className="border-2 border-blue-500">
            <CardHeader>
              <CardTitle>Edit Draft Reply</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="text-sm font-medium text-gray-700">Draft Body</label>
                <Textarea
                  value={editingDraft}
                  onChange={(e) => setEditingDraft(e.target.value)}
                  className="mt-2 font-mono text-sm"
                  rows={8}
                />
              </div>
              <div className="flex gap-2">
                <Button
                  onClick={() => handleAction("save_draft", editingReview)}
                  disabled={actionInProgress}
                >
                  <CheckCheck className="w-4 h-4 mr-2" />
                  Save Draft
                </Button>
                <Button variant="outline" onClick={() => setEditingReview(null)}>
                  Cancel
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Specialist Input Modal */}
        {editingReview && editingReview.status === "awaiting_specialist_input" && (
          <Card className="border-2 border-purple-500">
            <CardHeader>
              <CardTitle>Provide Specialist Input</CardTitle>
              <p className="text-sm text-gray-600 mt-2">
                Email from {editingReview.sender} requires your clinical input.
              </p>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <p className="font-medium mb-2">Original Email:</p>
                <p className="text-sm bg-gray-50 p-3 rounded">{editingReview.subject}</p>
              </div>
              {editingReview.draft_body && (
                <div>
                  <p className="font-medium mb-2">Current Draft:</p>
                  <p className="text-sm bg-gray-50 p-3 rounded">{editingReview.draft_body}</p>
                </div>
              )}
              <div>
                <label className="text-sm font-medium text-gray-700">Your Clinical Input</label>
                <Textarea
                  placeholder="Provide your specialist guidance, recommendations, or changes needed..."
                  value={specialistInput}
                  onChange={(e) => setSpecialistInput(e.target.value)}
                  className="mt-2"
                  rows={6}
                />
              </div>
              <div className="flex gap-2">
                <Button
                  onClick={() => handleAction("submit_specialist_input", editingReview)}
                  disabled={actionInProgress || !specialistInput}
                  className="bg-purple-600 hover:bg-purple-700"
                >
                  <Stethoscope className="w-4 h-4 mr-2" />
                  Submit Input
                </Button>
                <Button variant="outline" onClick={() => setEditingReview(null)}>
                  Cancel
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Reviews Grid */}
        <div className="space-y-4">
          {loading ? (
            Array.from({ length: 3 }).map((_, i) => (
              <Card key={i}>
                <CardHeader>
                  <Skeleton className="h-6 w-1/2" />
                </CardHeader>
                <CardContent>
                  <Skeleton className="h-20" />
                </CardContent>
              </Card>
            ))
          ) : filteredReviews.length === 0 ? (
            <Card>
              <CardContent className="py-12 text-center">
                <Mail className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                <p className="text-gray-600">No reviews found</p>
              </CardContent>
            </Card>
          ) : (
            filteredReviews.map((review) => (
              <ReviewCard key={review.id} review={review} onAction={handleAction} />
            ))
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
