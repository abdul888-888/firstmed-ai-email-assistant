"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Mail, BarChart3, LogOut, Stethoscope } from "lucide-react";
import { Button } from "@/components/ui/button";
import { clearToken } from "@/lib/auth";
import { useState } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

type NavItem = {
  href: string;
  label: string;
  icon: React.ReactNode;
};

const navItems: NavItem[] = [
  { href: "/reviews", label: "Inbox Queue", icon: <Mail className="h-5 w-5" /> },
  { href: "/analytics", label: "Analytics", icon: <BarChart3 className="h-5 w-5" /> },
];

export function Sidebar({ userEmail }: { userEmail?: string }) {
  const pathname = usePathname();
  const [loggingOut, setLoggingOut] = useState(false);

  function handleLogout() {
    setLoggingOut(true);
    try {
      clearToken();
      window.location.href = "/";
    } catch (e) {
      console.error("Logout failed:", e);
      setLoggingOut(false);
    }
  }

  return (
    <aside className="fixed left-0 top-0 z-50 h-screen w-64 border-r border-slate-200 bg-white shadow-sm">
      {/* Logo Section */}
      <div className="border-b border-slate-100 px-6 py-6">
        <Link href="/" className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-600 to-indigo-700 shadow-md">
            <Stethoscope className="h-6 w-6 text-white" strokeWidth={2.5} />
          </div>
          <div className="flex flex-col">
            <span className="text-lg font-bold text-slate-900 tracking-tight">FirstMed</span>
            <span className="text-xs font-medium text-emerald-600">AI Assistant</span>
          </div>
        </Link>
      </div>

      {/* Navigation Section */}
      <nav className="flex-1 space-y-2 px-4 py-6">
        {navItems.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-4 py-3 text-sm font-medium transition-all duration-200",
                isActive
                  ? "bg-indigo-50 text-indigo-700 shadow-sm"
                  : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
              )}
            >
              <span
                className={cn(
                  "transition-colors",
                  isActive ? "text-indigo-600" : "text-slate-400"
                )}
              >
                {item.icon}
              </span>
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* User Section */}
      <div className="border-t border-slate-100 space-y-3 px-4 py-6">
        {userEmail && (
          <div className="px-2 py-3 rounded-lg bg-slate-50 border border-slate-100">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">
              Logged in as
            </p>
            <p className="text-sm font-semibold text-slate-900 truncate mt-1">{userEmail}</p>
          </div>
        )}
        <Button
          onClick={handleLogout}
          disabled={loggingOut}
          variant="outline"
          className="w-full justify-center gap-2 text-slate-600 border-slate-200 hover:bg-red-50 hover:text-red-700 hover:border-red-200"
        >
          {loggingOut ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <LogOut className="h-4 w-4" />
          )}
          Sign Out
        </Button>
      </div>
    </aside>
  );
}
