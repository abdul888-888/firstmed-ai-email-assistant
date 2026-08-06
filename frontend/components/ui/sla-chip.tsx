import * as React from "react";
import { cn } from "@/lib/utils";
import { Clock, AlertTriangle, AlertCircle, CheckCircle2 } from "lucide-react";

export type SLAStatus = "on_time" | "at_risk" | "overdue";

interface SLAChipProps {
  status: SLAStatus;
  elapsedText?: string;
  className?: string;
}

export function SLAChip({ status, elapsedText, className }: SLAChipProps) {
  if (status === "overdue") {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-red-100 text-red-800 border border-red-300 dark:bg-red-950/80 dark:text-red-300 dark:border-red-800",
          className
        )}
        title="SLA Overdue - Needs Immediate Attention"
      >
        <AlertCircle className="w-3.5 h-3.5 text-red-600 dark:text-red-400 shrink-0" />
        <span>{elapsedText || "Overdue"}</span>
      </span>
    );
  }

  if (status === "at_risk") {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800 border border-amber-300 dark:bg-amber-950/80 dark:text-amber-300 dark:border-amber-800",
          className
        )}
        title="SLA At Risk"
      >
        <AlertTriangle className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400 shrink-0" />
        <span>{elapsedText || "At Risk"}</span>
      </span>
    );
  }

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800",
        className
      )}
      title="Within SLA"
    >
      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400 shrink-0" />
      <span>{elapsedText || "On Time"}</span>
    </span>
  );
}
