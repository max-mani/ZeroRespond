// src/pages/PlaybookPage.tsx
import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getCase, getCasePlaybook } from "../api/client";
import PlaybookRunner from "../components/playbook/PlaybookRunner";
import { ArrowLeft, BookOpen } from "lucide-react";

export default function PlaybookPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: caseData } = useQuery({
    queryKey: ["case", id],
    queryFn: () => getCase(id!),
    enabled: !!id,
  });

  const { data: playbook, isLoading, isError } = useQuery({
    queryKey: ["playbook", id],
    queryFn: () => getCasePlaybook(id!),
    enabled: !!id,
  });

  return (
    <div>
      <div className="flex items-center gap-4 mb-6">
        <button
          onClick={() => navigate(`/cases/${id}`)}
          className="flex items-center gap-2 text-sm text-slate-400
                     hover:text-slate-200 transition-colors"
        >
          <ArrowLeft size={14} />
          Back to Case
        </button>
        {caseData && (
          <div>
            <div className="flex items-center gap-2">
              <BookOpen size={14} className="text-blue-400" />
              <span className="text-sm font-medium text-white">Response Playbook</span>
            </div>
            <p className="text-xs text-slate-500 font-mono">{caseData.id}</p>
          </div>
        )}
      </div>

      {isLoading && (
        <div className="text-center text-slate-500 py-16">Loading playbook...</div>
      )}
      {isError && (
        <div className="text-center text-slate-500 py-16">
          No playbook found for this breach type.
        </div>
      )}
      {playbook && caseData && (
        <PlaybookRunner
          playbook={playbook}
          caseId={id!}
          completedStepIds={[]}
        />
      )}
    </div>
  );
}