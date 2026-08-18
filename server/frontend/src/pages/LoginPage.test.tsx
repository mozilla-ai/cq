import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { AuthProvider } from "../auth"
import { LoginPage } from "./LoginPage"

const originalFetch = globalThis.fetch

function mockFetch(status: number, body: unknown = {}) {
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  }) as unknown as typeof fetch
}

function submitLogin() {
  render(
    <AuthProvider>
      <LoginPage />
    </AuthProvider>,
  )
  fireEvent.change(screen.getByLabelText(/username/i), {
    target: { value: "demo" },
  })
  fireEvent.change(screen.getByLabelText(/password/i), {
    target: { value: "demo123" },
  })
  fireEvent.click(screen.getByRole("button", { name: /sign in/i }))
}

describe("LoginPage error reporting", () => {
  afterEach(() => {
    globalThis.fetch = originalFetch
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it("reports bad credentials when the API returns 401", async () => {
    mockFetch(401, { detail: "Invalid credentials" })
    submitLogin()
    expect(await screen.findByText("Invalid credentials")).toBeInTheDocument()
  })

  it("reports unavailability, not bad credentials, on a 502 from the dev proxy", async () => {
    mockFetch(502)
    submitLogin()
    expect(
      await screen.findByText(/unavailable \(HTTP 502\)/i),
    ).toBeInTheDocument()
    expect(screen.queryByText("Invalid credentials")).not.toBeInTheDocument()
  })

  it("reports unavailability when the server errors with 500", async () => {
    mockFetch(500, { detail: "boom" })
    submitLogin()
    expect(
      await screen.findByText(/unavailable \(HTTP 500\)/i),
    ).toBeInTheDocument()
  })

  it("surfaces the server's detail for other 4xx responses", async () => {
    mockFetch(429, { detail: "Too many attempts" })
    submitLogin()
    expect(await screen.findByText("Too many attempts")).toBeInTheDocument()
  })

  it("reports an unreachable server when fetch itself fails", async () => {
    globalThis.fetch = vi
      .fn()
      .mockRejectedValue(
        new TypeError("Failed to fetch"),
      ) as unknown as typeof fetch
    submitLogin()
    expect(
      await screen.findByText(/cannot reach the cq server/i),
    ).toBeInTheDocument()
  })
})
