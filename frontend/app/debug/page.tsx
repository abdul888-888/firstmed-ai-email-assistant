"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Check, X, AlertCircle, RefreshCw } from "lucide-react";
import { API_BASE_URL } from "@/lib/api";
import { authHeader, getToken } from "@/lib/auth";

type TestResult = {
  name: string;
  status: "pending" | "success" | "error" | "warning";
  message: string;
  details?: string;
};

export default function DebugPage() {
  const [results, setResults] = useState<TestResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [frontendUrl, setFrontendUrl] = useState("http://localhost:3000");

  const addResult = (result: TestResult) => {
    setResults((prev) => [...prev, result]);
  };

  const clearResults = () => {
    setResults([]);
  };

  useEffect(() => {
    if (typeof window !== "undefined") {
      setFrontendUrl(window.location.origin);
    }
  }, []);

  const runTests = async () => {
    clearResults();
    setLoading(true);

    // Test 1: Check localStorage
    const token = getToken();
    addResult({
      name: "📦 Token in localStorage",
      status: token ? "success" : "error",
      message: token ? "✅ Token found" : "❌ No token stored",
      details: token ? `${token.substring(0, 30)}...` : "Sign in to get a token",
    });

    // Test 2: Check auth header
    const header = authHeader();
    const hasAuthHeader = Object.keys(header).includes("Authorization");
    addResult({
      name: "🔑 Auth Header",
      status: hasAuthHeader ? "success" : "error",
      message: hasAuthHeader ? "✅ Auth header configured" : "❌ No auth header",
      details: hasAuthHeader ? header.Authorization?.substring(0, 30) + "..." : "Missing Bearer token",
    });

    // Test 3: Health check (no auth required)
    addResult({
      name: "🏥 Backend Health (no auth)",
      status: "pending",
      message: "Testing...",
    });
    try {
      const healthRes = await fetch(`${API_BASE_URL}/api/v1/health`);
      addResult({
        name: "🏥 Backend Health (no auth)",
        status: healthRes.ok ? "success" : "error",
        message: healthRes.ok ? "✅ Backend is responding" : `❌ Status ${healthRes.status}`,
        details: `Status: ${healthRes.status} ${healthRes.statusText}`,
      });
    } catch (e) {
      addResult({
        name: "🏥 Backend Health (no auth)",
        status: "error",
        message: `❌ Connection failed`,
        details: `${e instanceof Error ? e.message : String(e)}`,
      });
    }

    // Test 4: Authenticated request
    if (token) {
      addResult({
        name: "🔐 Authenticated Request (GET /reviews/pending)",
        status: "pending",
        message: "Testing...",
      });
      try {
        const reviewsRes = await fetch(`${API_BASE_URL}/api/v1/reviews/pending`, {
          headers: {
            "Content-Type": "application/json",
            ...authHeader(),
          },
        });

        if (reviewsRes.status === 401) {
          addResult({
            name: "🔐 Authenticated Request (GET /reviews/pending)",
            status: "error",
            message: "❌ Got 401 Unauthorized",
            details:
              "Token exists but backend rejected it. Backend might have different SECRET_KEY or token is expired.",
          });
        } else if (reviewsRes.ok) {
          const data = await reviewsRes.json();
          addResult({
            name: "🔐 Authenticated Request (GET /reviews/pending)",
            status: "success",
            message: "✅ Request successful",
            details: `Received ${data.count || 0} reviews`,
          });
        } else {
          const data = await reviewsRes.json().catch(() => ({}));
          addResult({
            name: "🔐 Authenticated Request (GET /reviews/pending)",
            status: "error",
            message: `❌ Status ${reviewsRes.status}`,
            details: `${data.detail || reviewsRes.statusText}`,
          });
        }
      } catch (e) {
        addResult({
          name: "🔐 Authenticated Request (GET /reviews/pending)",
          status: "error",
          message: `❌ Connection failed`,
          details: `${e instanceof Error ? e.message : String(e)}`,
        });
      }
    } else {
      addResult({
        name: "🔐 Authenticated Request",
        status: "warning",
        message: "⚠️  Skipped (no token)",
        details: "Sign in first, then run tests again",
      });
    }

    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-white p-8">
      <div className="mx-auto max-w-2xl">
        <h1 className="text-4xl font-bold mb-2">🔍 Auth Debugging Dashboard</h1>
        <p className="text-slate-600 mb-6">
          Run tests to diagnose authentication issues
        </p>

        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <span>Configuration</span>
              <Button onClick={runTests} disabled={loading} className="gap-2">
                <RefreshCw className="h-4 w-4" />
                {loading ? "Running..." : "Run Tests"}
              </Button>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex justify-between py-2 border-b">
              <span className="text-slate-600">API Base URL:</span>
              <code className="bg-slate-100 px-2 py-1 rounded">{API_BASE_URL}</code>
            </div>
            <div className="flex justify-between py-2 border-b">
              <span className="text-slate-600">Frontend URL:</span>
              <code className="bg-slate-100 px-2 py-1 rounded">
                {frontendUrl}
              </code>
            </div>
          </CardContent>
        </Card>

        {results.length > 0 && (
          <div className="space-y-3">
            {results.map((result, idx) => (
              <Card
                key={idx}
                className={
                  result.status === "error"
                    ? "border-red-200 bg-red-50"
                    : result.status === "success"
                      ? "border-emerald-200 bg-emerald-50"
                      : result.status === "warning"
                        ? "border-amber-200 bg-amber-50"
                        : "border-slate-200"
                }
              >
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between gap-3">
                    <CardTitle className="text-base">{result.name}</CardTitle>
                    {result.status === "success" && (
                      <Check className="h-5 w-5 text-emerald-600 flex-shrink-0 mt-1" />
                    )}
                    {result.status === "error" && (
                      <X className="h-5 w-5 text-red-600 flex-shrink-0 mt-1" />
                    )}
                    {result.status === "warning" && (
                      <AlertCircle className="h-5 w-5 text-amber-600 flex-shrink-0 mt-1" />
                    )}
                  </div>
                </CardHeader>
                <CardContent className="pt-0 space-y-2">
                  <p className="text-sm font-medium">{result.message}</p>
                  {result.details && (
                    <p className="text-xs text-slate-600 bg-white rounded px-2 py-1">
                      {result.details}
                    </p>
                  )}
                </CardContent>
              </Card>
            ))}

            {results.some((r) => r.status === "error") && (
              <Card className="border-red-200 bg-red-50">
                <CardContent className="pt-6 flex items-start gap-3">
                  <AlertCircle className="h-5 w-5 text-red-600 flex-shrink-0 mt-0.5" />
                  <p className="text-sm text-red-800">
                    See <code className="bg-red-100 px-1 rounded">AUTH_DEBUGGING_GUIDE.md</code> in the root directory for detailed troubleshooting steps.
                  </p>
                </CardContent>
              </Card>
            )}
          </div>
        )}

        {results.length === 0 && !loading && (
          <Card className="border-dashed">
            <CardContent className="py-8 text-center text-slate-500">
              Click &quot;Run Tests&quot; to start diagnosing authentication issues
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
