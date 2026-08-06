import * as React from "react";
import { cn } from "@/lib/utils";
import { FileEdit, ArrowRightLeft, Clock, Hourglass } from "lucide-react";

export type FrontOfficeStatus = "drafted" | "routed" | "waiting_specialist" | "pending";

interface StatusTagProps {
  status: FrontOfficeStatus | string;
  targetDepartment?: string;
  className?: string;
}

export function StatusTag({ status, targetDepartment, className }: StatusTagProps) {
  const normStatus = status.toLowerCase();

  if (normStatus === "drafted" || normStatus === "approved") {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-md text-xs font-semibold bg-sky-100 text-sky-800 border border-sky-300 dark:bg-sky-950/80 dark:text-sky-300 dark:border-sky-800",
          className
        )}
      >
        <FileEdit className="w-3.5 h-3.5 text-sky-600 dark:text-sky-400" />
        Drafted
      </span>
    );
  }

  if (normStatus === "routed" || normStatus === "route_to_staff" || normStatus === "needs_physician_review") {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-md text-xs font-semibold bg-purple-100 text-purple-800 border border-purple-300 dark:bg-purple-950/80 dark:text-purple-300 dark:border-purple-800",
          className
        )}
      >
        <ArrowRightLeft className="w-3.5 h-3.5 text-purple-600 dark:text-purple-400" />
        Routed{targetDepartment ? `: ${targetDepartment}` : ""}
      </span>
    );
  }

  if (normStatus === "waiting_specialist" || normStatus === "awaiting_specialist_input") {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-md text-xs font-semibold bg-amber-100 text-amber-900 border border-amber-300 dark:bg-amber-950/80 dark:text-amber-300 dark:border-amber-800",
          className
        )}
      >
        <Clock className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />
        Waiting on specialist
      </span>
    );
  }

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-md text-xs font-medium bg-slate-100 text-slate-700 border border-slate-300 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700",
        className
      )}
    >
      <Hourglass className="w-3.5 h-3.5 text-slate-500" />
      Pending
    </span>
  );
}
