import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Neutral pill. Pass color utility classes via `className` for semantic tints
 * (e.g. `bg-red-100 text-red-700 border-red-200`).
 */
export function Badge({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        "border-slate-200 bg-slate-100 text-slate-700",
        className,
      )}
      {...props}
    />
  );
}
