"use client";

import { useQuery } from "@tanstack/react-query";

type HealthResponse = { status: string; backend: string };

async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch("/api/health", { cache: "no-store" });
  if (!res.ok) throw new Error(`health check failed: ${res.status}`);
  return res.json();
}

/**
 * Small live indicator that pings the frontend /api/health proxy (which in turn
 * checks backend liveness). Demonstrates the TanStack Query wiring end-to-end.
 */
export function BackendStatus() {
  const { data, isPending, isError } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 15_000,
    retry: false,
  });

  const backendUp = data?.backend === "ok";
  const label = isPending
    ? "checking…"
    : isError || !backendUp
      ? "unreachable"
      : "connected";
  const dot = isPending
    ? "bg-muted-foreground"
    : backendUp
      ? "bg-green-500"
      : "bg-destructive";

  return (
    <div className="inline-flex items-center gap-2 rounded-full border border-border px-3 py-1 text-sm text-muted-foreground">
      <span className={`h-2 w-2 rounded-full ${dot}`} aria-hidden />
      <span>Backend: {label}</span>
    </div>
  );
}
