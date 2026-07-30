"use client";

import { useEffect, useState } from "react";
import { getToken, authHeader } from "@/lib/auth";
import { API_BASE_URL } from "@/lib/api";

export default function TestAuthPage() {
  const [token, setToken] = useState("");
  const [response, setResponse] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const storedToken = getToken();
    setToken(storedToken || "");
  }, []);

  const testRequest = async () => {
    setLoading(true);
    setResponse(null);

    const headers = {
      "Content-Type": "application/json",
      ...authHeader(),
    };

    console.log("Request details:", {
      url: `${API_BASE_URL}/api/v1/reviews/pending`,
      headers,
    });

    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/reviews/pending`, {
        headers,
      });

      const data = await res.json().catch(() => ({}));

      setResponse({
        status: res.status,
        statusText: res.statusText,
        data,
        headers: {
          "content-type": res.headers.get("content-type"),
        },
      });

      console.log("Response:", { status: res.status, data });
    } catch (e) {
      setResponse({
        error: String(e),
      });
      console.error("Error:", e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 p-8">
      <div className="max-w-2xl mx-auto">
        <h1 className="text-3xl font-bold mb-6">🔍 Auth Test</h1>

        <div className="bg-white rounded-lg border border-slate-200 p-6 mb-6">
          <h2 className="text-lg font-semibold mb-4">Token Status</h2>
          <div className="space-y-2">
            <p className="text-sm">
              <span className="font-medium">Token in localStorage:</span>{" "}
              {token ? `${token.substring(0, 30)}...` : "❌ NOT FOUND"}
            </p>
            <p className="text-sm">
              <span className="font-medium">Auth Header:</span>{" "}
              {token
                ? `✅ Authorization: Bearer ${token.substring(0, 20)}...`
                : "❌ No token"}
            </p>
            <p className="text-sm">
              <span className="font-medium">Backend URL:</span> {API_BASE_URL}
            </p>
          </div>
        </div>

        <button
          onClick={testRequest}
          disabled={loading || !token}
          className="bg-blue-600 text-white px-6 py-3 rounded-lg font-semibold hover:bg-blue-700 disabled:opacity-50 mb-6"
        >
          {loading ? "Testing..." : "Test GET /api/v1/reviews/pending"}
        </button>

        {response && (
          <div className="bg-white rounded-lg border border-slate-200 p-6">
            <h2 className="text-lg font-semibold mb-4">Response</h2>

            {response.error ? (
              <div className="bg-red-50 border border-red-200 rounded p-4">
                <p className="text-red-700 font-semibold">Error:</p>
                <p className="text-red-600 text-sm">{response.error}</p>
              </div>
            ) : (
              <div className="space-y-4">
                <div className={`p-4 rounded ${response.status === 200 ? "bg-green-50 border border-green-200" : "bg-red-50 border border-red-200"}`}>
                  <p className={`font-semibold ${response.status === 200 ? "text-green-700" : "text-red-700"}`}>
                    Status: {response.status} {response.statusText}
                  </p>
                </div>

                {response.status === 401 && (
                  <div className="bg-yellow-50 border border-yellow-200 rounded p-4">
                    <p className="text-yellow-800 font-semibold">⚠️ 401 Unauthorized</p>
                    <p className="text-yellow-700 text-sm mt-2">
                      The backend rejected your token. Possible causes:
                    </p>
                    <ul className="text-yellow-700 text-sm mt-2 list-disc list-inside space-y-1">
                      <li>Token expired (default: 60 minutes)</li>
                      <li>Backend SECRET_KEY doesn&apos;t match token signature</li>
                      <li>User doesn&apos;t exist in database</li>
                      <li>Token is malformed</li>
                    </ul>
                    <p className="text-yellow-700 text-sm mt-3 font-semibold">Try:</p>
                    <ol className="text-yellow-700 text-sm mt-1 list-decimal list-inside space-y-1">
                      <li>Sign out and back in to get a fresh token</li>
                      <li>Check backend console for error messages</li>
                      <li>Restart backend to reload SECRET_KEY</li>
                    </ol>
                  </div>
                )}

                <div className="bg-slate-50 rounded p-4 overflow-auto max-h-96">
                  <p className="font-semibold text-sm mb-2">Response Data:</p>
                  <pre className="text-xs text-slate-700">
                    {JSON.stringify(response.data, null, 2)}
                  </pre>
                </div>
              </div>
            )}
          </div>
        )}

        <div className="mt-8 text-sm text-slate-600">
          <p className="mb-2">📝 Debug info is also printed to browser console (F12)</p>
          <p>Check backend console (Terminal 2) for token validation logs</p>
        </div>
      </div>
    </div>
  );
}
