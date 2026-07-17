/**
 * Backend API base URL. Injected at build/runtime via NEXT_PUBLIC_API_BASE_URL
 * (see .env.example). Falls back to the local backend port.
 */
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/** Backend liveness endpoint (Phase 1). */
export const BACKEND_HEALTH_URL = `${API_BASE_URL}/api/v1/health`;
