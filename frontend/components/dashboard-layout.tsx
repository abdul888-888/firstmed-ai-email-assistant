"use client";

// Match the exact filename casing!

import { useEffect, useState } from "react";
import { Sidebar } from "@/components/sidebar";
import { jwtDecode } from "jwt-decode";
import { getToken } from "@/lib/auth";
import { apiFetch } from "@/lib/api";

interface TokenPayload {
  email?: string;
}

interface CurrentUser {
  id: string;
  email: string;
  role: "ADMIN" | "FRONT_OFFICE" | "CLINICAL_REVIEWER" | "BOOKING_COORDINATOR";
  is_active: boolean;
}

// Map backend role values to frontend UI roles
function mapBackendRoleToFrontend(backendRole: string): "front_office" | "clinical_reviewer" | "booking_coordinator" | "admin" {
  // Normalize to uppercase for consistent mapping
  const normalizedRole = backendRole.toUpperCase();
  const roleMap: Record<string, "front_office" | "clinical_reviewer" | "booking_coordinator" | "admin"> = {
    "ADMIN": "admin",
    "FRONT_OFFICE": "front_office",
    "CLINICAL_REVIEWER": "clinical_reviewer",
    "BOOKING_COORDINATOR": "booking_coordinator",
  };
  return roleMap[normalizedRole] || "front_office";
}

export function DashboardLayout({ children }: { children: React.ReactNode }) {
  const [userEmail, setUserEmail] = useState<string>();
  const [userRole, setUserRole] = useState<"front_office" | "clinical_reviewer" | "booking_coordinator" | "admin">("front_office");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadUserData = async () => {
      const token = getToken();
      if (!token) {
        setLoading(false);
        return;
      }

      try {
        // Fetch current user from backend (§7 server-side role verification)
        const currentUser = await apiFetch<CurrentUser>({ path: "/auth/me" });
        setUserEmail(currentUser.email);
        setUserRole(mapBackendRoleToFrontend(currentUser.role));
      } catch (err) {
        console.error("Failed to load user data:", err);
        // Fallback to token decoding if /me fails
        try {
          const payload = jwtDecode<TokenPayload>(token);
          setUserEmail(payload.email);
        } catch {
          console.error("Failed to decode token");
        }
      } finally {
        setLoading(false);
      }
    };

    void loadUserData();
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-slate-500">Loading...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Sidebar userEmail={userEmail} role={userRole} />
      <div className="ml-64">
        {children}
      </div>
    </div>
  );
}
