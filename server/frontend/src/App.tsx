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

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}
