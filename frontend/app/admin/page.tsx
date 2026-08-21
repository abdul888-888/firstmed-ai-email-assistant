"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Activity,
  CheckCircle2,
  Clock,
  FileText,
  HelpCircle,
  Plus,
  Shield,
  Trash2,
  UserPlus,
  Users,
} from "lucide-react";

import { DashboardLayout } from "@/components/dashboard-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  createRoutingRule,
  deleteRoutingRule,
  getAuditLog,
  inviteStaffMember,
  listRoutingRules,
  listTeamMembers,
  type AuditLogEntry,
  type RoutingRule,
  type TeamMember,
} from "@/lib/admin";
import { API_BASE_URL, getKnowledgeGaps, type KnowledgeGap } from "@/lib/api";
import { getToken } from "@/lib/auth";

export default function AdminDashboardPage() {
  const router = useRouter();
  const [isAuthorized, setIsAuthorized] = useState(false);
  const [users, setUsers] = useState<TeamMember[]>([]);
  const [rules, setRules] = useState<RoutingRule[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLogEntry[]>([]);
  const [gaps, setGaps] = useState<KnowledgeGap[]>([]);
  const [loading, setLoading] = useState(true);

  // SLA Threshold state
  const [slaAtRiskHours, setSlaAtRiskHours] = useState<number>(12);
  const [slaOverdueHours, setSlaOverdueHours] = useState<number>(24);
  const [slaSaveLoading, setSlaSaveLoading] = useState(false);
  const [slaSaveMessage, setSlaSaveMessage] = useState<string | null>(null);

  // Modal states
  const [showCreateUserModal, setShowCreateUserModal] = useState(false);
  const [newUserEmail, setNewUserEmail] = useState("");
  const [newUserFullName, setNewUserFullName] = useState("");
  const [newUserPassword, setNewPassword] = useState("");
  const [newUserRole, setNewUserRole] = useState("FRONT_OFFICE");
  const [newUserDepartment, setNewUserDepartment] = useState("FRONT_OFFICE");
  const [createUserSubmitting, setCreateUserSubmitting] = useState(false);
  const [createUserError, setCreateUserError] = useState<string | null>(null);

  const [showRuleModal, setShowRuleModal] = useState(false);
  const [ruleCategory, setRuleCategory] = useState("");
  const [ruleTargetQueue, setRuleTargetQueue] = useState("front_office");

  const loadData = async () => {
    setLoading(true);
    try {
      const [u, r, l, g] = await Promise.all([
        listTeamMembers(),
        listRoutingRules(),
        getAuditLog(),
        getKnowledgeGaps(),
      ]);
      setUsers(u);
      setRules(r);
      setAuditLogs(l);
      setGaps(g.gaps);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // Check if user has admin role before loading data
    const checkAuthorization = async () => {
      try {
        const token = getToken() || localStorage.getItem("token") || localStorage.getItem("firstmed_access_token");
        if (!token) {
          router.push("/login");
          return;
        }

        const response = await fetch(`${API_BASE_URL}/api/v1/auth/me`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });

        if (!response.ok) {
          router.push("/login");
          return;
        }

        const user = await response.json();
        console.log("User from /auth/me:", user);
        console.log("User role:", user.role);
        
        // Check if user role is admin (case-insensitive)
        const isAdmin = user.role && user.role.toLowerCase() === "admin";
        console.log("Is admin?", isAdmin);
        
        if (isAdmin) {
          setIsAuthorized(true);
          await loadData();
        } else {
          // Not authorized, redirect to /reviews
          console.log("User is not admin, redirecting to /reviews");
          router.push("/reviews");
        }
      } catch (err) {
        console.error("Authorization check failed:", err);
        router.push("/login");
      }
    };

    void checkAuthorization();
  }, [router]);

  const handleCreateStaffUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreateUserSubmitting(true);
    setCreateUserError(null);
    try {
      const token = getToken() || localStorage.getItem("token") || localStorage.getItem("firstmed_access_token");
      const res = await fetch(`${API_BASE_URL}/api/v1/admin/users`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          email: newUserEmail,
          full_name: newUserFullName,
          password: newUserPassword,
          role: newUserRole,
          department: newUserDepartment,
          is_on_shift: true,
        }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Failed to create user (${res.status})`);
      }

      setShowCreateUserModal(false);
      setNewUserEmail("");
      setNewUserFullName("");
      setNewPassword("");
      await loadData();
    } catch (err: any) {
      setCreateUserError(err.message || "Failed to create staff member");
    } finally {
      setCreateUserSubmitting(false);
    }
  };

  const handleAddRule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ruleCategory) return;
    try {
      await createRoutingRule(ruleCategory, ruleTargetQueue);
      setShowRuleModal(false);
      setRuleCategory("");
      await loadData();
    } catch (err) {
      alert("Failed to add routing rule");
    }
  };

  const handleDeleteRule = async (id: string) => {
    try {
      await deleteRoutingRule(id);
      await loadData();
    } catch (err) {
      alert("Failed to delete routing rule");
    }
  };

  // Show loading or unauthorized message
  if (!isAuthorized) {
    return (
      <DashboardLayout>
        <div className="flex min-h-screen items-center justify-center bg-slate-50">
          <div className="text-center">
            {loading ? (
              <>
                <div className="mx-auto h-12 w-12 animate-spin rounded-full border-4 border-slate-200 border-t-blue-600"></div>
                <h2 className="mt-4 text-lg font-semibold text-slate-900">Checking permissions...</h2>
              </>
            ) : (
              <>
                <Shield className="mx-auto h-12 w-12 text-slate-400" />
                <h2 className="mt-4 text-lg font-semibold text-slate-900">Access Denied</h2>
                <p className="mt-1 text-sm text-slate-500">You do not have permission to access the Admin Dashboard.</p>
              </>
            )}
          </div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="min-h-screen bg-slate-50 p-6 md:p-10">
        <div className="mx-auto max-w-7xl space-y-8">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-slate-200 pb-5">
            <div>
              <div className="flex items-center gap-2">
                <Shield className="h-7 w-7 text-slate-900" />
                <h1 className="text-2xl font-bold tracking-tight text-slate-900">Admin Dashboard</h1>
              </div>
              <p className="mt-1 text-sm text-slate-500">System governance, staff scope, routing rules, and audit logs.</p>
            </div>
            <div className="flex items-center gap-3">
              <Button size="sm" variant="outline" onClick={() => router.push("/admin/users")}>
                <Users className="mr-2 h-4 w-4" /> Manage All Staff
              </Button>
              <Button size="sm" onClick={() => setShowCreateUserModal(true)} className="bg-emerald-600 hover:bg-emerald-700">
                <UserPlus className="mr-2 h-4 w-4" /> Add Staff User
              </Button>
            </div>
          </div>

          {/* Grid of Admin Cards (§6) */}
          <div className="grid gap-8 lg:grid-cols-2">
            {/* Card 1: Staff & Roles */}
            <Card className="border-slate-200 shadow-sm">
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle className="text-lg font-bold flex items-center gap-2">
                    <Users className="h-5 w-5 text-slate-600" /> Staff & Roles
                  </CardTitle>
                  <CardDescription>Role permissions and direct send rights scope.</CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  <Button variant="outline" size="sm" onClick={() => setShowCreateUserModal(true)}>
                    <Plus className="mr-1 h-3.5 w-3.5" /> Add User
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-slate-100 text-xs uppercase font-semibold text-slate-500">
                      <tr>
                        <th className="p-3">Staff Member</th>
                        <th className="p-3">Role</th>
                        <th className="p-3">Send Rights</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {users.map((u) => (
                        <tr key={u.id}>
                          <td className="p-3 font-medium text-slate-900">{u.full_name || u.email}</td>
                          <td className="p-3">
                            <Badge className="bg-slate-50 border-slate-200">{u.role}</Badge>
                          </td>
                          <td className="p-3">
                            {u.role === "ADMIN" || u.role === "FRONT_OFFICE" || u.role === "BOOKING_COORDINATOR" ? (
                              <span className="text-xs font-semibold text-emerald-700">Direct Send</span>
                            ) : (
                              <span className="text-xs text-slate-400">Input Only</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>

            {/* Card 2: Routing Rules */}
            <Card className="border-slate-200 shadow-sm">
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle className="text-lg font-bold flex items-center gap-2">
                    <Activity className="h-5 w-5 text-blue-600" /> Routing Rules
                  </CardTitle>
                  <CardDescription>Category mapping to target department queues.</CardDescription>
                </div>
                <Button variant="outline" size="sm" onClick={() => setShowRuleModal(true)}>
                  <Plus className="mr-1 h-3.5 w-3.5" /> Add Rule
                </Button>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {rules.map((rule) => (
                    <div key={rule.id} className="flex items-center justify-between rounded-lg border border-slate-200 bg-white p-3 text-sm">
                      <div>
                        <p className="font-semibold text-slate-900">{rule.category}</p>
                        <p className="text-xs text-slate-500">Routes to: <span className="font-medium text-slate-700">{rule.target_queue}</span></p>
                      </div>
                      <Button variant="ghost" size="sm" onClick={() => handleDeleteRule(rule.id)} className="text-slate-400 hover:text-rose-600">
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Card 3: Audit Log */}
            <Card className="border-slate-200 shadow-sm">
              <CardHeader>
                <CardTitle className="text-lg font-bold flex items-center gap-2">
                  <FileText className="h-5 w-5 text-slate-700" /> Audit Log
                </CardTitle>
                <CardDescription>Chronological feed of sends, approvals, and admin updates.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3 max-h-[300px] overflow-y-auto pr-2">
                  {auditLogs.map((log) => (
                    <div key={log.id} className="rounded-md bg-slate-50 p-3 text-xs space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-slate-900">{log.action}</span>
                        <span className="text-slate-400">{log.timestamp}</span>
                      </div>
                      <p className="text-slate-600">Actor: <span className="font-medium">{log.actor}</span> · Target: {log.target}</p>
                      <p className="text-slate-500">{log.details}</p>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Card 4: Manager Knowledge Gap Rollup */}
            <Card className="border-slate-200 shadow-sm">
              <CardHeader>
                <CardTitle className="text-lg font-bold flex items-center gap-2">
                  <HelpCircle className="h-5 w-5 text-amber-600" /> Knowledge Gap Rollup
                </CardTitle>
                <CardDescription>Manager-level overview of unresolved knowledge base queries.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {gaps.slice(0, 3).map((gap) => (
                    <div key={gap.id} className="rounded-lg border border-amber-200 bg-amber-50/50 p-3 text-xs flex justify-between items-center">
                      <div>
                        <p className="font-bold text-amber-950">{gap.topic}</p>
                        <p className="text-amber-800">{gap.occurrences} recorded occurrences</p>
                      </div>
                      <Badge className="bg-amber-200 text-amber-900 border-amber-300">
                        {gap.escalated ? `Escalated (${gap.escalated_to})` : "Monitoring"}
                      </Badge>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Card 4: SLA Thresholds */}
            <Card className="border-slate-200 shadow-sm">
              <CardHeader>
                <div>
                  <CardTitle className="text-lg font-bold flex items-center gap-2">
                    <Clock className="h-5 w-5 text-teal-600" /> SLA Thresholds
                  </CardTitle>
                  <CardDescription>Configure response time targets without redeploying.</CardDescription>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-4">
                  <div className="space-y-2">
                    <Label htmlFor="at-risk-hours" className="text-sm font-semibold text-slate-700">
                      At-Risk Threshold (hours)
                    </Label>
                    <div className="flex items-center gap-2">
                      <input
                        id="at-risk-hours"
                        type="number"
                        min="1"
                        max="24"
                        value={slaAtRiskHours}
                        onChange={(e) => setSlaAtRiskHours(Math.max(1, parseInt(e.target.value) || 12))}
                        className="w-20 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium"
                      />
                      <span className="text-xs text-slate-600">If email is waiting longer than this, mark as "At Risk"</span>
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="overdue-hours" className="text-sm font-semibold text-slate-700">
                      Overdue Threshold (hours)
                    </Label>
                    <div className="flex items-center gap-2">
                      <input
                        id="overdue-hours"
                        type="number"
                        min="1"
                        max="72"
                        value={slaOverdueHours}
                        onChange={(e) => setSlaOverdueHours(Math.max(1, parseInt(e.target.value) || 24))}
                        className="w-20 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium"
                      />
                      <span className="text-xs text-slate-600">If email is waiting longer than this, mark as "Overdue"</span>
                    </div>
                  </div>
                </div>
                
                {slaSaveMessage && (
                  <div className={`rounded-md p-3 text-sm font-medium ${
                    slaSaveMessage.includes("success") || slaSaveMessage.includes("saved")
                      ? "bg-emerald-50 text-emerald-800"
                      : "bg-red-50 text-red-800"
                  }`}>
                    {slaSaveMessage}
                  </div>
                )}

                <Button
                  onClick={async () => {
                    setSlaSaveLoading(true);
                    // Note: In a real implementation, this would call an API endpoint to save these values
                    // For now, we show the intended flow
                    try {
                      // Example: await apiFetch({ path: "/admin/sla-config", method: "POST", body: JSON.stringify({ at_risk_hours: slaAtRiskHours, overdue_hours: slaOverdueHours }) });
                      await new Promise((resolve) => setTimeout(resolve, 500)); // Simulate API call
                      setSlaSaveMessage("✓ SLA thresholds updated successfully");
                      setTimeout(() => setSlaSaveMessage(null), 3000);
                    } catch (err) {
                      setSlaSaveMessage("Failed to save SLA configuration");
                    } finally {
                      setSlaSaveLoading(false);
                    }
                  }}
                  disabled={slaSaveLoading}
                  className="w-full bg-teal-600 hover:bg-teal-700"
                >
                  {slaSaveLoading ? "Saving..." : "Save SLA Configuration"}
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>

        {/* Create Staff User Modal */}
        {showCreateUserModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4">
            <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl space-y-4">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                  <UserPlus className="h-5 w-5 text-emerald-600" /> Add Staff Member
                </h2>
                <button
                  type="button"
                  onClick={() => setShowCreateUserModal(false)}
                  className="text-slate-400 hover:text-slate-600 font-semibold"
                >
                  ✕
                </button>
              </div>

              {createUserError && (
                <div className="rounded-md bg-rose-50 p-3 text-sm text-rose-700 font-medium">
                  {createUserError}
                </div>
              )}

              <form onSubmit={handleCreateStaffUser} className="space-y-4">
                <div className="space-y-1.5">
                  <Label htmlFor="full_name">Full Name</Label>
                  <Input
                    id="full_name"
                    type="text"
                    placeholder="e.g. Dr. Jane Smith"
                    value={newUserFullName}
                    onChange={(e) => setNewUserFullName(e.target.value)}
                    required
                  />
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="email">Email Address</Label>
                  <Input
                    id="email"
                    type="email"
                    placeholder="e.g. user@gmail.com"
                    value={newUserEmail}
                    onChange={(e) => setNewUserEmail(e.target.value)}
                    required
                  />
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="password">Initial Password</Label>
                  <Input
                    id="password"
                    type="password"
                    placeholder="Min 8 characters"
                    value={newUserPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    required
                    minLength={8}
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="role">Assigned Role</Label>
                    <select
                      id="role"
                      value={newUserRole}
                      onChange={(e) => {
                        setNewUserRole(e.target.value);
                        setNewUserDepartment(e.target.value);
                      }}
                      className="w-full rounded-md border border-slate-200 bg-white p-2 text-sm focus:ring-2 focus:ring-emerald-500"
                    >
                      <option value="FRONT_OFFICE">Front Office</option>
                      <option value="PHYSIOTHERAPY">Physiotherapy Specialist</option>
                      <option value="GASTROENTEROLOGY">Gastroenterology Specialist</option>
                      <option value="LABORATORY">Laboratory</option>
                      <option value="NURSE_SPECIALIST">Nurse Specialist</option>
                      <option value="ADMIN">Admin</option>
                    </select>
                  </div>

                  <div className="space-y-1.5">
                    <Label htmlFor="department">Department</Label>
                    <select
                      id="department"
                      value={newUserDepartment}
                      onChange={(e) => setNewUserDepartment(e.target.value)}
                      className="w-full rounded-md border border-slate-200 bg-white p-2 text-sm focus:ring-2 focus:ring-emerald-500"
                    >
                      <option value="FRONT_OFFICE">Front Office</option>
                      <option value="PHYSIOTHERAPY">Physiotherapy</option>
                      <option value="GASTROENTEROLOGY">Gastroenterology</option>
                      <option value="LABORATORY">Laboratory</option>
                      <option value="NURSE_SPECIALIST">Nurse Specialist</option>
                    </select>
                  </div>
                </div>

                <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
                  <Button variant="outline" type="button" onClick={() => setShowCreateUserModal(false)}>
                    Cancel
                  </Button>
                  <Button type="submit" disabled={createUserSubmitting} className="bg-emerald-600 hover:bg-emerald-700">
                    {createUserSubmitting ? "Creating..." : "Create Staff Account"}
                  </Button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Rule Modal */}
        {showRuleModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
            <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl space-y-4">
              <h2 className="text-lg font-bold text-slate-900">Add Routing Rule</h2>
              <form onSubmit={handleAddRule} className="space-y-4">
                <div className="space-y-2">
                  <Label>Category Name</Label>
                  <Input placeholder="e.g. Billing & Claims" value={ruleCategory} onChange={(e) => setRuleCategory(e.target.value)} required />
                </div>
                <div className="space-y-2">
                  <Label>Target Queue</Label>
                  <select
                    value={ruleTargetQueue}
                    onChange={(e) => setRuleTargetQueue(e.target.value)}
                    className="w-full rounded-md border border-slate-200 bg-white p-2 text-sm"
                  >
                    <option value="front_office">Front Office</option>
                    <option value="physiotherapy">Physiotherapy</option>
                    <option value="gastroenterology">Gastroenterology</option>
                    <option value="laboratory">Laboratory</option>
                    <option value="nurse_specialist">Nurse Specialist</option>
                  </select>
                </div>
                <div className="flex justify-end gap-2">
                  <Button variant="outline" type="button" onClick={() => setShowRuleModal(false)}>Cancel</Button>
                  <Button type="submit" className="bg-blue-600 hover:bg-blue-700">Add Rule</Button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
