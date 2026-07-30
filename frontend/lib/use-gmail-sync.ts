/**
 * useGmailSync — debounced "pull recent inbox mail → triage → pending reviews".
 *
 * Enqueues a background Celery task (`POST /api/v1/workflows/pull-async`) and
 * polls `GET /api/v1/workflows/pull-async/{task_id}` until it finishes, rather
 * than blocking on a single long request. Requires a Celery worker to be
 * running (`celery -A app.workers.celery_app.celery_app worker`) — with none
 * running the task just sits queued and this surfaces as a timeout error
 * after `POLL_TIMEOUT_MS`, not a silent hang.
 *
 * Also provides:
 *  - a 15s debounce lock (button stays disabled for `LOCK_MS` after each click),
 *  - a localStorage-persisted "last synced" timestamp shared across the app,
 *  - a live "X minutes ago" label that ticks without extra network calls.
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  getPullGmailStatus,
  pullGmailAsync,
  type PullResult,
} from "@/lib/api";

const LOCK_MS = 15_000;
const LAST_SYNCED_KEY = "firstmed_last_synced_at";

// How often to poll the task-status endpoint, and how long to wait before
// giving up and telling the user a worker might not be running.
const POLL_INTERVAL_MS = 2_000;
const POLL_TIMEOUT_MS = 180_000;

function readLastSynced(): number | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(LAST_SYNCED_KEY);
  const n = raw ? Number(raw) : NaN;
  return Number.isFinite(n) ? n : null;
}

/** Format an epoch-ms timestamp as a compact relative label. */
export function formatRelative(ts: number | null, now: number): string {
  if (!ts) return "never";
  const secs = Math.max(0, Math.round((now - ts) / 1000));
  if (secs < 5) return "just now";
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins} min${mins === 1 ? "" : "s"} ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs} hour${hrs === 1 ? "" : "s"} ago`;
  const days = Math.round(hrs / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export type UseGmailSync = {
  /** Trigger a sync. No-op while locked or already syncing. */
  sync: () => Promise<void>;
  /** True while the background task is queued/running (enqueue → poll → done). */
  syncing: boolean;
  /** True while syncing OR within the post-click debounce window. */
  disabled: boolean;
  /** Epoch-ms of the last successful sync (persisted), or null. */
  lastSyncedAt: number | null;
  /** Human label, e.g. "3 mins ago" — recomputed every 30s. */
  lastSyncedLabel: string;
  /** Summary returned by the most recently completed pull. */
  lastResult: PullResult | null;
  /** Error message from the most recent failed/timed-out sync, if any. */
  error: string | null;
};

/**
 * @param onComplete called after a successful sync (e.g. to reload the queue).
 * @param onUnauthorized called when the backend returns 401 (e.g. re-sign-in).
 */
export function useGmailSync(opts?: {
  onComplete?: (result: PullResult) => void;
  onUnauthorized?: () => void;
  maxResults?: number;
}): UseGmailSync {
  const { onComplete, onUnauthorized, maxResults = 12 } = opts ?? {};

  const [syncing, setSyncing] = useState(false);
  const [locked, setLocked] = useState(false);
  const [lastSyncedAt, setLastSyncedAt] = useState<number | null>(null);
  const [lastResult, setLastResult] = useState<PullResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(0);

  const lockTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Flips true on unmount so an in-flight poll loop stops touching state.
  const cancelledRef = useRef(false);

  // Hydrate persisted state on mount (avoids SSR/client mismatch).
  useEffect(() => {
    setLastSyncedAt(readLastSynced());
    setNow(Date.now());
    const tick = setInterval(() => setNow(Date.now()), 30_000);
    return () => {
      cancelledRef.current = true;
      clearInterval(tick);
      if (lockTimer.current) clearTimeout(lockTimer.current);
    };
  }, []);

  const sync = useCallback(async () => {
    if (syncing || locked) return;

    setSyncing(true);
    setLocked(true);
    setError(null);

    // Start the 15s debounce lock immediately on click.
    if (lockTimer.current) clearTimeout(lockTimer.current);
    lockTimer.current = setTimeout(() => setLocked(false), LOCK_MS);

    try {
      const { task_id } = await pullGmailAsync(maxResults);

      const startedAt = Date.now();
      let result: PullResult | null = null;
      let failure: string | null = null;

      while (true) {
        if (cancelledRef.current) return;

        if (Date.now() - startedAt > POLL_TIMEOUT_MS) {
          failure = "Sync is taking too long — is a background worker running?";
          break;
        }

        await sleep(POLL_INTERVAL_MS);
        if (cancelledRef.current) return;

        const status = await getPullGmailStatus(task_id);
        if (status.state === "SUCCESS") {
          result = status.result ?? {};
          break;
        }
        if (status.state === "FAILURE") {
          failure = status.error ?? "Sync failed";
          break;
        }
        // PENDING / STARTED / RETRY — keep polling.
      }

      if (cancelledRef.current) return;

      if (failure) {
        setError(failure);
        return;
      }

      const stamp = Date.now();
      setLastResult(result);
      setLastSyncedAt(stamp);
      setNow(stamp);
      if (typeof window !== "undefined") {
        window.localStorage.setItem(LAST_SYNCED_KEY, String(stamp));
      }
      if (result) onComplete?.(result);
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) {
        onUnauthorized?.();
        return;
      }
      setError(err instanceof Error ? err.message : "Sync failed");
    } finally {
      if (!cancelledRef.current) setSyncing(false);
    }
  }, [syncing, locked, maxResults, onComplete, onUnauthorized]);

  return {
    sync,
    syncing,
    disabled: syncing || locked,
    lastSyncedAt,
    lastSyncedLabel: formatRelative(lastSyncedAt, now || Date.now()),
    lastResult,
    error,
  };
}
