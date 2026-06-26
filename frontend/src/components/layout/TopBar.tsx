// src/components/layout/TopBar.tsx
import { useQuery } from "@tanstack/react-query";
import { getAiHealth } from "../../api/client";
import { useAuth } from "../../context/AuthContext";
import { Cpu, Circle, LogOut, User } from "lucide-react";

export default function TopBar() {
  const { data: aiHealth } = useQuery({
    queryKey: ["ai-health"],
    queryFn: getAiHealth,
    refetchInterval: 30_000,
  });
  const { user, logout } = useAuth();
  const aiOk = aiHealth?.status === "ok";

  return (
    <header className="h-14 bg-surface-800 border-b border-surface-700
                       flex items-center justify-between px-6 shrink-0">
      <h1 className="text-sm font-medium text-slate-300">
        Incident Response Platform
      </h1>

      <div className="flex items-center gap-5">
        {/* AI Status */}
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <Cpu size={14} />
          <span>AI Agent</span>
          <Circle size={8} className={aiOk ? "text-green-400 fill-green-400" : "text-red-400 fill-red-400"} />
          <span className={aiOk ? "text-green-400" : "text-red-400"}>
            {aiOk ? "Online" : "Offline"}
          </span>
        </div>

        {/* User info */}
        {user && (
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <User size={13} />
            <span>{user.email}</span>
            <span className="text-slate-600">·</span>
            <span className="text-blue-400 capitalize">{user.role}</span>
          </div>
        )}

        {/* Logout */}
        <button
          onClick={logout}
          className="flex items-center gap-1.5 text-xs text-slate-500
                     hover:text-red-400 transition-colors"
        >
          <LogOut size={13} />
          Sign out
        </button>
      </div>
    </header>
  );
}