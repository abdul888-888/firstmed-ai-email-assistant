"use client";

import { useState, useEffect } from "react";
import {
  MessageSquare,
  Send,
  UserCheck,
  Building2,
  Tag,
  Share2,
  Clock,
} from "lucide-react";
import { getToken, authHeader } from "@/lib/auth";
import { API_BASE_URL } from "@/lib/api";

interface InternalNoteItem {
  id: string;
  email_id: string;
  author_id: string;
  author_name: string;
  author_role: string;
  content: string;
  mentioned_department?: string;
  created_at?: string;
}

const DEPARTMENTS = [
  "FRONT_OFFICE",
  "PHYSIOTHERAPY",
  "GASTROENTEROLOGY",
  "LABORATORY",
  "NURSE_SPECIALIST",
];

export function CollaborationDrawer({
  emailId,
  currentDepartment,
  onReassigned,
}: {
  emailId: string;
  currentDepartment?: string;
  onReassigned?: (newDept: string) => void;
}) {
  const [notes, setNotes] = useState<InternalNoteItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [content, setContent] = useState("");
  const [mentionedDepartment, setMentionedDepartment] = useState("");
  const [targetDepartment, setTargetDepartment] = useState(
    currentDepartment || "PHYSIOTHERAPY"
  );
  const [reassignNote, setReassignNote] = useState("");
  const [reassigning, setReassigning] = useState(false);

  const fetchNotes = async () => {
    if (!emailId) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/email/${emailId}/notes`, {
        headers: { ...authHeader() },
      });
      if (res.ok) {
        const data = await res.json();
        setNotes(data.notes || []);
      }
    } catch (e) {
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchNotes();
  }, [emailId]);

  const handleAddNote = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!content.trim()) return;
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/email/${emailId}/notes`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeader(),
        },
        body: JSON.stringify({
          content,
          mentioned_department: mentionedDepartment || null,
        }),
      });
      if (res.ok) {
        setContent("");
        setMentionedDepartment("");
        fetchNotes();
      }
    } catch (e) {}
  };

  const handleReassign = async (e: React.FormEvent) => {
    e.preventDefault();
    setReassigning(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/email/${emailId}/reassign`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeader(),
        },
        body: JSON.stringify({
          target_department: targetDepartment,
          note: reassignNote,
        }),
      });
      if (res.ok) {
        setReassignNote("");
        fetchNotes();
        if (onReassigned) onReassigned(targetDepartment);
      }
    } catch (e) {
    } finally {
      setReassigning(false);
    }
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-6 shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-100 pb-3">
        <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
          <MessageSquare className="h-5 w-5 text-indigo-600" />
          Internal Notes & Department Transfer
        </h3>
        <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-slate-100 text-slate-600 border border-slate-200 flex items-center gap-1">
          <Building2 className="h-3 w-3" />
          Owner: {currentDepartment || "FRONT_OFFICE"}
        </span>
      </div>

      {/* Transfer Department Form */}
      <form onSubmit={handleReassign} className="bg-indigo-50/60 rounded-lg p-4 border border-indigo-100 space-y-3">
        <div className="flex items-center gap-2 text-xs font-bold text-indigo-900">
          <Share2 className="h-4 w-4 text-indigo-600" />
          Re-Assign Target Department
        </div>
        <div className="grid grid-cols-2 gap-3">
          <select
            value={targetDepartment}
            onChange={(e) => setTargetDepartment(e.target.value)}
            className="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-xs font-semibold bg-white focus:ring-2 focus:ring-indigo-500 outline-none"
          >
            {DEPARTMENTS.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
          <button
            type="submit"
            disabled={reassigning}
            className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-medium text-xs px-3 py-1.5 rounded-lg shadow transition"
          >
            {reassigning ? "Transferring..." : "Re-Assign Email"}
          </button>
        </div>
        <input
          type="text"
          value={reassignNote}
          onChange={(e) => setReassignNote(e.target.value)}
          placeholder="Transfer reason or notes (e.g. Referral for physio clear)..."
          className="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-xs bg-white outline-none"
        />
      </form>

      {/* Internal Notes Feed */}
      <div className="space-y-3">
        <div className="text-xs font-bold text-slate-500 uppercase tracking-wider">
          Collaboration Feed ({notes.length})
        </div>
        {loading ? (
          <div className="text-xs text-slate-400 py-4 text-center">Loading notes...</div>
        ) : notes.length === 0 ? (
          <div className="text-xs text-slate-400 py-4 text-center italic bg-slate-50 rounded-lg border border-slate-100">
            No internal notes attached yet.
          </div>
        ) : (
          <div className="space-y-3 max-h-60 overflow-y-auto pr-1">
            {notes.map((n) => (
              <div key={n.id} className="p-3 rounded-lg bg-slate-50 border border-slate-100 text-xs space-y-1">
                <div className="flex items-center justify-between text-slate-700">
                  <span className="font-semibold flex items-center gap-1.5">
                    <UserCheck className="h-3.5 w-3.5 text-indigo-500" />
                    {n.author_name}
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-700 font-bold">
                      {n.author_role}
                    </span>
                  </span>
                  {n.created_at && (
                    <span className="text-[10px] text-slate-400 flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {new Date(n.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </span>
                  )}
                </div>
                <p className="text-slate-800 leading-relaxed">{n.content}</p>
                {n.mentioned_department && (
                  <span className="inline-flex items-center gap-1 text-[10px] font-bold text-amber-700 bg-amber-50 px-2 py-0.5 rounded border border-amber-200 mt-1">
                    <Tag className="h-3 w-3" />@{n.mentioned_department}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Add Comment Form */}
      <form onSubmit={handleAddNote} className="space-y-3 pt-2 border-t border-slate-100">
        <textarea
          rows={2}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="Add an internal note or use @DEPARTMENT..."
          className="w-full p-2.5 border border-slate-200 rounded-lg text-xs outline-none focus:ring-2 focus:ring-indigo-500"
        />
        <div className="flex items-center justify-between">
          <select
            value={mentionedDepartment}
            onChange={(e) => setMentionedDepartment(e.target.value)}
            className="px-2 py-1 border border-slate-200 rounded-md text-xs bg-slate-50 text-slate-600 outline-none"
          >
            <option value="">No @mention</option>
            {DEPARTMENTS.map((d) => (
              <option key={d} value={d}>
                @{d}
              </option>
            ))}
          </select>
          <button
            type="submit"
            className="flex items-center gap-1.5 bg-indigo-600 hover:bg-indigo-700 text-white font-medium text-xs px-3 py-1.5 rounded-lg shadow transition"
          >
            <Send className="h-3.5 w-3.5" />
            Add Note
          </button>
        </div>
      </form>
    </div>
  );
}
