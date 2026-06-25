// src/pages/Cases.tsx
import CaseList from "../components/cases/CaseList";
import ErrorMessage from "../components/ui/ErrorMessage";

export default function Cases() {
  return (
    <div>
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-white">Incident Cases</h2>
        <p className="text-sm text-slate-400 mt-1">
          All detected incidents. Click a case to view AI analysis and take action.
        </p>
      </div>
      <CaseList />
    </div>
  );
}