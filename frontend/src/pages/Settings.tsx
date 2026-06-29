// src/pages/Settings.tsx
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getOrg, updateOrg } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { Building2, Save, CheckCircle2 } from "lucide-react";

export default function Settings() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const isAdmin = user?.role === "admin";

  const { data: org, isLoading } = useQuery({
    queryKey: ["org"],
    queryFn: getOrg,
  });

  const [form, setForm] = useState({
    name:          org?.name ?? "",
    dpo_name:      org?.dpo_name ?? "",
    dpo_email:     org?.dpo_email ?? "",
    address:       org?.address ?? "",
    cert_in_email: org?.cert_in_email ?? "",
  });

  // Sync form when org data loads
  if (org && !form.name && !isLoading) {
    setForm({
      name:          org.name,
      dpo_name:      org.dpo_name,
      dpo_email:     org.dpo_email,
      address:       org.address ?? "",
      cert_in_email: org.cert_in_email,
    });
  }

  const mutation = useMutation({
    mutationFn: () => updateOrg(form),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["org"] }),
  });

  if (isLoading) {
    return <div className="text-center text-slate-500 py-16">Loading settings...</div>;
  }

  return (
    <div className="max-w-2xl">
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-1">
          <Building2 size={18} className="text-blue-400" />
          <h2 className="text-xl font-semibold text-white">Organisation Settings</h2>
        </div>
        <p className="text-sm text-slate-400">
          This information appears on all DPDP Act 2023 breach notification PDFs.
          {!isAdmin && " Only admins can update these settings."}
        </p>
      </div>

      <div className="bg-surface-800 rounded-xl border border-surface-700 p-6 space-y-4">
        {[
          { label: "Organisation Name",       key: "name",          placeholder: "Coimbatore Medical College Hospital" },
          { label: "Data Protection Officer", key: "dpo_name",      placeholder: "Dr. Full Name" },
          { label: "DPO Email",               key: "dpo_email",     placeholder: "dpo@organisation.in" },
          { label: "Organisation Address",    key: "address",       placeholder: "City, State, PIN Code" },
          { label: "CERT-In Notification Email", key: "cert_in_email", placeholder: "incident@cert-in.org.in" },
        ].map(({ label, key, placeholder }) => (
          <div key={key}>
            <label className="text-xs text-slate-400 mb-1 block">{label}</label>
            <input
              type="text"
              value={form[key as keyof typeof form]}
              onChange={(e) => setForm(prev => ({ ...prev, [key]: e.target.value }))}
              placeholder={placeholder}
              disabled={!isAdmin}
              className="w-full bg-surface-700 border border-surface-600 text-slate-200
                         text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500
                         disabled:opacity-50 disabled:cursor-not-allowed"
            />
          </div>
        ))}

        {isAdmin && (
          <div className="flex items-center gap-3 pt-2">
            <button
              onClick={() => mutation.mutate()}
              disabled={mutation.isPending}
              className="flex items-center gap-2 px-4 py-2 text-sm
                         bg-blue-600 hover:bg-blue-700 text-white rounded-lg
                         transition-colors disabled:opacity-50"
            >
              <Save size={14} />
              {mutation.isPending ? "Saving..." : "Save Settings"}
            </button>
            {mutation.isSuccess && (
              <div className="flex items-center gap-1 text-xs text-green-400">
                <CheckCircle2 size={13} />
                Saved
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}