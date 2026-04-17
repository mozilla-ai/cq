import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { ApiKeyPublic, CreatedApiKey } from "../types";
import { secondsUntil, timeAgo, timeUntil } from "../utils";

const TTL_PATTERN = /^\d+[smhd]$/;
const TTL_SUGGESTIONS = ["30d", "90d", "365d", "1h", "15m"];

const DAY_SECONDS = 24 * 60 * 60;
const WEEK_SECONDS = 7 * DAY_SECONDS;
const MAX_ACTIVE_KEYS = 20;

type KeyFilter = "all" | "active" | "revoked";

function formatDate(iso: string | null): string {
  if (!iso) return "never";
  return new Date(iso).toLocaleString();
}

function statusLabel(key: ApiKeyPublic): string {
  if (key.revoked_at) return "Revoked";
  if (key.is_expired) return "Expired";
  return "Active";
}

function statusBadgeClasses(key: ApiKeyPublic): string {
  if (key.revoked_at) return "bg-red-100 text-red-700";
  if (key.is_expired) return "bg-gray-200 text-gray-600";
  return "bg-green-100 text-green-700";
}

function expiryUrgencyClasses(key: ApiKeyPublic): string {
  if (key.revoked_at || key.is_expired) return "bg-gray-100 text-gray-500";
  const remaining = secondsUntil(key.expires_at);
  if (remaining <= DAY_SECONDS) return "bg-red-100 text-red-700";
  if (remaining <= WEEK_SECONDS) return "bg-amber-100 text-amber-700";
  return "bg-green-100 text-green-700";
}

function expiryLabel(key: ApiKeyPublic): string {
  if (key.revoked_at) return "revoked";
  if (key.is_expired) return "expired";
  return `${timeUntil(key.expires_at)} left`;
}

function expiryTooltip(key: ApiKeyPublic): string {
  if (key.revoked_at) return `Revoked ${formatDate(key.revoked_at)}`;
  if (key.is_expired) return `Expired ${formatDate(key.expires_at)}`;
  return `Expires ${formatDate(key.expires_at)}`;
}

function parseLabelsInput(raw: string): string[] {
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

function matchesFilter(key: ApiKeyPublic, filter: KeyFilter): boolean {
  if (filter === "all") return true;
  if (filter === "revoked") return key.revoked_at !== null;
  return key.is_active;
}

function matchesSearch(key: ApiKeyPublic, query: string): boolean {
  if (query === "") return true;
  const needle = query.toLowerCase();
  return (
    key.name.toLowerCase().includes(needle) ||
    key.labels.some((label) => label.toLowerCase().includes(needle))
  );
}

interface RevokePrompt {
  id: string;
  name: string;
}

export function ApiKeysPage() {
  const [keys, setKeys] = useState<ApiKeyPublic[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [ttl, setTtl] = useState("90d");
  const [labelsInput, setLabelsInput] = useState("");
  const [creating, setCreating] = useState(false);
  const [createdKey, setCreatedKey] = useState<CreatedApiKey | null>(null);
  const [copied, setCopied] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const [revokePrompt, setRevokePrompt] = useState<RevokePrompt | null>(null);
  const [revoking, setRevoking] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState<KeyFilter>("all");
  const [search, setSearch] = useState("");

  const activeCount = useMemo(() => keys.filter((k) => k.is_active).length, [keys]);
  const revokedCount = useMemo(
    () => keys.filter((k) => k.revoked_at !== null).length,
    [keys],
  );
  const filteredKeys = useMemo(
    () => keys.filter((k) => matchesFilter(k, filter) && matchesSearch(k, search)),
    [keys, filter, search],
  );
  const atCap = activeCount >= MAX_ACTIVE_KEYS;

  function toggleExpanded(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  const ttlIsValid = TTL_PATTERN.test(ttl);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listApiKeys();
      setKeys(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load API keys");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function handleCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!ttlIsValid) {
      setError(`TTL must match ${TTL_PATTERN.source} (for example 90d)`);
      return;
    }
    setCreating(true);
    setError(null);
    try {
      const created = await api.createApiKey(name.trim(), ttl, parseLabelsInput(labelsInput));
      setCreatedKey(created);
      setCopied(false);
      setAcknowledged(false);
      setName("");
      setTtl("90d");
      setLabelsInput("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create key");
    } finally {
      setCreating(false);
    }
  }

  async function confirmRevoke() {
    if (!revokePrompt) return;
    setRevoking(true);
    try {
      await api.revokeApiKey(revokePrompt.id);
      setRevokePrompt(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to revoke key");
    } finally {
      setRevoking(false);
    }
  }

  async function copyToken() {
    if (!createdKey) return;
    await navigator.clipboard.writeText(createdKey.token);
    setCopied(true);
  }

  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-2xl font-semibold text-gray-900">API Keys</h1>
        <p className="mt-2 text-sm text-gray-600">
          API keys let agents act on your behalf. Give each key a name and an expiry; attach optional
          labels to group or filter keys later. The full key is shown only once at creation.
        </p>
      </section>

      <section className="rounded-lg border border-gray-200 bg-white p-6">
        <h2 className="text-lg font-medium text-gray-900">Create a new key</h2>
        <form onSubmit={handleCreate} className="mt-4 grid gap-4 md:grid-cols-2">
          <label className="flex flex-col text-sm">
            <span className="text-gray-700">Name</span>
            <input
              type="text"
              required
              maxLength={64}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. laptop-mcp"
              className="mt-1 rounded-md border border-gray-300 px-3 py-2 focus:border-indigo-500 focus:outline-none"
            />
          </label>
          <label className="flex flex-col text-sm">
            <span className="text-gray-700">TTL</span>
            <input
              type="text"
              required
              list="ttl-suggestions"
              value={ttl}
              onChange={(e) => setTtl(e.target.value)}
              maxLength={16}
              aria-invalid={ttl.length > 0 && !ttlIsValid}
              className="mt-1 rounded-md border border-gray-300 px-3 py-2 focus:border-indigo-500 focus:outline-none"
            />
            <datalist id="ttl-suggestions">
              {TTL_SUGGESTIONS.map((s) => (
                <option key={s} value={s} />
              ))}
            </datalist>
            <span className="mt-1 text-xs text-gray-500">
              e.g. <code>30s</code>, <code>15m</code>, <code>2h</code>, <code>90d</code> (max 365d).
            </span>
          </label>
          <label className="flex flex-col text-sm md:col-span-2">
            <span className="text-gray-700">Labels (optional)</span>
            <input
              type="text"
              value={labelsInput}
              onChange={(e) => setLabelsInput(e.target.value)}
              placeholder="comma-separated, e.g. mcp, claude, personal"
              className="mt-1 rounded-md border border-gray-300 px-3 py-2 focus:border-indigo-500 focus:outline-none"
            />
          </label>
          <div className="md:col-span-2">
            <button
              type="submit"
              disabled={creating || name.trim() === "" || !ttlIsValid || atCap}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {creating ? "Creating…" : "Create key"}
            </button>
            {atCap && (
              <p className="mt-2 text-xs text-amber-700 md:col-span-2">
                You have the maximum of {MAX_ACTIVE_KEYS} active keys. Revoke one to create another.
              </p>
            )}
          </div>
        </form>
        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      </section>

      <section>
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="shrink-0 text-lg font-medium text-gray-900">
            Your keys
            <span className="ml-2 text-sm font-normal text-gray-500">
              {activeCount} of {MAX_ACTIVE_KEYS} active
            </span>
          </h2>
          <div
            role="group"
            aria-label="Filter keys"
            className="inline-flex shrink-0 overflow-hidden rounded-lg border border-gray-200 bg-white text-sm"
          >
            {(
              [
                ["all", `All (${keys.length})`],
                ["active", `Active (${activeCount})`],
                ["revoked", `Revoked (${revokedCount})`],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => setFilter(value)}
                aria-pressed={filter === value}
                className={`px-3 py-1.5 ${
                  filter === value
                    ? "bg-indigo-600 text-white"
                    : "text-gray-700 hover:bg-gray-50"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name or label…"
            aria-label="Search keys"
            className="min-w-40 flex-1 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
          />
        </div>
        {loading ? (
          <p className="mt-4 text-sm text-gray-500">Loading…</p>
        ) : keys.length === 0 ? (
          <p className="mt-4 text-sm text-gray-500">No API keys yet.</p>
        ) : filteredKeys.length === 0 ? (
          <p className="mt-4 text-sm text-gray-500">No keys match the current filter.</p>
        ) : (
          <ul className="mt-4 space-y-3">
            {filteredKeys.map((key) => {
              const isOpen = expanded.has(key.id);
              return (
                <li
                  key={key.id}
                  className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm"
                >
                  <button
                    type="button"
                    onClick={() => toggleExpanded(key.id)}
                    aria-expanded={isOpen}
                    aria-controls={`apikey-details-${key.id}`}
                    className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left hover:bg-gray-50"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <h3 className="truncate text-base font-semibold text-gray-900">
                          {key.name}
                        </h3>
                        <code className="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-xs text-gray-600">
                          {key.prefix}…
                        </code>
                      </div>
                      <div className="mt-1.5">
                        <span className="group relative inline-block">
                          <span
                            className={`inline-flex cursor-help items-center rounded-full px-2 py-0.5 text-xs font-medium ${expiryUrgencyClasses(
                              key,
                            )}`}
                          >
                            {expiryLabel(key)}
                          </span>
                          <span
                            role="tooltip"
                            className="pointer-events-none invisible absolute bottom-full left-1/2 z-20 mb-1 -translate-x-1/2 whitespace-nowrap rounded bg-gray-900 px-2 py-1 text-xs text-white opacity-0 transition-opacity group-hover:visible group-hover:opacity-100"
                          >
                            {expiryTooltip(key)}
                          </span>
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusBadgeClasses(
                          key,
                        )}`}
                      >
                        {statusLabel(key)}
                      </span>
                      <svg
                        aria-hidden="true"
                        className={`h-4 w-4 text-gray-400 transition-transform ${isOpen ? "rotate-180" : ""}`}
                        viewBox="0 0 20 20"
                        fill="currentColor"
                      >
                        <path
                          fillRule="evenodd"
                          d="M5.23 7.21a.75.75 0 011.06.02L10 11.06l3.71-3.83a.75.75 0 111.08 1.04l-4.25 4.39a.75.75 0 01-1.08 0L5.21 8.27a.75.75 0 01.02-1.06z"
                          clipRule="evenodd"
                        />
                      </svg>
                    </div>
                  </button>

                  {isOpen && (
                    <div
                      id={`apikey-details-${key.id}`}
                      className="border-t border-gray-200 bg-gray-50/60 px-5 py-4"
                    >
                      {key.labels.length > 0 && (
                        <div className="mb-4">
                          <div className="text-xs uppercase tracking-wide text-gray-400">Labels</div>
                          <div className="mt-1 flex flex-wrap gap-1">
                            {key.labels.map((label) => (
                              <span
                                key={label}
                                className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs text-indigo-700"
                              >
                                {label}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-3">
                        <div>
                          <dt className="text-xs uppercase tracking-wide text-gray-400">TTL</dt>
                          <dd className="mt-0.5 font-mono text-gray-800">{key.ttl}</dd>
                        </div>
                        <div>
                          <dt className="text-xs uppercase tracking-wide text-gray-400">Created</dt>
                          <dd className="mt-0.5 text-gray-700">{timeAgo(key.created_at)}</dd>
                        </div>
                        <div>
                          <dt className="text-xs uppercase tracking-wide text-gray-400">Last used</dt>
                          <dd className="mt-0.5 text-gray-700">
                            {key.last_used_at ? timeAgo(key.last_used_at) : "never"}
                          </dd>
                        </div>
                      </dl>
                      {key.is_active && (
                        <div className="mt-4 flex justify-end">
                          <button
                            onClick={() => setRevokePrompt({ id: key.id, name: key.name })}
                            className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 bg-white px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50"
                          >
                            <svg
                              aria-hidden="true"
                              className="h-4 w-4"
                              viewBox="0 0 20 20"
                              fill="currentColor"
                            >
                              <path
                                fillRule="evenodd"
                                d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm4 0a1 1 0 012 0v6a1 1 0 11-2 0V8z"
                                clipRule="evenodd"
                              />
                            </svg>
                            Revoke
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {createdKey && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="created-key-heading"
          className="fixed inset-0 z-10 flex items-center justify-center bg-black/40 p-4"
        >
          <div className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl">
            <h3 id="created-key-heading" className="text-lg font-semibold text-gray-900">
              Your new API key
            </h3>
            <p className="mt-2 text-sm text-gray-600">
              Copy this token now. It will not be shown again.
            </p>
            <div className="mt-4 flex items-center gap-2 rounded-md bg-gray-100 p-3">
              <code className="flex-1 break-all text-sm">{createdKey.token}</code>
              <button
                onClick={copyToken}
                className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-indigo-700"
              >
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
            <label className="mt-4 flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={acknowledged}
                onChange={(e) => setAcknowledged(e.target.checked)}
              />
              I have copied this token and saved it securely.
            </label>
            <div className="mt-4 flex justify-end">
              <button
                onClick={() => setCreatedKey(null)}
                disabled={!acknowledged}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {revokePrompt && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="revoke-key-heading"
          className="fixed inset-0 z-10 flex items-center justify-center bg-black/40 p-4"
        >
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
            <h3 id="revoke-key-heading" className="text-lg font-semibold text-gray-900">
              Revoke &ldquo;{revokePrompt.name}&rdquo;?
            </h3>
            <p className="mt-2 text-sm text-gray-600">
              Clients using this key will start receiving 401 responses immediately. This cannot be undone.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <button
                onClick={() => setRevokePrompt(null)}
                disabled={revoking}
                className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={confirmRevoke}
                disabled={revoking}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
              >
                {revoking ? "Revoking…" : "Revoke"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
