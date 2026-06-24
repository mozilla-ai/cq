import { useLayoutEffect } from "react"
import { BrowserRouter, Navigate, Route, Routes } from "react-router"
import { AuthProvider, useAuth } from "./auth"
import { Layout } from "./components/Layout"
import { ProtectedRoute } from "./components/ProtectedRoute"
import { ApiKeysPage } from "./pages/ApiKeysPage"
import { DashboardPage } from "./pages/DashboardPage"
import { LoginPage } from "./pages/LoginPage"
import { ReviewPage } from "./pages/ReviewPage"

function AppRoutes() {
  const { isAuthenticated } = useAuth()
  return (
    <Routes>
      <Route
        path="/login"
        element={
          isAuthenticated ? <Navigate to="/review" replace /> : <LoginPage />
        }
      />
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/review" element={<ReviewPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/settings/api-keys" element={<ApiKeysPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/review" replace />} />
    </Routes>
  )
}

function ThemeInitializer({ children }: { children: React.ReactNode }) {
  useLayoutEffect(() => {
    try {
      const stored = localStorage.getItem("cq-dark-mode")
      const dark =
        stored !== null
          ? stored === "true"
          : window.matchMedia("(prefers-color-scheme: dark)").matches
      document.documentElement.classList.toggle("dark", dark)
    } catch {
      // localStorage blocked (privacy mode, embedded context)
      if (window.matchMedia("(prefers-color-scheme: dark)").matches) {
        document.documentElement.classList.add("dark")
      }
    }
  }, [])
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ThemeInitializer>
          <AppRoutes />
        </ThemeInitializer>
      </AuthProvider>
    </BrowserRouter>
  )
}
