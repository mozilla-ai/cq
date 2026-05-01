import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { ApiKeysPage } from "./ApiKeysPage"

const originalFetch = globalThis.fetch
const originalClipboard = navigator.clipboard

type MockResponse = {
  ok: boolean
  status: number
  body: unknown
}

function queueResponses(responses: MockResponse[]) {
  let i = 0
  globalThis.fetch = vi.fn().mockImplementation(() => {
    const resp = responses[i] ?? responses[responses.length - 1]
    i += 1
    return Promise.resolve({
      ok: resp.ok,
      status: resp.status,
      json: () => Promise.resolve(resp.body),
    })
  }) as unknown as typeof fetch
}

describe("ApiKeysPage", () => {
  beforeEach(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    })
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: originalClipboard,
    })
    vi.restoreAllMocks()
  })

  it("renders the empty state when no keys exist", async () => {
    queueResponses([{ ok: true, status: 200, body: { data: [], count: 0 } }])
    render(<ApiKeysPage />)
    expect(await screen.findByText(/no api keys yet/i)).toBeInTheDocument()
  })

  it("creates a key and shows the plaintext modal once", async () => {
    const listedKey = {
      id: "id1",
      name: "laptop",
      labels: [],
      prefix: "cqa_abcd",
      ttl: "90d",
      expires_at: "2027-01-01T00:00:00+00:00",
      created_at: "2026-04-16T00:00:00+00:00",
      last_used_at: null,
      revoked_at: null,
      is_expired: false,
      is_active: true,
    }
    queueResponses([
      { ok: true, status: 200, body: { data: [], count: 0 } },
      {
        ok: true,
        status: 201,
        body: { ...listedKey, token: "cqa_newplaintext" },
      },
      {
        ok: true,
        status: 200,
        body: { data: [listedKey], count: 1 },
      },
    ])

    render(<ApiKeysPage />)
    await screen.findByText(/no api keys yet/i)
    fireEvent.change(screen.getByLabelText(/^name$/i), {
      target: { value: "laptop" },
    })
    const form = screen
      .getByRole("button", { name: /create key/i })
      .closest("form")
    if (!form) throw new Error("create key form not found")
    fireEvent.submit(form)

    await screen.findByRole("dialog")
    expect(screen.getByText("cqa_newplaintext")).toBeInTheDocument()

    // "Done" button is disabled until the user acknowledges.
    const doneButton = screen.getByRole("button", { name: /done/i })
    expect(doneButton).toBeDisabled()

    fireEvent.click(screen.getByRole("checkbox"))
    expect(doneButton).toBeEnabled()

    fireEvent.click(doneButton)
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    )
  })

  it("revokes a key after confirmation", async () => {
    const activeKey = {
      id: "id1",
      name: "laptop",
      labels: [],
      prefix: "cqa_abcd",
      ttl: "90d",
      expires_at: "2027-01-01T00:00:00+00:00",
      created_at: "2026-04-16T00:00:00+00:00",
      last_used_at: null,
      revoked_at: null,
      is_expired: false,
      is_active: true,
    }
    const revokedKey = {
      ...activeKey,
      revoked_at: "2026-04-17T00:00:00+00:00",
      is_active: false,
    }
    queueResponses([
      { ok: true, status: 200, body: { data: [activeKey], count: 1 } },
      { ok: true, status: 200, body: { message: "API key revoked." } },
      { ok: true, status: 200, body: { data: [revokedKey], count: 1 } },
    ])

    render(<ApiKeysPage />)

    // Expand the key card to reveal the Revoke action.
    const summaryButton = await screen.findByRole("button", { expanded: false })
    fireEvent.click(summaryButton)

    const revokeButton = await screen.findByRole("button", { name: "Revoke" })
    fireEvent.click(revokeButton)

    // Confirmation dialog appears; click its Revoke button to confirm.
    const dialog = await screen.findByRole("dialog")
    const confirmButton = Array.from(dialog.querySelectorAll("button")).find(
      (b) => b.textContent?.trim() === "Revoke",
    )
    expect(confirmButton).toBeDefined()
    if (!confirmButton) throw new Error("confirm button not found")
    fireEvent.click(confirmButton)

    await waitFor(() =>
      expect(
        screen.getByText("Revoked", { selector: "span" }),
      ).toBeInTheDocument(),
    )
    // After revoke, the "Revoke" action button in the card is gone.
    expect(screen.queryByRole("button", { name: "Revoke" })).toBeNull()
  })
})
