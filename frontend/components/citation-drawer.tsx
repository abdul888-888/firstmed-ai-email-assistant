"use client";

import { FileText, ExternalLink, ShieldAlert, Sparkles, CheckCircle } from "lucide-react";

interface CitationItem {
  document_id: string;
  source: string;
  title: string;
  url?: string;
}

export function NotionCitationDrawer({
  templateName = "GP_Price_ValueCard_v2",
  citations = [
    {
      document_id: "doc-1",
      source: "Notion Medical Knowledge Base",
      title: "FirstMed General Practice Fee Schedule 2026",
      url: "https://notion.so/firstmed/gp-pricing-2026",
    },
    {
      document_id: "doc-2",
      source: "Clinical Standard Operating Guidelines",
      title: "Physiotherapy & Orthopaedic Referral Workflow v4",
      url: "https://notion.so/firstmed/physio-referrals",
    },
  ],
  workflowRule = "Rule #4: Direct administrative pricing query — verified with RAG notion store.",
}: {
  templateName?: string;
  citations?: CitationItem[];
  workflowRule?: string;
}) {
  return (
    <div className="bg-slate-900 text-slate-100 rounded-xl p-5 space-y-5 shadow-lg border border-slate-800">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-3">
        <h3 className="text-sm font-bold flex items-center gap-2 text-indigo-400">
          <Sparkles className="h-4 w-4 text-indigo-400" />
          AI Transparency & Source Verification
        </h3>
        <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1">
          <CheckCircle className="h-3 w-3" /> Verifiable Grounding
        </span>
      </div>

      {/* Matched Template */}
      <div className="space-y-1.5">
        <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block">
          Matched Response Template
        </span>
        <div className="flex items-center justify-between bg-slate-800/80 border border-slate-700/60 rounded-lg p-2.5">
          <span className="font-mono text-xs text-indigo-300 font-bold">{templateName}</span>
          <span className="text-[10px] text-slate-400 bg-slate-700 px-2 py-0.5 rounded">High Confidence</span>
        </div>
      </div>

      {/* RAG Notion Citation Cards */}
      <div className="space-y-2">
        <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block">
          Notion Knowledge Base Citations ({citations.length})
        </span>
        <div className="space-y-2">
          {citations.map((c, i) => (
            <div
              key={c.document_id || i}
              className="bg-slate-800/60 border border-slate-700/40 rounded-lg p-3 space-y-1.5 hover:border-slate-600 transition"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-200 flex items-center gap-1.5">
                  <FileText className="h-3.5 w-3.5 text-indigo-400" />
                  {c.title}
                </span>
                {c.url && (
                  <a
                    href={c.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-indigo-400 hover:text-indigo-300 text-[11px] flex items-center gap-1 font-medium"
                  >
                    View Source <ExternalLink className="h-3 w-3" />
                  </a>
                )}
              </div>
              <p className="text-[11px] text-slate-400 font-mono">Source: {c.source}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Applied AI Workflow Rule */}
      <div className="bg-slate-800/40 border border-slate-700/50 rounded-lg p-3 space-y-1">
        <span className="text-[10px] font-bold text-amber-400 uppercase tracking-wider flex items-center gap-1">
          <ShieldAlert className="h-3 w-3" /> Active Classification Rule
        </span>
        <p className="text-xs text-slate-300">{workflowRule}</p>
      </div>
    </div>
  );
}
