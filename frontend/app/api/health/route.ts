import { NextResponse } from "next/server";

import { BACKEND_HEALTH_URL } from "@/lib/api";

// Always evaluated at request time — never statically cached at build.
export const dynamic = "force-dynamic";

/**
 * Frontend liveness + backend reachability.
 * Returns `{ status, backend }` where `backend` is "ok" when the FastAPI
 * liveness endpoint responds, otherwise "unreachable".
 */
export async function GET() {
  let backend = "unreachable";
  try {
    const res = await fetch(BACKEND_HEALTH_URL, {
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });
    if (res.ok) backend = "ok";
  } catch {
    backend = "unreachable";
  }

  return NextResponse.json({ status: "ok", backend });
}
