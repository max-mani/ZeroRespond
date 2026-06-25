// src/components/ui/ErrorMessage.tsx
import { AlertTriangle } from "lucide-react";

export default function ErrorMessage({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-3 bg-red-500/10 border border-red-500/20
                    rounded-lg p-4 text-sm text-red-400">
      <AlertTriangle size={16} className="shrink-0" />
      {message}
    </div>
  );
}