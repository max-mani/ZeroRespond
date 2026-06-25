// src/pages/Dashboard.tsx
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { getCases } from "../api/client";
import { SeverityBadge, StatusBadge } from "../components/cases/StatusBadge";
import { formatDistanceToNow } from "../components/utils/time";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";
import { AlertTriangle, FolderOpen, Shield, Activity } from "lucide-react";
import ErrorMessage from "../components/ui/ErrorMessage";
import { usePageTitle } from "../hooks/usePageTitle";

const BREACH_COLORS: Record<string, string> = {
  ransomware:          "#ef4444",
  phishing:            "#f97316",
  unauthorized_access: "#3b82f6",
  exfiltration:        "#a855f7",
  insider:             "#eab308",
};

export default function Dashboard() {
  const navigate = useNavigate();
  usePageTitle("Dashboard");
  const { data: cases, isLoading } = useQuery({
    queryKey: ["cases"],
    queryFn: () => getCases({ limit: 100 }),
    refetchInterval: 30_000,
  });

  if (isLoading) {
    return <div className="text-center text-slate-500 py-16">Loading...</div>;
  }

  const allCases = cases ?? [];

  // Compute stats
  const total    = allCases.length;
  const open     = allCases.filter((c) => c.status === "open").length;
  const critical = allCases.filter((c) => c.severity === "critical").length;
  const high     = allCases.filter((c) => c.severity === "high").length;

  // Breach type distribution for chart
  const breachCounts = allCases.reduce<Record<string, number>>((acc, c) => {
    acc[c.breach_type] = (acc[c.breach_type] ?? 0) + 1;
    return acc;
  }, {});
  const chartData = Object.entries(breachCounts).map(([name, value]) => ({ name, value }));

  // 5 most recent cases
  const recent = [...allCases]
    .sort((a, b) => new Date(b.detected_at).getTime() - new Date(a.detected_at).getTime())
    .slice(0, 5);

  return (
    <div className="space-y-6">

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard icon={FolderOpen}    label="Total Cases"      value={total}    color="blue"   />
        <StatCard icon={Activity}      label="Open"             value={open}     color="blue"   />
        <StatCard icon={AlertTriangle} label="Critical"         value={critical} color="red"    />
        <StatCard icon={Shield}        label="High Severity"    value={high}     color="orange" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">

        {/* Breach type chart */}
        <div className="bg-surface-800 rounded-xl border border-surface-700 p-6">
          <h3 className="text-sm font-semibold text-white mb-4">Breach Type Distribution</h3>
          {chartData.length === 0 ? (
            <p className="text-slate-500 text-sm text-center py-8">No data yet</p>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie
                  data={chartData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                  label={({ name, percent }) =>
                    `${name.replace("_", " ")} ${(percent * 100).toFixed(0)}%`
                  }
                  labelLine={false}
                >
                  {chartData.map((entry) => (
                    <Cell
                      key={entry.name}
                      fill={BREACH_COLORS[entry.name] ?? "#64748b"}
                    />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#1e293b",
                    border: "1px solid #334155",
                    borderRadius: "8px",
                    color: "#f1f5f9",
                    fontSize: "12px",
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Recent cases */}
        <div className="bg-surface-800 rounded-xl border border-surface-700 p-6">
          <h3 className="text-sm font-semibold text-white mb-4">Recent Cases</h3>
          {recent.length === 0 ? (
            <p className="text-slate-500 text-sm">No cases yet.</p>
          ) : (
            <div className="space-y-3">
              {recent.map((c) => (
                <div
                  key={c.id}
                  onClick={() => navigate(`/cases/${c.id}`)}
                  className="flex items-center justify-between gap-3 p-3
                             bg-surface-700 rounded-lg cursor-pointer
                             hover:bg-surface-600 transition-colors"
                >
                  <div className="min-w-0">
                    <p className="text-sm text-slate-200 truncate">{c.title}</p>
                    <p className="text-xs text-slate-500 font-mono mt-0.5">{c.id}</p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <SeverityBadge severity={c.severity} />
                    <StatusBadge status={c.status} />
                    <span className="text-xs text-slate-500">
                      {formatDistanceToNow(c.detected_at)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Stat card helper ────────────────────────────────────────────────────────

function StatCard({
  icon: Icon,
  label,
  value,
  color,
}: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  label: string;
  value: number;
  color: "blue" | "red" | "orange" | "green";
}) {
  const colorClass = {
    blue:   "text-blue-400",
    red:    "text-red-400",
    orange: "text-orange-400",
    green:  "text-green-400",
  }[color];

  return (
    <div className="bg-surface-800 rounded-xl border border-surface-700 p-5">
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs text-slate-400">{label}</p>
        <Icon size={16} className={colorClass} />
      </div>
      <p className={`text-2xl font-bold ${colorClass}`}>{value}</p>
    </div>
  );
}