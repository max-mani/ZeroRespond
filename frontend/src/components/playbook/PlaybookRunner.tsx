// src/components/playbook/PlaybookRunner.tsx
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { completeStep } from "../../api/client";
import type { Playbook, PlaybookStep } from "../../types";
import {
  CheckCircle2, Circle, ChevronDown, ChevronUp,
  Terminal, Target, AlertTriangle
} from "lucide-react";
import { clsx } from "clsx";

interface Props {
  playbook: Playbook;
  caseId: string;
  completedStepIds?: number[];  // IDs of steps already completed for this case
}

export default function PlaybookRunner({ playbook, caseId, completedStepIds = [] }: Props) {
  const queryClient = useQueryClient();
  const [expandedStep, setExpandedStep] = useState<number | null>(playbook.steps[0]?.id ?? null);
  const [localCompleted, setLocalCompleted] = useState<Set<number>>(new Set(completedStepIds));
  const [activeTab, setActiveTab] = useState<"linux" | "windows">("linux");

  const completeMutation = useMutation({
    mutationFn: ({ stepId }: { stepId: number }) => completeStep(caseId, stepId),
    onSuccess: (_, { stepId }) => {
      setLocalCompleted(prev => new Set([...prev, stepId]));
      queryClient.invalidateQueries({ queryKey: ["case", caseId] });
    },
  });

  const completedCount = localCompleted.size;
  const totalSteps = playbook.steps.length;
  const progressPct = totalSteps > 0 ? (completedCount / totalSteps) * 100 : 0;

  return (
    <div className="space-y-4">

      {/* Header + Progress */}
      <div className="bg-surface-800 rounded-xl border border-surface-700 p-5">
        <h3 className="text-sm font-semibold text-white mb-1">{playbook.name}</h3>
        {playbook.description && (
          <p className="text-xs text-slate-400 mb-4">{playbook.description}</p>
        )}

        <div className="flex items-center gap-3">
          <div className="flex-1 h-2 bg-surface-600 rounded-full overflow-hidden">
            <div
              className="h-2 rounded-full bg-blue-500 transition-all duration-500"
              style={{ width: `${progressPct}%` }}
            />
          </div>
          <span className="text-xs text-slate-400 shrink-0">
            {completedCount} / {totalSteps} steps
          </span>
        </div>
      </div>

      {/* Steps */}
      <div className="space-y-2">
        {playbook.steps.map((step, idx) => {
          const isCompleted = localCompleted.has(step.id);
          const isExpanded  = expandedStep === step.id;
          const isBlocking  = step.is_blocking && !isCompleted && idx > 0 &&
                              !localCompleted.has(playbook.steps[idx - 1]?.id ?? -1);

          return (
            <div
              key={step.id}
              className={clsx(
                "bg-surface-800 border rounded-xl overflow-hidden transition-colors",
                isCompleted ? "border-green-500/30" : "border-surface-700"
              )}
            >
              {/* Step header */}
              <button
                onClick={() => setExpandedStep(isExpanded ? null : step.id)}
                className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-surface-700 transition-colors"
              >
                {/* Complete/pending icon */}
                {isCompleted ? (
                  <CheckCircle2 size={18} className="text-green-400 shrink-0" />
                ) : (
                  <Circle size={18} className="text-slate-600 shrink-0" />
                )}

                {/* Step number + title */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-500 font-mono">
                      Step {step.step_number}
                    </span>
                    {step.is_blocking && (
                      <span className="text-xs text-red-400 font-medium">REQUIRED</span>
                    )}
                  </div>
                  <p className={clsx(
                    "text-sm font-medium mt-0.5",
                    isCompleted ? "text-slate-400 line-through" : "text-slate-200"
                  )}>
                    {step.title}
                  </p>
                </div>

                {/* Expand toggle */}
                {isExpanded
                  ? <ChevronUp size={14} className="text-slate-500 shrink-0" />
                  : <ChevronDown size={14} className="text-slate-500 shrink-0" />
                }
              </button>

              {/* Step detail (expanded) */}
              {isExpanded && (
                <div className="px-4 pb-4 space-y-4 border-t border-surface-700 pt-4">

                  {/* Description */}
                  <p className="text-sm text-slate-300 leading-relaxed">
                    {step.description}
                  </p>

                  {/* Goal */}
                  {step.goal && (
                    <div className="flex items-start gap-2 bg-blue-500/10 border border-blue-500/20 rounded-lg p-3">
                      <Target size={14} className="text-blue-400 shrink-0 mt-0.5" />
                      <p className="text-xs text-blue-300">
                        <span className="font-semibold">Goal: </span>
                        {step.goal}
                      </p>
                    </div>
                  )}

                  {/* Commands */}
                  {(step.linux_cmd || step.windows_cmd) && (
                    <div>
                      {/* OS tab switcher */}
                      <div className="flex gap-1 mb-2">
                        {step.linux_cmd && (
                          <button
                            onClick={() => setActiveTab("linux")}
                            className={clsx(
                              "text-xs px-3 py-1 rounded-md transition-colors",
                              activeTab === "linux"
                                ? "bg-surface-600 text-slate-200"
                                : "text-slate-500 hover:text-slate-300"
                            )}
                          >
                            Linux
                          </button>
                        )}
                        {step.windows_cmd && (
                          <button
                            onClick={() => setActiveTab("windows")}
                            className={clsx(
                              "text-xs px-3 py-1 rounded-md transition-colors",
                              activeTab === "windows"
                                ? "bg-surface-600 text-slate-200"
                                : "text-slate-500 hover:text-slate-300"
                            )}
                          >
                            Windows
                          </button>
                        )}
                      </div>

                      {/* Command block */}
                      <div className="bg-slate-900 border border-surface-600 rounded-lg p-3">
                        <div className="flex items-center gap-2 mb-2">
                          <Terminal size={12} className="text-slate-500" />
                          <span className="text-xs text-slate-500">
                            {activeTab === "linux" ? "Bash" : "PowerShell"}
                          </span>
                        </div>
                        <pre className="text-xs text-green-300 font-mono whitespace-pre-wrap overflow-x-auto">
                          {activeTab === "linux" ? step.linux_cmd : step.windows_cmd}
                        </pre>
                      </div>
                    </div>
                  )}

                  {/* Complete button */}
                  {!isCompleted && (
                    <button
                      onClick={() => completeMutation.mutate({ stepId: step.id })}
                      disabled={completeMutation.isPending}
                      className="flex items-center gap-2 px-4 py-2 text-xs
                                 bg-green-600 hover:bg-green-700 text-white rounded-lg
                                 transition-colors disabled:opacity-50"
                    >
                      <CheckCircle2 size={13} />
                      {completeMutation.isPending ? "Marking complete..." : "Mark as Complete"}
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}