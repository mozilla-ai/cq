import type {
  ReviewItem,
  ReviewQueueResponse,
  ReviewDecisionResponse,
  ReviewStatsResponse,
} from "./types";

const API_BASE = "/api";
const TOKEN_KEY = "cq_auth_token";

let token: string | null = null;

export function setToken(t: string | null) {
  token = t;
  if (t) {
    localStorage.setItem(TOKEN_KEY, t);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

export function getToken(): string | null {
  if (!token) {
    token = localStorage.getItem(TOKEN_KEY);
  }
  return token;
}

class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

let onUnauthorized: (() => void) | null = null;

export function setOnUnauthorized(callback: () => void) {
  onUnauthorized = callback;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  const currentToken = getToken();
  if (currentToken) {
    headers["Authorization"] = `Bearer ${currentToken}`;
  }
  const resp = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!resp.ok) {
    if (resp.status === 401 && onUnauthorized) {
      onUnauthorized();
    }
    const body = await resp.json().catch(() => ({}));
    throw new ApiError(resp.status, body.detail || `HTTP ${resp.status}`);
  }
  return resp.json();
}

export const api = {
  login: (username: string, password: string) =>
    request<{ token: string; username: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),

  me: () => request<{ username: string; created_at: string }>("/auth/me"),

  reviewQueue: (limit = 20, offset = 0) =>
    request<ReviewQueueResponse>(
      `/review/queue?limit=${limit}&offset=${offset}`,
    ),

  approve: (unitId: string) =>
    request<ReviewDecisionResponse>(`/review/${unitId}/approve`, {
      method: "POST",
    }),

  reject: (unitId: string) =>
    request<ReviewDecisionResponse>(`/review/${unitId}/reject`, {
      method: "POST",
    }),

  reviewStats: () => request<ReviewStatsResponse>("/review/stats"),

  getUnit: (unitId: string) => request<ReviewItem>(`/review/${unitId}`),

  listUnits: (params: {
    domain?: string;
    confidence_min?: number;
    confidence_max?: number;
    status?: string;
  }) => {
    const qs = new URLSearchParams();
    if (params.domain) qs.set("domain", params.domain);
    if (params.confidence_min != null)
      qs.set("confidence_min", String(params.confidence_min));
    if (params.confidence_max != null)
      qs.set("confidence_max", String(params.confidence_max));
    if (params.status) qs.set("status", params.status);
    const query = qs.toString();
    return request<ReviewItem[]>(`/review/units${query ? `?${query}` : ""}`);
  },
};

export { ApiError };
