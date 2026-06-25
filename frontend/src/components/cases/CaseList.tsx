// src/components/cases/CaseList.tsx
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { getCases } from "../../api/client";
import { SeverityBadge, StatusBadge, BreachTypeBadge } from "./StatusBadge";
import type { Severity, Status, BreachType } from "../../types";
import { formatDistanceToNow } from "../utils/time";
import { ChevronRight, RefreshCw } from "lucide-react";

export default function CaseList() {
  const navigate = useNavigate();
  const [severityFilter, setSeverityFilter] = useState<Severity | "">("");
  const [statusFilter, setStatusFilter]     = useState<Status | "">("");
  const [breachFilter, setBreachFilter]     = useState<BreachType | "">("");

  const { data: cases, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["cases", severityFilter, statusFilter, breachFilter],
    queryFn: () => getCases({
      severity:    severityFilter    || undefined,
      status:      statusFilter      || undefined,
      breach_type: breachFilter      || undefined,
      limit: 100,
    }),
  });

  return (
    <div>
      {/* Filter bar */}
      <div className="flex items-center gap-3 mb-4">
        <select
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value as Severity | "")}
          className="bg-surface-800 border border-surface-600 text-slate-300
                     text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-blue-500"
        >
          <option value="">All severities</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as Status | "")}
          className="bg-surface-800 border border-surface-600 text-slate-300
                     text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-blue-500"
        >
          <option value="">All statuses</option>
          <option value="open">Open</option>
          <option value="investigating">Investigating</option>
          <option value="contained">Contained</option>
          <option value="resolved">Resolved</option>
          <option value="closed">Closed</option>
        </select>

        <select
          value={breachFilter}
          onChange={(e) => setBreachFilter(e.target.value as BreachType | "")}
          className="bg-surface-800 border border-surface-600 text-slate-300
                     text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-blue-500"
        >
          <option value="">All types</option>
          <option value="ransomware">Ransomware</option>
          <option value="phishing">Phishing</option>
          <option value="unauthorized_access">Unauthorized Access</option>
          <option value="exfiltration">Exfiltration</option>
          <option value="insider">Insider</option>
        </select>

        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="ml-auto flex items-center gap-2 text-xs text-slate-400
                     hover:text-slate-200 transition-colors"
        >
          <RefreshCw size={13} className={isFetching ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="text-center text-slate-500 py-16">Loading cases...</div>
      ) : !cases || cases.length === 0 ? (
        <div className="text-center text-slate-500 py-16">No cases found.</div>
      ) : (
        <div className="bg-surface-800 rounded-xl border border-surface-700 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-700 text-slate-400 text-xs uppercase tracking-wide">
                <th className="text-left px-4 py-3">Case ID</th>
                <th className="text-left px-4 py-3">Title</th>
                <th className="text-left px-4 py-3">Severity</th>
                <th className="text-left px-4 py-3">Status</th>
                <th className="text-left px-4 py-3">Type</th>
                <th className="text-left px-4 py-3">Host</th>
                <th className="text-left px-4 py-3">Confidence</th>
                <th className="text-left px-4 py-3">Detected</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-700">
              {cases.map((c) => (
                <tr
                  key={c.id}
                  onClick={() => navigate(`/cases/${c.id}`)}
                  className="hover:bg-surface-700 cursor-pointer transition-colors"
                >
                  <td className="px-4 py-3 font-mono text-xs text-slate-400">
                    {c.id}
                  </td>
                  <td className="px-4 py-3 text-slate-100 max-w-xs truncate">
                    {c.title}
                  </td>
                  <td className="px-4 py-3">
                    <SeverityBadge severity={c.severity} />
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={c.status} />
                  </td>
                  <td className="px-4 py-3">
                    <BreachTypeBadge type={c.breach_type} />
                  </td>
                  <td className="px-4 py-3 text-slate-400 font-mono text-xs">
                    {c.source_host ?? "—"}
                  </td>
                  <td className="px-4 py-3">
                    {c.ai_confidence != null ? (
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1.5 bg-surface-600 rounded-full">
                          <div
                            className="h-1.5 rounded-full bg-blue-500"
                            style={{ width: `${c.ai_confidence}%` }}
                          />
                        </div>
                        <span className="text-xs text-slate-400">
                          {c.ai_confidence.toFixed(0)}%
                        </span>
                      </div>
                    ) : (
                      <span className="text-xs text-slate-600">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-400 text-xs">
                    {formatDistanceToNow(c.detected_at)}
                  </td>
                  <td className="px-4 py-3">
                    <ChevronRight size={14} className="text-slate-600" />
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