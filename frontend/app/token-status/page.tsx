"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, AlertTriangle, Clock, LogOut, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { DashboardLayout } from "@/components/dashboard-layout";
import { getToken, clearToken, startGoogleSignIn } from "@/lib/auth";
import {
  checkTokenStatus,
  formatExpirationTime,
  getExpirationMessage,
  type TokenStatus,
} from "@/lib/token-status";
import { cn } from "@/lib/utils";

export default function TokenStatusPage() {
  const [status, setStatus] = useState<TokenStatus | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const checkStatus = () => {
    const token = getToken();
    const newStatus = checkTokenStatus(token);
    setStatus(newStatus);
  };

  useEffect(() => {
    checkStatus();
    const interval = setInterval(checkStatus, 1000); // Update every second
    return () => clearInterval(interval);
  }, []);

  const handleLogout = () => {
    clearToken();
    window.location.href = "/";
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await startGoogleSignIn("/token-status");
    } catch (error) {
      console.error("Failed to start sign-in:", error);
    } finally {
      setRefreshing(false);
    }
  };

  if (!status) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-96">
          <div className="animate-spin">
            <Clock className="w-8 h-8 text-blue-600" />
          </div>
        </div>
      </DashboardLayout>
    );
  }

  const message = getExpirationMessage(status);
  const expiresInMinutes = status.expiresIn ? Math.floor(status.expiresIn / 60) : 0;
  const isAboutToExpire = status.expiresIn !== null && status.expiresIn < 300; // 5 minutes

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Authentication Status</h1>
          <p className="text-gray-600 mt-1">Check your token and session status</p>
        </div>

        {/* Main Status Card */}
        <Card className={cn(
          "border-2",
          status.isExpired ? "border-red-300" : isAboutToExpire ? "border-yellow-300" : "border-green-300"
        )}>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                {status.isExpired ? (
                  <>
                    <AlertTriangle className="w-6 h-6 text-red-600" />
                    Token Expired
                  </>
                ) : isAboutToExpire ? (
                  <>
                    <AlertTriangle className="w-6 h-6 text-yellow-600" />
                    Token Expiring Soon
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="w-6 h-6 text-green-600" />
                    Token Valid
                  </>
                )}
              </CardTitle>
              <Badge className={cn(
                status.isExpired
                  ? "bg-red-100 text-red-800"
                  : isAboutToExpire
                  ? "bg-yellow-100 text-yellow-800"
                  : "bg-green-100 text-green-800"
              )}>
                {status.hasToken ? "Signed In" : "Not Signed In"}
              </Badge>
            </div>
          </CardHeader>

          <CardContent className="space-y-4">
            {/* Status Message */}
            <div className="p-4 rounded-lg bg-gray-50 border border-gray-200">
              <p className="text-lg font-medium text-gray-900">{message}</p>
            </div>

            {/* Details Grid */}
            {status.hasToken && (
              <>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Expiration Time */}
                  <div className="border rounded-lg p-4">
                    <p className="text-sm text-gray-600 font-medium">Expires At</p>
                    <p className="text-lg font-mono text-gray-900 mt-1">
                      {formatExpirationTime(status.expiresAt)}
                    </p>
                  </div>

                  {/* Time Remaining */}
                  <div className="border rounded-lg p-4">
                    <p className="text-sm text-gray-600 font-medium">Time Remaining</p>
                    {status.isExpired ? (
                      <p className="text-lg font-mono text-red-600 mt-1">Expired</p>
                    ) : status.expiresIn !== null ? (
                      <>
                        <p className="text-lg font-mono text-gray-900 mt-1">
                          {expiresInMinutes > 0
                            ? `${expiresInMinutes} minutes`
                            : `${status.expiresIn} seconds`}
                        </p>
                        <p className="text-xs text-gray-500 mt-1">
                          {status.expiresIn > 0
                            ? `${status.expiresIn} seconds exactly`
                            : "less than 1 second"}
                        </p>
                      </>
                    ) : (
                      <p className="text-lg font-mono text-gray-900 mt-1">Unknown</p>
                    )}
                  </div>

                  {/* User ID */}
                  <div className="border rounded-lg p-4">
                    <p className="text-sm text-gray-600 font-medium">User ID</p>
                    <p className="text-sm font-mono text-gray-900 mt-1 break-all">
                      {status.userInfo?.sub || "Unknown"}
                    </p>
                  </div>

                  {/* Role */}
                  <div className="border rounded-lg p-4">
                    <p className="text-sm text-gray-600 font-medium">Role</p>
                    <p className="text-lg font-medium text-gray-900 mt-1 capitalize">
                      {status.userInfo?.role || "Unknown"}
                    </p>
                  </div>
                </div>

                {/* Token Preview */}
                <div className="border rounded-lg p-4 bg-gray-50">
                  <p className="text-sm text-gray-600 font-medium mb-2">Token</p>
                  <code className="text-xs text-gray-700 break-all block p-2 bg-white border border-gray-200 rounded overflow-x-auto">
                    {status.rawToken?.substring(0, 50)}...
                  </code>
                  <p className="text-xs text-gray-500 mt-2">
                    Full token is {status.rawToken?.length || 0} characters
                  </p>
                </div>

                {/* Status Indicator Bar */}
                <div className="border rounded-lg p-4">
                  <p className="text-sm text-gray-600 font-medium mb-3">Token Lifespan</p>
                  <div className="w-full bg-gray-200 rounded-full h-2 overflow-hidden">
                    <div
                      className={cn(
                        "h-full transition-all",
                        status.isExpired
                          ? "bg-red-600"
                          : isAboutToExpire
                          ? "bg-yellow-500"
                          : "bg-green-600"
                      )}
                      style={{
                        width: `${Math.max(0, Math.min(100, (status.expiresIn || 0) / 36))}%`,
                      }}
                    />
                  </div>
                  <p className="text-xs text-gray-500 mt-2">
                    Default token lifetime: 60 minutes
                  </p>
                </div>
              </>
            )}

            {/* No Token State */}
            {!status.hasToken && (
              <div className="border rounded-lg p-4 bg-blue-50">
                <p className="text-sm text-blue-900">
                  You are not currently signed in. Click the button below to sign in.
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Action Buttons */}
        <div className="flex gap-3 flex-wrap">
          <Button onClick={checkStatus} variant="outline">
            <RefreshCw className="w-4 h-4 mr-2" />
            Refresh Status
          </Button>

          {status.hasToken && status.isExpired && (
            <Button onClick={handleRefresh} disabled={refreshing} className="bg-blue-600 hover:bg-blue-700">
              {refreshing ? (
                <>
                  <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                  Signing In...
                </>
              ) : (
                <>
                  <Clock className="w-4 h-4 mr-2" />
                  Sign In Again
                </>
              )}
            </Button>
          )}

          {status.hasToken && isAboutToExpire && (
            <Button onClick={handleRefresh} disabled={refreshing} className="bg-yellow-600 hover:bg-yellow-700">
              {refreshing ? (
                <>
                  <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                  Refreshing...
                </>
              ) : (
                <>
                  <RefreshCw className="w-4 h-4 mr-2" />
                  Refresh Token
                </>
              )}
            </Button>
          )}

          {status.hasToken && (
            <Button onClick={handleLogout} variant="destructive">
              <LogOut className="w-4 h-4 mr-2" />
              Sign Out
            </Button>
          )}
        </div>

        {/* Info Box */}
        <Card className="bg-blue-50 border-blue-200">
          <CardHeader>
            <CardTitle className="text-base">How Token Expiration Works</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-gray-700">
            <p>
              • Your authentication token is valid for <strong>60 minutes</strong> from the time you sign in
            </p>
            <p>
              • When expired, you&rsquo;ll need to sign in again to continue using the app
            </p>
            <p>
              • This page updates in real-time and displays your token status
            </p>
            <p>
              • If your token is about to expire (within 5 minutes), we recommend signing in again
            </p>
            <p>
              • Signing out immediately clears your token from this device
            </p>
          </CardContent>
        </Card>
      </div>
    </DashboardLayout>
  );
}
