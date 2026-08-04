import { useEffect, useState } from "react";
import { Sidebar } from "@/components/sidebar";
import { getToken, authHeader } from "@/lib/auth";
import { API_BASE_URL } from "@/lib/api";
import {
  Users,
  UserPlus,
  Shield,
  Clock,
  Building2,
  CheckCircle2,
  XCircle,
  RefreshCw,
} from "lucide-react";

interface UserItem {
  id: string;
  email: string;
  full_name: string;
  role: string;
  department: string;
  is_active: boolean;
  is_on_shift: boolean;
  shift_started_at?: string;
  created_at: string;
}

const DEPARTMENTS = [
  "FRONT_OFFICE",
  "PHYSIOTHERAPY",
  "GASTROENTEROLOGY",
  "LABORATORY",
  "NURSE_SPECIALIST",
];

const ROLES = [
  "ADMIN",
  "FRONT_OFFICE",
  "PHYSIOTHERAPY",
  "GASTROENTEROLOGY",
  "LABORATORY",
  "NURSE_SPECIALIST",
];

export default function AdminUsersPage() {
  const [users, setUsers] = useState<UserItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [userEmail, setUserEmail] = useState("");

  // Create User Modal
  const [showModal, setShowModal] = useState(false);
  const [newEmail, setNewEmail] = useState("");
  const [newFullName, setNewFullName] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState("FRONT_OFFICE");
  const [newDepartment, setNewDepartment] = useState("FRONT_OFFICE");
  const [submitting, setSubmitting] = useState(false);

  const fetchUsers = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/admin/users`, {
        headers: { ...authHeader() },
      });
      if (!res.ok) {
        throw new Error(`Failed to load users (${res.status})`);
      }
      const data = await res.json();
      setUsers(data.users || []);
    } catch (err: any) {
      setError(err.message || "Failed to fetch users");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
    // decode email if available
    const token = getToken();
    if (token) {
      try {
        const payload = JSON.parse(atob(token.split(".")[1]));
        setUserEmail(payload.sub || "Admin");
      } catch (e) {}
    }
  }, []);

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/admin/users`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeader(),
        },
        body: JSON.stringify({
          email: newEmail,
          full_name: newFullName,
          password: newPassword,
          role: newRole,
          department: newDepartment,
          is_on_shift: true,
        }),
      });
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to create user");
      }
      setShowModal(false);
      setNewEmail("");
      setNewFullName("");
      setNewPassword("");
      fetchUsers();
    } catch (err: any) {
      alert(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleToggleShift = async (user: UserItem) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/admin/users/${user.id}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          ...authHeader(),
        },
        body: JSON.stringify({
          is_on_shift: !user.is_on_shift,
        }),
      });
      if (res.ok) {
        fetchUsers();
      }
    } catch (e) {}
  };

  const handleRoleChange = async (user: UserItem, role: string) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/admin/users/${user.id}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          ...authHeader(),
        },
        body: JSON.stringify({
          role,
          department: role !== "ADMIN" ? role : user.department,
        }),
      });
      if (res.ok) {
        fetchUsers();
      }
    } catch (e) {}
  };

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar userEmail={userEmail} />

      <main className="flex-1 pl-64 p-8">
        <div className="max-w-7xl mx-auto space-y-6">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-slate-900 flex items-center gap-2">
                <Users className="h-7 w-7 text-indigo-600" />
                Staff & Department Management
              </h1>
              <p className="text-sm text-slate-500 mt-1">
                Configure role-based access control, department isolation, and staff active shifts.
              </p>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={fetchUsers}
                className="p-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 transition"
                title="Refresh"
              >
                <RefreshCw className="h-4 w-4" />
              </button>
              <button
                onClick={() => setShowModal(true)}
                className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium px-4 py-2 rounded-lg shadow transition"
              >
                <UserPlus className="h-4 w-4" />
                Add Staff User
              </button>
            </div>
          </div>

          {/* User Table Card */}
          <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
            {loading ? (
              <div className="p-12 text-center text-slate-400">Loading users...</div>
            ) : error ? (
              <div className="p-12 text-center text-red-500">{error}</div>
            ) : (
              <table className="w-full text-left text-sm text-slate-600">
                <thead className="bg-slate-50 border-b border-slate-200 text-slate-700 font-semibold uppercase text-xs">
                  <tr>
                    <th className="px-6 py-4">User</th>
                    <th className="px-6 py-4">Role</th>
                    <th className="px-6 py-4">Department</th>
                    <th className="px-6 py-4">Active Shift</th>
                    <th className="px-6 py-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {users.map((u) => (
                    <tr key={u.id} className="hover:bg-slate-50/50 transition">
                      <td className="px-6 py-4">
                        <div className="font-semibold text-slate-900">{u.full_name || u.email}</div>
                        <div className="text-xs text-slate-400">{u.email}</div>
                      </td>
                      <td className="px-6 py-4">
                        <select
                          value={u.role}
                          onChange={(e) => handleRoleChange(u, e.target.value)}
                          className="bg-slate-50 border border-slate-200 text-xs font-semibold rounded-md px-2 py-1 focus:ring-2 focus:ring-indigo-500"
                        >
                          {ROLES.map((r) => (
                            <option key={r} value={r}>
                              {r}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="px-6 py-4">
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-slate-100 text-slate-700">
                          <Building2 className="h-3 w-3 text-slate-400" />
                          {u.department || u.role}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <button
                          onClick={() => handleToggleShift(u)}
                          className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium transition ${
                            u.is_on_shift
                              ? "bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100"
                              : "bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100"
                          }`}
                        >
                          <Clock className="h-3.5 w-3.5" />
                          {u.is_on_shift ? "On Shift" : "Off Duty"}
                        </button>
                      </td>
                      <td className="px-6 py-4 text-right">
                        <span className="text-xs text-slate-400">Active</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* Create User Modal */}
        {showModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm">
            <div className="bg-white rounded-2xl shadow-xl border border-slate-100 w-full max-w-md p-6 space-y-5">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                  <UserPlus className="h-5 w-5 text-indigo-600" />
                  Add Staff Member
                </h3>
                <button
                  onClick={() => setShowModal(false)}
                  className="text-slate-400 hover:text-slate-600 text-sm font-semibold"
                >
                  ✕
                </button>
              </div>

              <form onSubmit={handleCreateUser} className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">
                    Full Name
                  </label>
                  <input
                    type="text"
                    required
                    value={newFullName}
                    onChange={(e) => setNewFullName(e.target.value)}
                    placeholder="Dr. Jane Smith"
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">
                    Email Address
                  </label>
                  <input
                    type="email"
                    required
                    value={newEmail}
                    onChange={(e) => setNewEmail(e.target.value)}
                    placeholder="jane.smith@firstmed.com"
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">
                    Password
                  </label>
                  <input
                    type="password"
                    required
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="••••••••"
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-slate-700 mb-1">
                      Assigned Role
                    </label>
                    <select
                      value={newRole}
                      onChange={(e) => {
                        setNewRole(e.target.value);
                        setNewDepartment(e.target.value);
                      }}
                      className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white focus:ring-2 focus:ring-indigo-500 outline-none"
                    >
                      {ROLES.map((r) => (
                        <option key={r} value={r}>
                          {r}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-700 mb-1">
                      Department
                    </label>
                    <select
                      value={newDepartment}
                      onChange={(e) => setNewDepartment(e.target.value)}
                      className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white focus:ring-2 focus:ring-indigo-500 outline-none"
                    >
                      {DEPARTMENTS.map((d) => (
                        <option key={d} value={d}>
                          {d}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="flex justify-end gap-2 border-t border-slate-100 pt-4 mt-6">
                  <button
                    type="button"
                    onClick={() => setShowModal(false)}
                    className="px-4 py-2 rounded-lg text-sm font-medium text-slate-600 hover:bg-slate-100 transition"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={submitting}
                    className="px-4 py-2 rounded-lg text-sm font-medium bg-indigo-600 hover:bg-indigo-700 text-white shadow transition"
                  >
                    {submitting ? "Saving..." : "Create Staff User"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
