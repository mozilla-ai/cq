import { useState, useEffect, useMemo } from "react";
import { Link, useOutletContext } from "react-router";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { api } from "../api";
import { StatusBadge } from "../components/StatusBadge";
import { timeAgo } from "../utils";
import type { ReviewStatsResponse, DailyCount } from "../types";

function useCumulativeTotals(daily: DailyCount[]) {
  return useMemo(() => {
    const data = daily.reduce<Array<DailyCount & { total: number }>>((acc, d) => {
      const total = (acc.length > 0 ? acc[acc.length - 1].total : 0) + d.proposed;
      acc.push({ ...d, total });
      return acc;
    }, []);
    // Prepend an origin point so a single day draws a line from zero.
    if (data.length > 0) {
      data.unshift({ date: "", proposed: 0, total: 0 });
    }
    return data;
  }, [daily]);
}

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

  const trendData = useCumulativeTotals(stats?.trends.daily ?? []);

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
            <div className="bg-white rounded-lg border border-gray-200 p-4 text-center">
              <p className="text-3xl font-bold text-red-600">{stats.counts.rejected}</p>
              <p className="text-xs text-gray-500 uppercase mt-1">Rejected</p>
            </div>
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
                      <div key={domain} className="flex items-center gap-3">
                        <span className="text-sm text-gray-700 w-24 truncate">{domain}</span>
                        <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-indigo-500 rounded-full"
                            style={{ width: `${(count / maxCount) * 100}%` }}
                          />
                        </div>
                        <span className="text-xs text-gray-400 w-6 text-right">{count}</span>
                      </div>
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
                    {Object.entries(stats.confidence_distribution).map(([bucket, count]) => (
                      <div key={bucket} className="flex-1 flex flex-col items-center gap-1">
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
                      </div>
                    ))}
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
                  <Line
                    type="monotone"
                    dataKey="proposed"
                    stroke="#6366f1"
                    strokeWidth={2}
                    dot={trendData.length <= 7}
                    name="Daily proposals"
                  />
                  <Line
                    type="monotone"
                    dataKey="total"
                    stroke="#9ca3af"
                    strokeWidth={1.5}
                    strokeDasharray="5 5"
                    dot={trendData.length <= 7}
                    name="Cumulative total"
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
                    {stats.recent_activity.map((event, i) => (
                      <tr key={i} className="border-b border-gray-50 last:border-0">
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
    </div>
  );
}
