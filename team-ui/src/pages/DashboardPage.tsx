import { useState, useEffect, useCallback } from "react";
import { Link, useOutletContext } from "react-router";
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { api } from "../api";
import { StatusBadge } from "../components/StatusBadge";
import { KnowledgeUnitModal } from "../components/KnowledgeUnitModal";
import { FilteredListModal, type ListFilter } from "../components/FilteredListModal";
import { timeAgo } from "../utils";
import type { ReviewStatsResponse } from "../types";


const CONFIDENCE_COLORS: Record<string, string> = {
  "0.0-0.3": "bg-red-200",
  "0.3-0.6": "bg-amber-200",
  "0.6-0.8": "bg-green-200",
  "0.8-1.0": "bg-green-400",
};

export function DashboardPage() {
  const { setPendingCount } = useOutletContext<{
    setPendingCount: (n: number) => void;
  }>();
  const [stats, setStats] = useState<ReviewStatsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedUnitId, setSelectedUnitId] = useState<string | null>(null);
  const [listFilter, setListFilter] = useState<ListFilter | null>(null);
  const closeModal = useCallback(() => setSelectedUnitId(null), []);
  const closeListModal = useCallback(() => setListFilter(null), []);

  useEffect(() => {
    function fetchStats() {
      api
        .reviewStats()
        .then((s) => {
          setStats(s);
          setPendingCount(s.counts.pending);
          setError(null);
        })
        .catch(() => setError("Failed to load dashboard. Retrying..."));
    }
    fetchStats();
    const interval = setInterval(fetchStats, 15_000);
    return () => clearInterval(interval);
  }, [setPendingCount]);

  const trendData = stats?.trends.daily ?? [];

  if (!stats && !error) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-white rounded-lg border border-gray-200 p-4">
              <div className="h-4 w-16 animate-pulse bg-gray-200 rounded mb-2" />
              <div className="h-8 w-12 animate-pulse bg-gray-200 rounded" />
            </div>
          ))}
        </div>
        {[1, 2].map((i) => (
          <div key={i} className="bg-white rounded-lg border border-gray-200 p-4 h-40 animate-pulse bg-gray-100" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-center">
          <p className="text-red-600 text-sm font-medium">{error}</p>
        </div>
      )}

      {stats && (
        <>
          <div className="grid grid-cols-3 gap-4">
            <Link
              to="/review"
              className="bg-white rounded-lg border border-gray-200 p-4 text-center hover:border-amber-300 transition-colors"
            >
              <p className="text-3xl font-bold text-amber-500">{stats.counts.pending}</p>
              <p className="text-xs text-gray-500 uppercase mt-1">Pending</p>
            </Link>
            <div className="bg-white rounded-lg border border-gray-200 p-4 text-center">
              <p className="text-3xl font-bold text-green-600">{stats.counts.approved}</p>
              <p className="text-xs text-gray-500 uppercase mt-1">Approved</p>
            </div>
            <button
              className="bg-white rounded-lg border border-gray-200 p-4 text-center hover:border-red-300 transition-colors w-full"
              onClick={() =>
                setListFilter({ title: "Rejected", status: "rejected" })
              }
            >
              <p className="text-3xl font-bold text-red-600">{stats.counts.rejected}</p>
              <p className="text-xs text-gray-500 uppercase mt-1">Rejected</p>
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-white rounded-lg border border-gray-200 p-4">
              <h3 className="text-xs font-semibold text-gray-500 uppercase mb-3">Domains</h3>
              <div className="space-y-3 max-h-48 overflow-y-auto">
                {Object.entries(stats.domains)
                  .sort(([, a], [, b]) => b - a)
                  .map(([domain, count]) => {
                    const maxCount = Math.max(...Object.values(stats.domains));
                    return (
                      <button
                        key={domain}
                        className="flex items-center gap-3 w-full text-left rounded hover:bg-indigo-50 transition-colors -mx-1 px-1"
                        onClick={() =>
                          setListFilter({ title: `Domain: ${domain}`, domain, status: "approved" })
                        }
                      >
                        <span className="text-sm text-gray-700 w-24 truncate">{domain}</span>
                        <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-indigo-500 rounded-full"
                            style={{ width: `${(count / maxCount) * 100}%` }}
                          />
                        </div>
                        <span className="text-xs text-gray-400 w-6 text-right">{count}</span>
                      </button>
                    );
                  })}
              </div>
            </div>

            <div className="bg-white rounded-lg border border-gray-200 p-4">
              <h3 className="text-xs font-semibold text-gray-500 uppercase mb-3">Confidence</h3>
              {(() => {
                const maxCount = Math.max(...Object.values(stats.confidence_distribution), 1);
                return (
                  <div className="flex gap-2">
                    {Object.entries(stats.confidence_distribution).map(([bucket, count]) => {
                      const [minStr, maxStr] = bucket.split("-");
                      const max = parseFloat(maxStr);
                      return (
                        <button
                          key={bucket}
                          className="flex-1 flex flex-col items-center gap-1 rounded hover:bg-gray-50 transition-colors cursor-pointer"
                          disabled={count === 0}
                          onClick={() =>
                            setListFilter({
                              title: `Confidence: ${bucket}`,
                              confidence_min: parseFloat(minStr),
                              confidence_max: max >= 1.0 ? undefined : max,
                              status: "approved",
                            })
                          }
                        >
                          <span className="text-xs text-gray-500 font-medium">{count}</span>
                          <div className="w-full h-24 flex items-end">
                            <div
                              className={`w-full rounded-t ${CONFIDENCE_COLORS[bucket] ?? "bg-gray-200"}`}
                              style={{
                                height: maxCount > 0 ? `${(count / maxCount) * 100}%` : "0",
                                minHeight: count > 0 ? "8px" : "0",
                              }}
                            />
                          </div>
                          <span className="text-[10px] text-gray-500 truncate w-full text-center">{bucket}</span>
                        </button>
                      );
                    })}
                  </div>
                );
              })()}
            </div>
          </div>

          <div className="bg-white rounded-lg border border-gray-200 p-4">
            <h3 className="text-xs font-semibold text-gray-500 uppercase mb-3">Submissions</h3>
            {trendData.length === 0 ? (
              <p className="text-gray-400 text-sm text-center py-8">No submission data yet</p>
            ) : (
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={trendData}>
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
                  <Tooltip />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Line
                    type="monotone"
                    dataKey="proposed"
                    stroke="#eab308"
                    strokeWidth={2}
                    dot={trendData.length <= 7}
                    name="Submitted"
                  />
                  <Line
                    type="monotone"
                    dataKey="approved"
                    stroke="#22c55e"
                    strokeWidth={2}
                    dot={trendData.length <= 7}
                    name="Approved"
                  />
                  <Line
                    type="monotone"
                    dataKey="rejected"
                    stroke="#ef4444"
                    strokeWidth={2}
                    dot={trendData.length <= 7}
                    name="Rejected"
                  />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>

          <div className="bg-white rounded-lg border border-gray-200 p-4">
            <h3 className="text-xs font-semibold text-gray-500 uppercase mb-3">Recent Activity</h3>
            <div className="max-h-60 overflow-y-auto">
              {stats.recent_activity.length === 0 ? (
                <p className="text-gray-400 text-sm">No activity yet</p>
              ) : (
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-gray-200">
                      <th className="py-1.5 pr-3 text-left text-[10px] font-semibold text-gray-400 uppercase w-20">Status</th>
                      <th className="py-1.5 pr-3 text-left text-[10px] font-semibold text-gray-400 uppercase">Summary</th>
                      <th className="py-1.5 pr-3 text-right text-[10px] font-semibold text-gray-400 uppercase w-20">Reviewer</th>
                      <th className="py-1.5 text-right text-[10px] font-semibold text-gray-400 uppercase w-16">Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.recent_activity.map((event) => (
                      <tr
                        key={event.unit_id}
                        className="border-b border-gray-50 last:border-0 cursor-pointer hover:bg-gray-50 transition-colors"
                        tabIndex={0}
                        role="button"
                        onClick={() => setSelectedUnitId(event.unit_id)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            setSelectedUnitId(event.unit_id);
                          }
                        }}
                      >
                        <td className="py-2 pr-3 w-20">
                          <StatusBadge status={event.type} />
                        </td>
                        <td className="py-2 pr-3 text-sm text-gray-700 truncate max-w-0">
                          {event.summary}
                        </td>
                        <td className="py-2 pr-3 text-xs text-gray-400 whitespace-nowrap w-20 text-right">
                          {event.reviewed_by ?? ""}
                        </td>
                        <td className="py-2 text-xs text-gray-400 whitespace-nowrap w-16 text-right">
                          {event.timestamp ? timeAgo(event.timestamp) : ""}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </>
      )}

      {listFilter && (
        <FilteredListModal
          key={listFilter.title}
          filter={listFilter}
          onClose={closeListModal}
          onSelectUnit={(id) => {
            setListFilter(null);
            setSelectedUnitId(id);
          }}
        />
      )}

      {selectedUnitId && (
        <KnowledgeUnitModal key={selectedUnitId} unitId={selectedUnitId} onClose={closeModal} />
      )}
    </div>
  );
}
