import * as React from "react";
import { Sparkles, Info } from "lucide-react";
import { cn } from "@/lib/utils";

interface AIDraftBadgeProps {
  templateName?: string | null;
  onViewSource?: () => void;
  className?: string;
}

export function AIDraftBadge({ templateName, onViewSource, className }: AIDraftBadgeProps) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-2 px-3 py-2 bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-md text-xs dark:from-blue-950/60 dark:to-indigo-950/60 dark:border-blue-800/60",
        className
      )}
    >
      <div className="flex items-center gap-2">
        <span className="inline-flex items-center gap-1 font-semibold text-blue-700 dark:text-blue-300">
          <Sparkles className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400" />
          AI draft — not sent
        </span>
        {templateName && (
          <span className="text-slate-600 dark:text-slate-400 border-l border-slate-300 dark:border-slate-700 pl-2">
            Matched Template: <strong className="font-medium text-slate-800 dark:text-slate-200">{templateName}</strong>
          </span>
        )}
      </div>

      {onViewSource && (
        <button
          type="button"
          onClick={onViewSource}
          className="inline-flex items-center gap-1 font-medium text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-200 transition-colors"
        >
          <Info className="w-3.5 h-3.5" />
          View Source Trace
        </button>
      )}
    </div>
  );
}
