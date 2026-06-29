import { useEffect, useRef, useState } from "react"
import { Link, Outlet, useLocation } from "react-router"
import { api } from "../api"
import { useAuth } from "../auth"

function SunIcon() {
  return (
    <svg
      aria-hidden="true"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
      className="h-5 w-5"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M12 3v2.25m6.364.386-1.591 1.591M21 12h-2.25m-.386 6.364-1.591-1.591M12 18.75V21m-4.773-4.227-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0Z"
      />
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg
      aria-hidden="true"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
      className="h-5 w-5"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M21.752 15.002A9.72 9.72 0 0 1 18 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 0 0 3 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 0 0 9.002-5.998Z"
      />
    </svg>
  )
}

export function Layout() {
  const { username, logout } = useAuth()
  const location = useLocation()
  const [pendingCount, setPendingCount] = useState(0)
  const [dark, setDark] = useState(() =>
    document.documentElement.classList.contains("dark"),
  )
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const onDashboard = location.pathname === "/dashboard"

  useEffect(() => {
    if (onDashboard) return
    function fetchCount() {
      api
        .reviewQueue(0, 0)
        .then((r) => setPendingCount(r.total))
        .catch(() => {})
    }
    fetchCount()
    const interval = setInterval(fetchCount, 15_000)
    return () => clearInterval(interval)
  }, [onDashboard])

  useEffect(() => {
    if (!menuOpen) return
    function handlePointerDown(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false)
      }
    }
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setMenuOpen(false)
    }
    document.addEventListener("mousedown", handlePointerDown)
    document.addEventListener("keydown", handleKeyDown)
    return () => {
      document.removeEventListener("mousedown", handlePointerDown)
      document.removeEventListener("keydown", handleKeyDown)
    }
  }, [menuOpen])

  function toggleTheme() {
    setDark((prev) => {
      const next = !prev
      document.documentElement.classList.toggle("dark", next)
      try {
        localStorage.setItem("cq-dark-mode", String(next))
      } catch {
        // localStorage blocked (privacy mode, embedded context)
      }
      return next
    })
  }

  function navLink(path: string, label: string) {
    const active = location.pathname === path
    return (
      <Link
        to={path}
        className={`px-3 py-1 text-sm font-medium whitespace-nowrap ${
          active
            ? "border-b-2 border-indigo-500 font-semibold text-gray-900 dark:text-slate-100"
            : "text-gray-500 hover:text-gray-900 dark:text-slate-400 dark:hover:text-slate-200"
        }`}
      >
        {label}
        {path === "/review" && pendingCount > 0 && (
          <span className="ml-1.5 inline-flex items-center justify-center rounded-full bg-amber-100 dark:bg-amber-500/20 px-2 py-0.5 text-xs font-medium text-amber-700 dark:text-amber-300">
            {pendingCount}
          </span>
        )}
      </Link>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-slate-950 overflow-x-hidden">
      <nav className="bg-white dark:bg-slate-900 border-b border-gray-200 dark:border-slate-800">
        <div className="max-w-2xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3 md:gap-6">
            <span className="text-lg font-bold text-indigo-600 dark:text-indigo-400">
              cq
            </span>
            {navLink("/review", "Review")}
            {navLink("/dashboard", "Dashboard")}
            {navLink("/settings/api-keys", "API Keys")}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={toggleTheme}
              aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
              title={dark ? "Switch to light mode" : "Switch to dark mode"}
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 hover:text-gray-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200 dark:focus-visible:ring-offset-slate-900"
            >
              {dark ? <MoonIcon /> : <SunIcon />}
            </button>
            <div className="relative" ref={menuRef}>
              <button
                type="button"
                onClick={() => setMenuOpen((open) => !open)}
                aria-haspopup="menu"
                aria-expanded={menuOpen}
                className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 px-2.5 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800 dark:focus-visible:ring-offset-slate-900"
              >
                <span className="max-w-[10rem] truncate">{username}</span>
                <svg
                  aria-hidden="true"
                  className={`h-4 w-4 text-gray-400 dark:text-slate-500 transition-transform ${
                    menuOpen ? "rotate-180" : ""
                  }`}
                  viewBox="0 0 20 20"
                  fill="currentColor"
                >
                  <path
                    fillRule="evenodd"
                    d="M5.23 7.21a.75.75 0 011.06.02L10 11.06l3.71-3.83a.75.75 0 111.08 1.04l-4.25 4.39a.75.75 0 01-1.08 0L5.21 8.27a.75.75 0 01.02-1.06z"
                    clipRule="evenodd"
                  />
                </svg>
              </button>
              {menuOpen && (
                <div
                  role="menu"
                  className="absolute right-0 mt-1 w-max min-w-full rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 py-1 shadow-lg z-10"
                >
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setMenuOpen(false)
                      logout()
                    }}
                    className="block w-full px-3 py-1.5 text-center text-sm text-gray-700 hover:bg-gray-100 dark:text-slate-200 dark:hover:bg-slate-800"
                  >
                    Logout
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </nav>
      <main className="max-w-2xl mx-auto py-8 px-4">
        <Outlet context={{ setPendingCount }} />
      </main>
    </div>
  )
}
