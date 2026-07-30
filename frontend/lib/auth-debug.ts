/**
 * Authentication debugging utilities to diagnose 401 issues
 */

import { getToken, authHeader } from "@/lib/auth";
import { API_BASE_URL } from "@/lib/api";

export async function debugAuthFlow() {
  console.group("🔐 Authentication Debug");

  // 1. Check if token exists
  const token = getToken();
  console.log("Token stored:", token ? `${token.substring(0, 20)}...` : "❌ NO TOKEN");

  // 2. Check auth header
  const header = authHeader();
  console.log("Auth header:", header);

  // 3. Test unauthenticated request
  console.log("\n📡 Testing health endpoint (unauthenticated):");
  try {
    const healthRes = await fetch(`${API_BASE_URL}/api/v1/health`);
    console.log("Status:", healthRes.status, healthRes.statusText);
    const healthData = await healthRes.json();
    console.log("Response:", healthData);
  } catch (e) {
    console.error("Error:", e);
  }

  // 4. Test authenticated request
  if (token) {
    console.log("\n🔒 Testing authenticated request (GET /api/v1/reviews/pending):");
    try {
      const reviewsRes = await fetch(`${API_BASE_URL}/api/v1/reviews/pending`, {
        headers: {
          "Content-Type": "application/json",
          ...authHeader(),
        },
      });
      console.log("Status:", reviewsRes.status, reviewsRes.statusText);
      const reviewsData = await reviewsRes.json();
      console.log("Response:", reviewsData);

      // Check if 401
      if (reviewsRes.status === 401) {
        console.error(
          "❌ Got 401 Unauthorized. Token might be invalid or expired."
        );
        console.log("Token header sent:", `Bearer ${token.substring(0, 20)}...`);
      }
    } catch (e) {
      console.error("Error:", e);
    }
  } else {
    console.log("⚠️  No token available, skipping authenticated test");
  }

  console.groupEnd();
}

// Call this in browser console: window.__debugAuth()
if (typeof window !== "undefined") {
  (window as any).__debugAuth = debugAuthFlow;
  console.log("✓ Call window.__debugAuth() to debug authentication");
}
