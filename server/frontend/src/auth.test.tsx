import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { AuthProvider, useAuth } from "./auth";
import { setToken } from "./api";

const TOKEN_KEY = "cq_auth_token";

const originalFetch = globalThis.fetch;

function mockFetch(response: object, status = 200) {
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(response),
  });
}

function AuthStatus() {
  const { isAuthenticated, username, loading } = useAuth();
  return (
    <div>
      <span data-testid="status">
        {isAuthenticated ? "authenticated" : "unauthenticated"}
      </span>
      <span data-testid="username">{username ?? ""}</span>
      <span data-testid="loading">{String(loading)}</span>
    </div>
  );
}

describe("AuthProvider session restore", () => {
  beforeEach(() => {
    localStorage.clear();
    setToken(null);
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("restores session from localStorage on mount", async () => {
    localStorage.setItem(TOKEN_KEY, "valid-jwt");
    mockFetch({ username: "alice", created_at: "2024-01-01" });

    render(
      <AuthProvider>
        <AuthStatus />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("authenticated");
    });
    expect(screen.getByTestId("username")).toHaveTextContent("alice");
  });

  it("clears invalid token from localStorage on mount", async () => {
    localStorage.setItem(TOKEN_KEY, "expired-jwt");
    mockFetch({ detail: "Invalid or expired token" }, 401);

    render(
      <AuthProvider>
        <AuthStatus />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
    });
    expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated");
  });

  it("does nothing when no token in localStorage", () => {
    const fetchSpy = vi.fn();
    globalThis.fetch = fetchSpy;

    render(
      <AuthProvider>
        <AuthStatus />
      </AuthProvider>,
    );

    expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("reports loading while session restore is in-flight", async () => {
    localStorage.setItem(TOKEN_KEY, "valid-jwt");

    let resolveFetch!: (value: Response) => void;
    globalThis.fetch = vi.fn().mockReturnValue(
      new Promise<Response>((resolve) => {
        resolveFetch = resolve;
      }),
    );

    render(
      <AuthProvider>
        <AuthStatus />
      </AuthProvider>,
    );

    // While /auth/me is pending, loading should be true.
    expect(screen.getByTestId("loading")).toHaveTextContent("true");
    expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated");

    // Resolve the fetch.
    resolveFetch({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ username: "alice", created_at: "2024-01-01" }),
    } as Response);

    await waitFor(() => {
      expect(screen.getByTestId("loading")).toHaveTextContent("false");
    });
    expect(screen.getByTestId("status")).toHaveTextContent("authenticated");
  });

  it("is not loading when no stored token exists", () => {
    const fetchSpy = vi.fn();
    globalThis.fetch = fetchSpy;

    render(
      <AuthProvider>
        <AuthStatus />
      </AuthProvider>,
    );

    expect(screen.getByTestId("loading")).toHaveTextContent("false");
  });
});
