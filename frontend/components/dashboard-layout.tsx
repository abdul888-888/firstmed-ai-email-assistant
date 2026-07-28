"use client";

// Force Vercel rebuild - file exists at correct path
import { useEffect, useState } from "react";
import { Sidebar } from "@/components/sidebar";
import { jwtDecode } from "jwt-decode";
import { getToken } from "@/lib/auth";

interface TokenPayload {
  email?: string;
}

export function DashboardLayout({ children }: { children: React.ReactNode }) {
  const [userEmail, setUserEmail] = useState<string>();

  useEffect(() => {
    const token = getToken();
    if (token) {
      try {
        const payload = jwtDecode<TokenPayload>(token);
        setUserEmail(payload.email);
      } catch {
        console.error("Failed to decode token");
      }
    }
  }, []);

  return (
    <div className="min-h-screen">
      <Sidebar userEmail={userEmail} />
      <div className="ml-64">
        {children}
      </div>
    </div>
  );
}
