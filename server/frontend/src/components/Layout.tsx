import { useState, useEffect } from "react";
import { Link, Outlet, useLocation } from "react-router";
import { useAuth } from "../auth";
import { api } from "../api";

export function Layout() {
  const { username, logout } = useAuth();
  const location = useLocation();
  const [pendingCount, setPendingCount] = useState(0);
  const onDashboard = location.pathname === "/dashboard";

  useEffect(() => {
    if (onDashboard) return;
    function fetchCount() {
      api.reviewQueue(0, 0).then((r) => setPendingCount(r.total)).catch(() => {});
    }
    fetchCount();
    const interval = setInterval(fetchCount, 15_000);
    return () => clearInterval(interval);
  }, [onDashboard]);

  function navLink(path: string, label: string) {
    const active = location.pathname === path;
    return (
      <Link
        to={path}
        className={`px-3 py-1 text-sm font-medium whitespace-nowrap ${
          active
            ? "border-b-2 border-indigo-500 font-semibold text-gray-900"
            : "text-gray-500 hover:text-gray-900"
        }`}
      >
        {label}
        {path === "/review" && pendingCount > 0 && (
          <span className="ml-1.5 inline-flex items-center justify-center rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
            {pendingCount}
          </span>
        )}
      </Link>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 overflow-x-hidden">
      <nav className="bg-white border-b border-gray-200">
        <div className="max-w-2xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3 md:gap-6">
            <span className="text-lg font-bold text-indigo-600">cq</span>
            {navLink("/review", "Review")}
            {navLink("/dashboard", "Dashboard")}
            {navLink("/settings/api-keys", "API Keys")}
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden md:inline text-sm text-gray-500">{username}</span>
            <button
              onClick={logout}
              className="text-sm text-gray-400 hover:text-gray-700"
            >
              Logout
            </button>
          </div>
        </div>
      </nav>
      <main className="max-w-2xl mx-auto py-8 px-4">
        <Outlet context={{ setPendingCount }} />
      </main>
    </div>
  );
}
