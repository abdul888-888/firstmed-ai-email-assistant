/**
 * Token expiration checker.
 * Decodes JWT without verification to check expiration status.
 * For security validation, the backend always verifies tokens.
 */

export interface TokenStatus {
  hasToken: boolean;
  isExpired: boolean;
  expiresAt: Date | null;
  expiresIn: number | null; // seconds
  userInfo: { sub: string; role?: string } | null;
  rawToken: string | null;
}

/** Decode a JWT payload without verification (client-side only for UX). */
function decodeJWT(token: string): Record<string, any> | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;

    // Decode payload (second part)
    const payload = parts[1];
    const decoded = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(decoded);
  } catch (error) {
    console.error("Failed to decode JWT:", error);
    return null;
  }
}

/** Check token status without network requests. */
export function checkTokenStatus(token: string | null): TokenStatus {
  if (!token) {
    return {
      hasToken: false,
      isExpired: true,
      expiresAt: null,
      expiresIn: null,
      userInfo: null,
      rawToken: null,
    };
  }

  const payload = decodeJWT(token);
  if (!payload || !payload.exp) {
    return {
      hasToken: true,
      isExpired: true,
      expiresAt: null,
      expiresIn: null,
      userInfo: null,
      rawToken: token,
    };
  }

  const expiresAt = new Date(payload.exp * 1000);
  const now = new Date();
  const isExpired = now > expiresAt;
  const expiresInSeconds = Math.floor((expiresAt.getTime() - now.getTime()) / 1000);

  return {
    hasToken: true,
    isExpired,
    expiresAt,
    expiresIn: Math.max(0, expiresInSeconds),
    userInfo: {
      sub: payload.sub,
      role: payload.role,
    },
    rawToken: token,
  };
}

/** User-friendly expiration message. */
export function getExpirationMessage(status: TokenStatus): string {
  if (!status.hasToken) {
    return "Not signed in";
  }

  if (status.isExpired) {
    return "Token expired - please sign in again";
  }

  if (status.expiresIn === null) {
    return "Unknown token status";
  }

  const minutes = Math.floor(status.expiresIn / 60);
  const seconds = status.expiresIn % 60;

  if (minutes === 0) {
    return `Expires in ${seconds} seconds`;
  }

  if (minutes < 5) {
    return `Expires in ${minutes}m ${seconds}s (about to expire!)`;
  }

  if (minutes < 60) {
    return `Expires in ${minutes} minutes`;
  }

  const hours = Math.floor(minutes / 60);
  return `Expires in about ${hours} hour${hours > 1 ? "s" : ""}`;
}

/** Format expiration time. */
export function formatExpirationTime(expiresAt: Date | null): string {
  if (!expiresAt) return "Unknown";

  return expiresAt.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
  });
}
