// src/components/layout/TopBar.tsx
import { useQuery } from "@tanstack/react-query";
import { getAiHealth } from "../../api/client";
import { Cpu, Circle } from "lucide-react";

export default function TopBar() {
  const { data: aiHealth } = useQuery({
    queryKey: ["ai-health"],
    queryFn: getAiHealth,
    refetchInterval: 30_000,
  });

  const aiOk = aiHealth?.status === "ok";

  return (
    <header className="h-14 bg-surface-800 border-b border-surface-700
                       flex items-center justify-between px-6 shrink-0">
      <h1 className="text-sm font-medium text-slate-300">
        Incident Response Platform
      </h1>

      {/* AI Status indicator */}
      <div className="flex items-center gap-2 text-xs text-slate-400">
        <Cpu size={14} />
        <span>AI Agent</span>
        <Circle
          size={8}
          className={aiOk ? "text-green-400 fill-green-400" : "text-red-400 fill-red-400"}
        />
        <span className={aiOk ? "text-green-400" : "text-red-400"}>
          {aiOk ? "Online" : "Offline"}
        </span>
      </div>
    </header>
  );
}