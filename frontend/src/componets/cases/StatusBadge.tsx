// src/components/cases/StatusBadge.tsx
import { clsx } from "clsx";
import type { Severity, Status, BreachType } from "../../types";

// ─── Severity badge ───────────────────────────────────────────────────────────

const severityStyles: Record<string, string> = {
  critical: "bg-red-500/20 text-red-400 border border-red-500/30",
  high:     "bg-orange-500/20 text-orange-400 border border-orange-500/30",
  medium:   "bg-yellow-500/20 text-yellow-400 border border-yellow-500/30",
  low:      "bg-green-500/20 text-green-400 border border-green-500/30",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className={clsx("px-2 py-0.5 rounded text-xs font-medium uppercase tracking-wide",
      severityStyles[severity])}>
      {severity}
    </span>
  );
}

// ─── Status badge ─────────────────────────────────────────────────────────────

const statusStyles: Record<string, string> = {
  open:          "bg-blue-500/20 text-blue-400 border border-blue-500/30",
  investigating: "bg-purple-500/20 text-purple-400 border border-purple-500/30",
  contained:     "bg-yellow-500/20 text-yellow-400 border border-yellow-500/30",
  resolved:      "bg-green-500/20 text-green-400 border border-green-500/30",
  closed:        "bg-slate-500/20 text-slate-400 border border-slate-500/30",
};

export function StatusBadge({ status }: { status: Status }) {
  return (
    <span className={clsx("px-2 py-0.5 rounded text-xs font-medium capitalize",
      statusStyles[status])}>
      {status}
    </span>
  );
}

// ─── Breach type badge ────────────────────────────────────────────────────────

const breachLabels: Record<BreachType, string> = {
  ransomware:          "Ransomware",
  phishing:            "Phishing",
  unauthorized_access: "Unauth. Access",
  exfiltration:        "Exfiltration",
  insider:             "Insider",
};

export function BreachTypeBadge({ type }: { type: BreachType }) {
  return (
    <span className="px-2 py-0.5 rounded text-xs font-medium
                     bg-slate-700 text-slate-300 border border-slate-600">
      {breachLabels[type]}
    </span>
  );
}