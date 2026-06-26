// src/components/cases/CaseDetail.tsx
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateCase, reEnrichCase } from "../../api/client";
import { SeverityBadge, StatusBadge, BreachTypeBadge } from "./StatusBadge";
import { formatDatetime } from "../utils/time";
import type { CaseDetail as CaseDetailType, Status } from "../../types";
import { generateReport } from "../../api/client";
import { FileText } from "lucide-react";
import {
  Brain, Shield, AlertTriangle, Clock,
  User, Database, RefreshCw, ChevronDown
} from "lucide-react";

interface Props {
  caseData: CaseDetailType;
}

export default function CaseDetail({ caseData: c }: Props) {
  const queryClient = useQueryClient();
  const [reportLoading, setReportLoading] = useState(false);

  const handleDownloadReport = async () => {
    setReportLoading(true);
    try {
      const blob = await generateReport(c.id);
      // Create a download link and trigger it
      const url = URL.createObjectURL(blob);
      const a   = document.createElement("a");
      a.href     = url;
      a.download = `DPDP_Report_${c.id}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      alert("Failed to generate report. Please try again.");
    } finally {
      setReportLoading(false);
    }
  };
  
  const [notesValue, setNotesValue]   = useState(c.notes ?? "");
  const [statusValue, setStatusValue] = useState<Status>(c.status);
  const [assignedTo, setAssignedTo]   = useState(c.assigned_to ?? "");

  const updateMutation = useMutation({
    mutationFn: (payload: Parameters<typeof updateCase>[1]) =>
      updateCase(c.id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["case", c.id] });
      queryClient.invalidateQueries({ queryKey: ["cases"] });
    },
  });

  const enrichMutation = useMutation({
    mutationFn: () => reEnrichCase(c.id),
    onSuccess: () => {
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ["case", c.id] });
      }, 5000); // wait 5s for enrichment to run
    },
  });

  const handleSave = () => {
    updateMutation.mutate({
      status: statusValue,
      notes: notesValue || undefined,
      assigned_to: assignedTo || undefined,
    });
  };

  return (
    <div className="space-y-6">

      {/* Header */}
      <div className="bg-surface-800 rounded-xl border border-surface-700 p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-mono text-slate-500 mb-1">{c.id}</p>
            <h2 className="text-xl font-semibold text-white">{c.title}</h2>
            <div className="flex items-center gap-2 mt-3">
              <SeverityBadge severity={c.severity} />
              <StatusBadge status={c.status} />
              <BreachTypeBadge type={c.breach_type} />
            </div>
          </div>
          <button
            onClick={() => enrichMutation.mutate()}
            disabled={enrichMutation.isPending}
            className="flex items-center gap-2 px-3 py-1.5 text-xs
                       bg-blue-600 hover:bg-blue-700 text-white rounded-lg
                       transition-colors disabled:opacity-50"
          >
            <RefreshCw size={12} className={enrichMutation.isPending ? "animate-spin" : ""} />
            Re-run AI
          </button>

          <button
    onClick={handleDownloadReport}
    disabled={reportLoading}
    className="flex items-center gap-2 px-3 py-1.5 text-xs
               bg-purple-600 hover:bg-purple-700 text-white rounded-lg
               transition-colors disabled:opacity-50"
  >
    <FileText size={12} />
    {reportLoading ? "Generating..." : "DPDP Report"}
  </button>
        </div>

        {/* Key metadata */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-5">
          <MetaItem icon={Clock} label="Detected" value={formatDatetime(c.detected_at)} />
          <MetaItem icon={Shield} label="Source Host" value={c.source_host ?? "Unknown"} />
          <MetaItem icon={AlertTriangle} label="Source IP" value={c.source_ip ?? "Unknown"} />
          <MetaItem icon={User} label="Assigned To" value={c.assigned_to ?? "Unassigned"} />
        </div>
      </div>

      {/* AI Analysis panel */}
      <div className="bg-surface-800 rounded-xl border border-surface-700 p-6">
        <div className="flex items-center gap-2 mb-4">
          <Brain size={16} className="text-blue-400" />
          <h3 className="text-sm font-semibold text-white">AI Analysis</h3>
          {c.ai_confidence != null && (
            <span className="ml-auto text-xs text-slate-400">
              Confidence: <span className="text-blue-400 font-medium">{c.ai_confidence.toFixed(1)}%</span>
            </span>
          )}
        </div>

        {c.ai_summary ? (
          <div className="space-y-4">
            <div>
              <p className="text-xs text-slate-500 mb-1">Summary</p>
              <p className="text-sm text-slate-200 leading-relaxed">{c.ai_summary}</p>
            </div>

            {c.immediate_action && (
              <div className="bg-orange-500/10 border border-orange-500/20 rounded-lg p-4">
                <p className="text-xs font-semibold text-orange-400 mb-1">
                  ⚡ Immediate Action Required
                </p>
                <p className="text-sm text-orange-200">{c.immediate_action}</p>
              </div>
            )}

            {c.ai_mitre && (
              <div>
                <p className="text-xs text-slate-500 mb-1">MITRE ATT&CK</p>
                <a
                  href={`https://attack.mitre.org/techniques/${c.ai_mitre.replace(".", "/")}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs font-mono
                             text-blue-400 hover:text-blue-300 underline"
                >
                  {c.ai_mitre}
                </a>
              </div>
            )}
          </div>
        ) : (
          <div className="text-center py-6 text-slate-500 text-sm">
            AI analysis pending — enrichment may still be running.
            <br />
            <button
              onClick={() => enrichMutation.mutate()}
              className="mt-2 text-blue-400 hover:text-blue-300 text-xs underline"
            >
              Trigger manually
            </button>
          </div>
        )}
      </div>

      {/* DPDP Section (only if data exists) */}
      {(c.data_categories || c.persons_affected) && (
        <div className="bg-surface-800 rounded-xl border border-surface-700 p-6">
          <div className="flex items-center gap-2 mb-4">
            <Database size={16} className="text-purple-400" />
            <h3 className="text-sm font-semibold text-white">DPDP Act 2023 — Breach Details</h3>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <MetaItem label="Data Categories" value={c.data_categories ?? "Not specified"} />
            <MetaItem
              label="Persons Affected"
              value={c.persons_affected != null ? c.persons_affected.toLocaleString() : "Unknown"}
            />
          </div>
        </div>
      )}

      {/* Responder Actions */}
      <div className="bg-surface-800 rounded-xl border border-surface-700 p-6">
        <h3 className="text-sm font-semibold text-white mb-4">Responder Actions</h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div>
            <label className="text-xs text-slate-400 mb-1 block">Update Status</label>
            <div className="relative">
              <select
                value={statusValue}
                onChange={(e) => setStatusValue(e.target.value as Status)}
                className="w-full bg-surface-700 border border-surface-600 text-slate-200
                           text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500
                           appearance-none pr-8"
              >
                <option value="open">Open</option>
                <option value="investigating">Investigating</option>
                <option value="contained">Contained</option>
                <option value="resolved">Resolved</option>
                <option value="closed">Closed</option>
              </select>
              <ChevronDown size={14} className="absolute right-2 top-2.5 text-slate-400 pointer-events-none" />
            </div>
          </div>

          <div>
            <label className="text-xs text-slate-400 mb-1 block">Assign To</label>
            <input
              type="text"
              value={assignedTo}
              onChange={(e) => setAssignedTo(e.target.value)}
              placeholder="responder@org.in"
              className="w-full bg-surface-700 border border-surface-600 text-slate-200
                         text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
            />
          </div>
        </div>

        <div className="mb-4">
          <label className="text-xs text-slate-400 mb-1 block">Responder Notes</label>
          <textarea
            value={notesValue}
            onChange={(e) => setNotesValue(e.target.value)}
            placeholder="Document your investigation steps, findings, and actions taken..."
            rows={4}
            className="w-full bg-surface-700 border border-surface-600 text-slate-200
                       text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500
                       resize-none"
          />
        </div>

        <button
          onClick={handleSave}
          disabled={updateMutation.isPending}
          className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-700 text-white
                     rounded-lg transition-colors disabled:opacity-50"
        >
          {updateMutation.isPending ? "Saving..." : "Save Changes"}
        </button>

        {updateMutation.isSuccess && (
          <span className="ml-3 text-xs text-green-400">Saved successfully</span>
        )}
      </div>
    </div>
  );
}

// ─── Helper ───────────────────────────────────────────────────────────────────

function MetaItem({
  icon: Icon,
  label,
  value,
}: {
  icon?: React.ComponentType<{ size?: number; className?: string }>;
  label: string;
  value: string;
}) {
  return (
    <div>
      <div className="flex items-center gap-1 mb-0.5">
        {Icon && <Icon size={11} className="text-slate-500" />}
        <p className="text-xs text-slate-500">{label}</p>
      </div>
      <p className="text-sm text-slate-200">{value}</p>
    </div>
  );
}