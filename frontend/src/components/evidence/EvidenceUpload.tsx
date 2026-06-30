// src/components/evidence/EvidenceUpload.tsx
import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getEvidence, uploadEvidence, deleteEvidenceFile } from "../../api/client";
import { useAuth } from "../../context/AuthContext";
import {
  Upload, FileText, Image as ImageIcon, FileArchive,
  Download, Trash2, Paperclip
} from "lucide-react";
import { formatDistanceToNow } from "../utils/time";

interface Props {
  caseId: string;
}

const TOKEN_KEY = "zr_access_token";

function fileIcon(filename: string) {
  const ext = filename.split(".").pop()?.toLowerCase();
  if (["png", "jpg", "jpeg"].includes(ext ?? "")) return ImageIcon;
  if (["zip", "pcap", "pcapng"].includes(ext ?? "")) return FileArchive;
  return FileText;
}

function formatBytes(bytes: number | null): string {
  if (bytes == null) return "Unknown size";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function EvidenceUpload({ caseId }: Props) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [description, setDescription] = useState("");
  const [dragActive, setDragActive] = useState(false);

  const { data: evidenceList, isLoading } = useQuery({
    queryKey: ["evidence", caseId],
    queryFn: () => getEvidence(caseId),
  });

  const uploadMutation = useMutation({
    mutationFn: ({ file, desc }: { file: File; desc: string }) =>
      uploadEvidence(caseId, file, desc),
    onSuccess: () => {
      setDescription("");
      queryClient.invalidateQueries({ queryKey: ["evidence", caseId] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (evidenceId: number) => deleteEvidenceFile(evidenceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["evidence", caseId] });
    },
  });

  const handleFileSelect = (file: File) => {
    uploadMutation.mutate({ file, desc: description });
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFileSelect(file);
  };

  const handleDownload = (evidenceId: number, filename: string) => {
    const token = localStorage.getItem(TOKEN_KEY);
    fetch(`/api/evidence/${evidenceId}/download`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => res.blob())
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
      });
  };

  const isAdmin = user?.role === "admin";

  return (
    <div className="bg-surface-800 rounded-xl border border-surface-700 p-6">
      <div className="flex items-center gap-2 mb-4">
        <Paperclip size={16} className="text-blue-400" />
        <h3 className="text-sm font-semibold text-white">Evidence</h3>
        {evidenceList && (
          <span className="text-xs text-slate-500">({evidenceList.length})</span>
        )}
      </div>

      <div
        onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer
                   transition-colors mb-4 ${
          dragActive
            ? "border-blue-500 bg-blue-500/5"
            : "border-surface-600 hover:border-surface-500"
        }`}
      >
        <Upload size={20} className="mx-auto text-slate-500 mb-2" />
        <p className="text-sm text-slate-400">
          {uploadMutation.isPending ? "Uploading..." : "Drag and drop a file, or click to browse"}
        </p>
        <p className="text-xs text-slate-600 mt-1">
          Max 50MB · PNG, JPG, PDF, TXT, LOG, CSV, JSON, PCAP, ZIP, EVTX
        </p>
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFileSelect(file);
          }}
        />
      </div>

      <input
        type="text"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Description for the next upload (optional)"
        className="w-full bg-surface-700 border border-surface-600 text-slate-200
                   text-sm rounded-lg px-3 py-2 mb-4 focus:outline-none focus:border-blue-500"
      />

      {uploadMutation.isError && (
        <p className="text-xs text-red-400 mb-3">
          Upload failed: {(uploadMutation.error as any)?.response?.data?.detail ?? "Unknown error"}
        </p>
      )}

      {isLoading ? (
        <p className="text-sm text-slate-500">Loading evidence...</p>
      ) : !evidenceList || evidenceList.length === 0 ? (
        <p className="text-sm text-slate-500">No evidence uploaded yet.</p>
      ) : (
        <div className="space-y-2">
          {evidenceList.map((ev) => {
            const Icon = fileIcon(ev.filename);
            return (
              <div
                key={ev.id}
                className="flex items-center gap-3 bg-surface-700 rounded-lg p-3"
              >
                <Icon size={16} className="text-slate-400 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-slate-200 truncate">{ev.filename}</p>
                  {ev.description && (
                    <p className="text-xs text-slate-500 truncate">{ev.description}</p>
                  )}
                  <p className="text-xs text-slate-600 mt-0.5">
                    {formatBytes(ev.file_size)} · {ev.uploaded_by ?? "Unknown"} ·{" "}
                    {formatDistanceToNow(ev.uploaded_at)}
                  </p>
                </div>
                <button
                  onClick={() => handleDownload(ev.id, ev.filename)}
                  className="p-1.5 text-slate-400 hover:text-blue-400 transition-colors"
                  title="Download"
                >
                  <Download size={14} />
                </button>
                {isAdmin && (
                  <button
                    onClick={() => {
                      if (confirm(`Delete ${ev.filename}?`)) {
                        deleteMutation.mutate(ev.id);
                      }
                    }}
                    className="p-1.5 text-slate-400 hover:text-red-400 transition-colors"
                    title="Delete"
                  >
                    <Trash2 size={14} />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}