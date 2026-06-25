// src/pages/Alerts.tsx
import { useQuery } from "@tanstack/react-query";
import { getAlerts } from "../api/client";
import { formatDistanceToNow } from "../components/utils/time";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { clsx } from "clsx";

const levelColor = (level: number) => {
  if (level >= 15) return "text-red-400";
  if (level >= 12) return "text-orange-400";
  if (level >= 8)  return "text-yellow-400";
  return "text-green-400";
};

export default function Alerts() {
  const { data: alerts, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["alerts"],
    queryFn:  () => getAlerts({ limit: 100 }),
    refetchInterval: 15_000,
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold text-white">Alert Feed</h2>
          <p className="text-sm text-slate-400 mt-1">
            Raw Wazuh alerts ingested into ZeroRespond.
          </p>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-2 text-xs text-slate-400
                     hover:text-slate-200 transition-colors"
        >
          <RefreshCw size={13} className={isFetching ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {isLoading ? (
        <div className="text-center text-slate-500 py-16">Loading alerts...</div>
      ) : !alerts || alerts.length === 0 ? (
        <div className="text-center text-slate-500 py-16">No alerts ingested yet.</div>
      ) : (
        <div className="bg-surface-800 rounded-xl border border-surface-700 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-700 text-slate-400 text-xs uppercase tracking-wide">
                <th className="text-left px-4 py-3">Level</th>
                <th className="text-left px-4 py-3">Alert ID</th>
                <th className="text-left px-4 py-3">Description</th>
                <th className="text-left px-4 py-3">Host</th>
                <th className="text-left px-4 py-3">Source IP</th>
                <th className="text-left px-4 py-3">Attack Type</th>
                <th className="text-left px-4 py-3">Received</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-700">
              {alerts.map((a) => (
                <tr key={a.id} className="hover:bg-surface-700 transition-colors">
                  <td className="px-4 py-3">
                    <span className={clsx("font-mono text-xs font-bold", levelColor(a.level))}>
                      L{a.level}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-400">
                    {a.id.slice(0, 20)}...
                  </td>
                  <td className="px-4 py-3 text-slate-200 max-w-xs truncate">
                    {a.description}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-400">
                    {a.host}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-400">
                    {a.source_ip ?? "—"}
                  </td>
                  <td className="px-4 py-3">
                    {a.attack_type ? (
                      <span className="text-xs text-blue-400 font-medium">
                        {a.attack_type.replace("_", " ")}
                      </span>
                    ) : (
                      <span className="text-xs text-slate-600 italic">pending AI</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-400">
                    {formatDistanceToNow(a.received_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}