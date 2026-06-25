// src/pages/CasePage.tsx
import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getCase } from "../api/client";
import CaseDetail from "../components/cases/CaseDetail";
import { ArrowLeft } from "lucide-react";

export default function CasePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: caseData, isLoading, isError } = useQuery({
    queryKey: ["case", id],
    queryFn: () => getCase(id!),
    refetchInterval: 10_000, // Poll every 10s so AI fields appear automatically
    enabled: !!id,
  });

  return (
    <div>
      <button
        onClick={() => navigate("/cases")}
        className="flex items-center gap-2 text-sm text-slate-400
                   hover:text-slate-200 transition-colors mb-6"
      >
        <ArrowLeft size={14} />
        Back to Cases
      </button>

      {isLoading && (
        <div className="text-center text-slate-500 py-16">Loading case...</div>
      )}
      {isError && (
        <div className="text-center text-red-400 py-16">
          Case not found or API error.
        </div>
      )}
      {caseData && <CaseDetail caseData={caseData} />}
    </div>
  );
}