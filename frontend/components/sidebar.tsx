"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Stethoscope,
  CalendarCheck,
  AlertTriangle,
  ShieldAlert,
  Users,
  LogOut,
  Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { clearToken } from "@/lib/auth";
import { useState } from "react";
import { cn } from "@/lib/utils";

export type UserRole = "front_office" | "clinical_reviewer" | "booking_coordinator" | "admin";

interface NavItem {
  href: string;
  label: string;
  icon: React.ReactNode;
  roles: UserRole[];
  badge?: string;
}

const navItems: NavItem[] = [
  {
    href: "/reviews",
    label: "Front Office Console",
    icon: <LayoutDashboard className="h-5 w-5" />,
    roles: ["front_office", "admin"],
  },
  {
    href: "/clinical",
    label: "Clinical Reviewer",
    icon: <Stethoscope className="h-5 w-5" />,
    roles: ["clinical_reviewer", "admin"],
  },
  {
    href: "/bookings",
    label: "Booking Coordinator",
    icon: <CalendarCheck className="h-5 w-5" />,
    roles: ["booking_coordinator", "admin"],
  },
  {
    href: "/needs-attention",
    label: "Needs Attention",
    icon: <AlertTriangle className="h-5 w-5" />,
    roles: ["front_office", "admin"],
    badge: "3",
  },
  {
    href: "/admin",
    label: "Admin Dashboard",
    icon: <ShieldAlert className="h-5 w-5" />,
    roles: ["admin"],
  },
  {
    href: "/admin/users",
    label: "Staff & Users",
    icon: <Users className="h-5 w-5" />,
    roles: ["admin"],
  },
];

export function Sidebar({ userEmail, role = "front_office" }: { userEmail?: string; role?: UserRole }) {
  const pathname = usePathname();
  const [loggingOut, setLoggingOut] = useState(false);
  // §7 Server-side role enforcement: role is now passed from backend, not selectable by user
  const activeRole: UserRole = role;

  // Filter items based on backend-enforced role
  const visibleNav = navItems.filter((item) =>
    activeRole === "admin" ? true : item.roles.includes(activeRole)
  );

  return (
    <aside className="fixed left-0 top-0 z-40 h-screen w-64 border-r border-slate-200 bg-white dark:bg-slate-900 dark:border-slate-800 shadow-sm flex flex-col justify-between">
      <div>
        {/* Logo Section */}
        <div className="border-b border-slate-100 dark:border-slate-800 px-5 py-5">
          <Link href="/console" className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-teal-600 to-emerald-700 shadow-md">
              <Stethoscope className="h-6 w-6 text-white" strokeWidth={2.2} />
            </div>
            <div className="flex flex-col">
              <span className="text-lg font-bold text-slate-900 dark:text-slate-100 tracking-tight leading-tight">
                FirstMed
              </span>
              <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                Reply Review Console
              </span>
            </div>
          </Link>
        </div>

        {/* Navigation Section */}
        <nav className="space-y-1.5 px-3 py-4">
          <p className="px-3 text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2">
            Navigation
          </p>
          {visibleNav.map((item) => {
            const isActive = pathname === item.href || (item.href === "/console" && pathname === "/reviews");
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center justify-between rounded-lg px-3.5 py-2.5 text-sm font-medium transition-all duration-150",
                  isActive
                    ? "bg-teal-50 text-teal-800 dark:bg-teal-950/70 dark:text-teal-200 shadow-sm font-semibold border-l-4 border-teal-600"
                    : "text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800/60 hover:text-slate-900 dark:hover:text-slate-200"
                )}
              >
                <div className="flex items-center gap-3">
                  <span
                    className={cn(
                      "transition-colors",
                      isActive ? "text-teal-600 dark:text-teal-400" : "text-slate-400"
                    )}
                  >
                    {item.icon}
                  </span>
                  <span>{item.label}</span>
                </div>
                {item.badge && (
                  <span className="px-2 py-0.5 text-xs font-bold rounded-full bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300">
                    {item.badge}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>
      </div>

      {/* User Section */}
      <div className="border-t border-slate-100 dark:border-slate-800 p-4 space-y-3 bg-slate-50/50 dark:bg-slate-900/50">
        {/* Active Role Display (server-enforced, read-only) */}
        <div className="px-2 py-2 rounded-md bg-white dark:bg-slate-800 border border-slate-200/80 dark:border-slate-700">
          <p className="text-[10px] font-medium text-slate-400 uppercase tracking-wide">Role (Server-Enforced)</p>
          <p className="text-xs font-semibold text-slate-800 dark:text-slate-200 capitalize">{activeRole.replace("_", " ")}</p>
        </div>

        {userEmail && (
          <div className="px-2 py-1.5 rounded-md bg-white dark:bg-slate-800 border border-slate-200/80 dark:border-slate-700">
            <p className="text-[10px] font-medium text-slate-400 uppercase tracking-wide">User</p>
            <p className="text-xs font-semibold text-slate-800 dark:text-slate-200 truncate">{userEmail}</p>
          </div>
        )}

        <Button
          onClick={() => {
            setLoggingOut(true);
            try {
              clearToken();
              window.location.href = "/login";
            } catch (e) {
              console.error("Logout failed:", e);
              setLoggingOut(false);
            }
          }}
          disabled={loggingOut}
          variant="outline"
          size="sm"
          className="w-full justify-center gap-2 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:bg-red-50 dark:hover:bg-red-950/60 hover:text-red-700 dark:hover:text-red-300 hover:border-red-200"
        >
          {loggingOut ? <Loader2 className="h-4 w-4 animate-spin" /> : <LogOut className="h-4 w-4" />}
          Sign Out
        </Button>
      </div>
    </aside>
  );
}
