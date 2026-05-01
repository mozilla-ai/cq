import type { ReactNode } from "react"
import { Navigate } from "react-router"
import { useAuth } from "../auth"

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, loading } = useAuth()
  if (loading) return null
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <>{children}</>
}
