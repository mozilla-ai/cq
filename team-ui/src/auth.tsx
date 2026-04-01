import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from "react";
import { api, getToken, setToken, setOnUnauthorized } from "./api";

interface AuthState {
  username: string | null;
  isAuthenticated: boolean;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [username, setUsername] = useState<string | null>(null);
  const [loading, setLoading] = useState(() => !!getToken());

  const login = useCallback(async (user: string, pass: string) => {
    const resp = await api.login(user, pass);
    setToken(resp.token);
    setUsername(resp.username);
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUsername(null);
  }, []);

  // Register 401 handler so any API call that gets 401 triggers logout.
  useEffect(() => {
    setOnUnauthorized(logout);
    return () => setOnUnauthorized(() => {});
  }, [logout]);

  // Restore session from a persisted token on mount.
  useEffect(() => {
    const stored = getToken();
    if (!stored) return;
    let cancelled = false;
    api.me().then(
      (resp) => {
        if (!cancelled) setUsername(resp.username);
      },
      () => {
        if (!cancelled) setToken(null);
      },
    ).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <AuthContext.Provider
      value={{ username, isAuthenticated: !!username, loading, login, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components -- Standard React context pattern: provider + hook exported together.
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
