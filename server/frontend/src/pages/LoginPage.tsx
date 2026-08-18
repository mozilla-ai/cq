import { type FormEvent, useState } from "react"
import { ApiError } from "../api"
import { useAuth } from "../auth"

// Only a 401 means the username/password were wrong. Every other failure —
// an unreachable API, a dev-proxy error, a 5xx — is an availability problem,
// and reporting it as "Invalid credentials" sends people looking for the
// wrong bug entirely.
function loginErrorMessage(err: unknown): string {
  if (!(err instanceof ApiError)) {
    return "Cannot reach the cq server. Check that the API is running."
  }
  if (err.status === 401) {
    return "Invalid credentials"
  }
  if (err.status >= 500) {
    return `The cq server is unavailable (HTTP ${err.status}).`
  }
  return err.message
}

export function LoginPage() {
  const { login } = useAuth()
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await login(username, password)
    } catch (err) {
      setError(loginErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-slate-950">
      <form
        onSubmit={handleSubmit}
        className="bg-white dark:bg-slate-900 p-8 rounded-lg shadow-sm border border-gray-200 dark:border-slate-800 w-full max-w-sm"
      >
        <h1 className="text-3xl font-bold mb-6 text-center text-indigo-600 dark:text-indigo-400">
          cq
        </h1>
        {error && (
          <p className="text-red-600 dark:text-red-400 text-sm mb-4 text-center">
            {error}
          </p>
        )}
        <label className="block mb-4">
          <span className="text-sm font-medium text-gray-700 dark:text-slate-300">
            Username
          </span>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="mt-1 block w-full rounded-lg border border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-gray-900 dark:text-slate-100 px-3 py-2 focus:border-indigo-500 focus:ring-indigo-500"
            required
          />
        </label>
        <label className="block mb-6">
          <span className="text-sm font-medium text-gray-700 dark:text-slate-300">
            Password
          </span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 block w-full rounded-lg border border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-gray-900 dark:text-slate-100 px-3 py-2 focus:border-indigo-500 focus:ring-indigo-500"
            required
          />
        </label>
        <button
          type="submit"
          disabled={loading}
          className="w-full bg-indigo-600 text-white py-2 rounded-lg font-medium hover:bg-indigo-700 disabled:opacity-50"
        >
          {loading ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </div>
  )
}
