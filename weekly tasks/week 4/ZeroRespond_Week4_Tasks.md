# ZeroRespond — Week 4 Task List
**Phase 4 · React Frontend · ZeroDashboard — Incident List + Case Detail + Alert Feed**

> **Goal by end of Week 4:** A working React dashboard that connects to your FastAPI backend and displays real data. Responders can see all active cases, filter by severity and status, open a case to view the full AI summary and MITRE technique, update case status, and see the live alert feed. No authentication yet — that is Week 5. Focus is on getting real data on screen with a clean, functional UI.

---

## What you have coming in from Week 3

- `GET /cases` — paginated, filterable list of cases with AI fields
- `GET /cases/{id}` — full case detail including `ai_summary`, `ai_mitre`, `ai_confidence`, `immediate_action`
- `PATCH /cases/{id}` — partial update (status, notes, assigned_to)
- `POST /alerts` — alert ingestion with async AI enrichment
- `GET /alerts` — list of all ingested alerts
- `POST /cases/{id}/re-enrich` — re-run AI on existing case
- `GET /health/ai` — Ollama status check
- Seed data: 5 realistic cases covering all 5 breach types

---

## Week 4 Architecture

```
frontend/
├── src/
│   ├── api/
│   │   └── client.ts          ← Axios instance + all API calls typed
│   ├── components/
│   │   ├── layout/
│   │   │   ├── Sidebar.tsx    ← Navigation sidebar
│   │   │   └── TopBar.tsx     ← Header with system status
│   │   ├── cases/
│   │   │   ├── CaseList.tsx   ← Table of all cases with filters
│   │   │   ├── CaseCard.tsx   ← Single row in the case list
│   │   │   ├── CaseDetail.tsx ← Full case view with AI summary
│   │   │   └── StatusBadge.tsx ← Coloured severity/status pill
│   │   └── alerts/
│   │       └── AlertFeed.tsx  ← Live list of recent alerts
│   ├── pages/
│   │   ├── Dashboard.tsx      ← Overview: counts + recent cases
│   │   ├── Cases.tsx          ← Full case list page
│   │   ├── CasePage.tsx       ← Single case detail page
│   │   └── Alerts.tsx         ← Alert feed page
│   ├── types/
│   │   └── index.ts           ← TypeScript types matching backend schemas
│   ├── App.tsx
│   └── main.tsx
├── package.json
└── vite.config.ts
```

---

## Tech Stack for Week 4

- **Vite + React 18 + TypeScript** — fast dev server, type safety
- **Tailwind CSS** — utility-first styling, no custom CSS files
- **React Router v6** — client-side routing between pages
- **Axios** — HTTP client for API calls
- **React Query (TanStack Query)** — server state management, caching, auto-refetch
- **Recharts** — for the dashboard summary charts
- **Lucide React** — icon library

---

## Day 1 — React Project Setup + API Client

### Task 1.1 — Scaffold the Vite + React + TypeScript project

```bash
cd frontend
npm create vite@latest . -- --template react-ts
# When prompted: select React, then TypeScript
npm install
```

Verify it boots:
```bash
npm run dev
# Should open http://localhost:5173
```

---

### Task 1.2 — Install all dependencies

```bash
npm install \
  axios \
  @tanstack/react-query \
  react-router-dom \
  recharts \
  lucide-react \
  clsx

npm install -D tailwindcss postcss autoprefixer @types/node
npx tailwindcss init -p
```

---

### Task 1.3 — Configure Tailwind CSS

Update `tailwind.config.js`:

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // ZeroRespond dark theme palette
        surface: {
          900: "#0f172a",   // page background
          800: "#1e293b",   // card/panel background
          700: "#334155",   // elevated surfaces
          600: "#475569",   // borders
        },
        severity: {
          critical: "#ef4444",   // red
          high:     "#f97316",   // orange
          medium:   "#eab308",   // yellow
          low:      "#22c55e",   // green
        }
      }
    },
  },
  plugins: [],
}
```

Update `src/index.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

body {
  background-color: #0f172a;
  color: #f1f5f9;
  font-family: 'Inter', system-ui, sans-serif;
}
```

---

### Task 1.4 — Create TypeScript types matching backend schemas

Create `src/types/index.ts`:

```typescript
// src/types/index.ts
// These types must match the Pydantic schemas in backend/app/schemas/

export type Severity = "critical" | "high" | "medium" | "low";
export type Status = "open" | "investigating" | "contained" | "resolved" | "closed";
export type BreachType =
  | "ransomware"
  | "phishing"
  | "unauthorized_access"
  | "exfiltration"
  | "insider";

// Matches CaseListItem schema
export interface CaseListItem {
  id: string;
  title: string;
  severity: Severity;
  status: Status;
  breach_type: BreachType;
  source_ip: string | null;
  source_host: string | null;
  assigned_to: string | null;
  ai_confidence: number | null;
  detected_at: string; // ISO datetime string
}

// Matches CaseDetail schema
export interface CaseDetail {
  id: string;
  title: string;
  severity: Severity;
  status: Status;
  breach_type: BreachType;
  data_categories: string | null;
  persons_affected: number | null;
  breach_est_at: string | null;
  source_host: string | null;
  source_ip: string | null;
  alert_id: string | null;
  playbook_id: number | null;
  assigned_to: string | null;
  ai_summary: string | null;
  ai_confidence: number | null;
  ai_mitre: string | null;
  immediate_action: string | null;
  notes: string | null;
  detected_at: string;
  resolved_at: string | null;
  created_at: string;
  updated_at: string | null;
}

// Matches CaseUpdate schema
export interface CaseUpdate {
  status?: Status;
  severity?: Severity;
  assigned_to?: string;
  notes?: string;
  data_categories?: string;
  persons_affected?: number;
  resolved_at?: string;
}

// Matches AlertOut schema
export interface AlertOut {
  id: string;
  wazuh_rule_id: number;
  level: number;
  description: string;
  source_ip: string | null;
  host: string;
  groups: string[] | null;
  attack_type: string | null;
  received_at: string;
}

// Dashboard summary (computed on frontend from case list)
export interface DashboardStats {
  total: number;
  open: number;
  critical: number;
  high: number;
  by_breach_type: Record<BreachType, number>;
}
```

---

### Task 1.5 — Create the API client

Create `src/api/client.ts`:

```typescript
// src/api/client.ts
import axios from "axios";
import type { CaseListItem, CaseDetail, CaseUpdate, AlertOut } from "../types";

const api = axios.create({
  baseURL: "http://localhost:8000",
  headers: { "Content-Type": "application/json" },
  timeout: 15000,
});

// ─── Cases ────────────────────────────────────────────────────────────────────

export const getCases = async (params?: {
  skip?: number;
  limit?: number;
  status?: string;
  severity?: string;
  breach_type?: string;
}): Promise<CaseListItem[]> => {
  const { data } = await api.get("/cases", { params });
  return data;
};

export const getCase = async (id: string): Promise<CaseDetail> => {
  const { data } = await api.get(`/cases/${id}`);
  return data;
};

export const updateCase = async (
  id: string,
  payload: CaseUpdate
): Promise<CaseDetail> => {
  const { data } = await api.patch(`/cases/${id}`, payload);
  return data;
};

export const reEnrichCase = async (id: string): Promise<CaseDetail> => {
  const { data } = await api.post(`/cases/${id}/re-enrich`);
  return data;
};

// ─── Alerts ───────────────────────────────────────────────────────────────────

export const getAlerts = async (params?: {
  skip?: number;
  limit?: number;
  host?: string;
}): Promise<AlertOut[]> => {
  const { data } = await api.get("/alerts", { params });
  return data;
};

// ─── Health ───────────────────────────────────────────────────────────────────

export const getHealth = async () => {
  const { data } = await api.get("/health");
  return data;
};

export const getAiHealth = async () => {
  const { data } = await api.get("/health/ai");
  return data;
};
```

---

### Task 1.6 — Set up React Query and Router in main.tsx

```tsx
// src/main.tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,       // Data is fresh for 30 seconds
      refetchInterval: 60_000, // Auto-refetch every 60 seconds
      retry: 2,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
```

---

### Task 1.7 — Create App.tsx with routing

```tsx
// src/App.tsx
import { Routes, Route, Navigate } from "react-router-dom";
import Sidebar from "./components/layout/Sidebar";
import TopBar from "./components/layout/TopBar";
import Dashboard from "./pages/Dashboard";
import Cases from "./pages/Cases";
import CasePage from "./pages/CasePage";
import Alerts from "./pages/Alerts";

export default function App() {
  return (
    <div className="flex h-screen bg-surface-900 text-slate-100 overflow-hidden">
      <Sidebar />
      <div className="flex flex-col flex-1 overflow-hidden">
        <TopBar />
        <main className="flex-1 overflow-y-auto p-6">
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/cases" element={<Cases />} />
            <Route path="/cases/:id" element={<CasePage />} />
            <Route path="/alerts" element={<Alerts />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
```

Commit:
```bash
git add frontend/
git commit -m "feat: vite react ts scaffold, tailwind config, types, api client, router"
```

---

## Day 2 — Layout Components (Sidebar + TopBar)

### Task 2.1 — Create the Sidebar

Create `src/components/layout/Sidebar.tsx`:

```tsx
// src/components/layout/Sidebar.tsx
import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  FolderOpen,
  Bell,
  Shield,
} from "lucide-react";
import { clsx } from "clsx";

const navItems = [
  { to: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/cases",     icon: FolderOpen,      label: "Cases"     },
  { to: "/alerts",    icon: Bell,            label: "Alerts"    },
];

export default function Sidebar() {
  return (
    <aside className="w-56 bg-surface-800 border-r border-surface-700 flex flex-col shrink-0">
      {/* Logo */}
      <div className="flex items-center gap-2 px-4 py-5 border-b border-surface-700">
        <Shield className="text-blue-400" size={22} />
        <span className="font-bold text-white tracking-wide text-sm">
          ZeroRespond
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-2 py-4 space-y-1">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              clsx(
                "flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors",
                isActive
                  ? "bg-blue-600 text-white font-medium"
                  : "text-slate-400 hover:text-slate-100 hover:bg-surface-700"
              )
            }
          >
            <Icon size={16} />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-surface-700">
        <p className="text-xs text-slate-500">DPDP Act 2023 Compliant</p>
      </div>
    </aside>
  );
}
```

---

### Task 2.2 — Create the TopBar

Create `src/components/layout/TopBar.tsx`:

```tsx
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
```

---

### Task 2.3 — Create shared StatusBadge component

Create `src/components/cases/StatusBadge.tsx`:

```tsx
// src/components/cases/StatusBadge.tsx
import { clsx } from "clsx";
import type { Severity, Status, BreachType } from "../../types";

// ─── Severity badge ───────────────────────────────────────────────────────────

const severityStyles: Record<string, string> = {
  critical: "bg-red-500/20 text-red-400 border border-red-500/30",
  high:     "bg-orange-500/20 text-orange-400 border border-orange-500/30",
  medium:   "bg-yellow-500/20 text-yellow-400 border border-yellow-500/30",
  low:      "bg-green-500/20 text-green-400 border border-green-500/30",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className={clsx("px-2 py-0.5 rounded text-xs font-medium uppercase tracking-wide",
      severityStyles[severity])}>
      {severity}
    </span>
  );
}

// ─── Status badge ─────────────────────────────────────────────────────────────

const statusStyles: Record<string, string> = {
  open:          "bg-blue-500/20 text-blue-400 border border-blue-500/30",
  investigating: "bg-purple-500/20 text-purple-400 border border-purple-500/30",
  contained:     "bg-yellow-500/20 text-yellow-400 border border-yellow-500/30",
  resolved:      "bg-green-500/20 text-green-400 border border-green-500/30",
  closed:        "bg-slate-500/20 text-slate-400 border border-slate-500/30",
};

export function StatusBadge({ status }: { status: Status }) {
  return (
    <span className={clsx("px-2 py-0.5 rounded text-xs font-medium capitalize",
      statusStyles[status])}>
      {status}
    </span>
  );
}

// ─── Breach type badge ────────────────────────────────────────────────────────

const breachLabels: Record<BreachType, string> = {
  ransomware:          "Ransomware",
  phishing:            "Phishing",
  unauthorized_access: "Unauth. Access",
  exfiltration:        "Exfiltration",
  insider:             "Insider",
};

export function BreachTypeBadge({ type }: { type: BreachType }) {
  return (
    <span className="px-2 py-0.5 rounded text-xs font-medium
                     bg-slate-700 text-slate-300 border border-slate-600">
      {breachLabels[type]}
    </span>
  );
}
```

Commit:
```bash
git add frontend/src/
git commit -m "feat: sidebar, topbar with AI status indicator, severity/status/breach badges"
```

---

## Day 3 — Cases List Page

### Task 3.1 — Create the CaseList component

Create `src/components/cases/CaseList.tsx`:

```tsx
// src/components/cases/CaseList.tsx
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { getCases } from "../../api/client";
import { SeverityBadge, StatusBadge, BreachTypeBadge } from "./StatusBadge";
import type { Severity, Status, BreachType } from "../../types";
import { formatDistanceToNow } from "../utils/time";
import { ChevronRight, RefreshCw } from "lucide-react";

export default function CaseList() {
  const navigate = useNavigate();
  const [severityFilter, setSeverityFilter] = useState<Severity | "">("");
  const [statusFilter, setStatusFilter]     = useState<Status | "">("");
  const [breachFilter, setBreachFilter]     = useState<BreachType | "">("");

  const { data: cases, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["cases", severityFilter, statusFilter, breachFilter],
    queryFn: () => getCases({
      severity:    severityFilter    || undefined,
      status:      statusFilter      || undefined,
      breach_type: breachFilter      || undefined,
      limit: 100,
    }),
  });

  return (
    <div>
      {/* Filter bar */}
      <div className="flex items-center gap-3 mb-4">
        <select
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value as Severity | "")}
          className="bg-surface-800 border border-surface-600 text-slate-300
                     text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-blue-500"
        >
          <option value="">All severities</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as Status | "")}
          className="bg-surface-800 border border-surface-600 text-slate-300
                     text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-blue-500"
        >
          <option value="">All statuses</option>
          <option value="open">Open</option>
          <option value="investigating">Investigating</option>
          <option value="contained">Contained</option>
          <option value="resolved">Resolved</option>
          <option value="closed">Closed</option>
        </select>

        <select
          value={breachFilter}
          onChange={(e) => setBreachFilter(e.target.value as BreachType | "")}
          className="bg-surface-800 border border-surface-600 text-slate-300
                     text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-blue-500"
        >
          <option value="">All types</option>
          <option value="ransomware">Ransomware</option>
          <option value="phishing">Phishing</option>
          <option value="unauthorized_access">Unauthorized Access</option>
          <option value="exfiltration">Exfiltration</option>
          <option value="insider">Insider</option>
        </select>

        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="ml-auto flex items-center gap-2 text-xs text-slate-400
                     hover:text-slate-200 transition-colors"
        >
          <RefreshCw size={13} className={isFetching ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="text-center text-slate-500 py-16">Loading cases...</div>
      ) : !cases || cases.length === 0 ? (
        <div className="text-center text-slate-500 py-16">No cases found.</div>
      ) : (
        <div className="bg-surface-800 rounded-xl border border-surface-700 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-700 text-slate-400 text-xs uppercase tracking-wide">
                <th className="text-left px-4 py-3">Case ID</th>
                <th className="text-left px-4 py-3">Title</th>
                <th className="text-left px-4 py-3">Severity</th>
                <th className="text-left px-4 py-3">Status</th>
                <th className="text-left px-4 py-3">Type</th>
                <th className="text-left px-4 py-3">Host</th>
                <th className="text-left px-4 py-3">Confidence</th>
                <th className="text-left px-4 py-3">Detected</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-700">
              {cases.map((c) => (
                <tr
                  key={c.id}
                  onClick={() => navigate(`/cases/${c.id}`)}
                  className="hover:bg-surface-700 cursor-pointer transition-colors"
                >
                  <td className="px-4 py-3 font-mono text-xs text-slate-400">
                    {c.id}
                  </td>
                  <td className="px-4 py-3 text-slate-100 max-w-xs truncate">
                    {c.title}
                  </td>
                  <td className="px-4 py-3">
                    <SeverityBadge severity={c.severity} />
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={c.status} />
                  </td>
                  <td className="px-4 py-3">
                    <BreachTypeBadge type={c.breach_type} />
                  </td>
                  <td className="px-4 py-3 text-slate-400 font-mono text-xs">
                    {c.source_host ?? "—"}
                  </td>
                  <td className="px-4 py-3">
                    {c.ai_confidence != null ? (
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1.5 bg-surface-600 rounded-full">
                          <div
                            className="h-1.5 rounded-full bg-blue-500"
                            style={{ width: `${c.ai_confidence}%` }}
                          />
                        </div>
                        <span className="text-xs text-slate-400">
                          {c.ai_confidence.toFixed(0)}%
                        </span>
                      </div>
                    ) : (
                      <span className="text-xs text-slate-600">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-400 text-xs">
                    {formatDistanceToNow(c.detected_at)}
                  </td>
                  <td className="px-4 py-3">
                    <ChevronRight size={14} className="text-slate-600" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
```

---

### Task 3.2 — Create a time formatting utility

Create `src/components/utils/time.ts`:

```typescript
// src/components/utils/time.ts

export function formatDistanceToNow(isoString: string): string {
  const date = new Date(isoString);
  const now  = new Date();
  const diff = Math.floor((now.getTime() - date.getTime()) / 1000); // seconds

  if (diff < 60)   return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export function formatDatetime(isoString: string): string {
  return new Date(isoString).toLocaleString("en-IN", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}
```

---

### Task 3.3 — Create the Cases page

Create `src/pages/Cases.tsx`:

```tsx
// src/pages/Cases.tsx
import CaseList from "../components/cases/CaseList";

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
```

Commit:
```bash
git add frontend/src/
git commit -m "feat: cases list page with severity/status/breach_type filters and confidence bar"
```

---

## Day 4 — Case Detail Page

### Task 4.1 — Create CaseDetail component

Create `src/components/cases/CaseDetail.tsx`:

```tsx
// src/components/cases/CaseDetail.tsx
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateCase, reEnrichCase } from "../../api/client";
import { SeverityBadge, StatusBadge, BreachTypeBadge } from "./StatusBadge";
import { formatDatetime } from "../utils/time";
import type { CaseDetail as CaseDetailType, Status } from "../../types";
import {
  Brain, Shield, AlertTriangle, Clock,
  User, Database, RefreshCw, ChevronDown
} from "lucide-react";

interface Props {
  caseData: CaseDetailType;
}

export default function CaseDetail({ caseData: c }: Props) {
  const queryClient = useQueryClient();
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
```

---

### Task 4.2 — Create the CasePage route page

Create `src/pages/CasePage.tsx`:

```tsx
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
```

Commit:
```bash
git add frontend/src/
git commit -m "feat: case detail page with AI analysis, immediate action, DPDP fields, update form"
```

---

## Day 5 — Dashboard + Alert Feed

### Task 5.1 — Create the Dashboard page

Create `src/pages/Dashboard.tsx`:

```tsx
// src/pages/Dashboard.tsx
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { getCases } from "../api/client";
import { SeverityBadge, StatusBadge } from "../components/cases/StatusBadge";
import { formatDistanceToNow } from "../components/utils/time";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";
import { AlertTriangle, FolderOpen, Shield, Activity } from "lucide-react";

const BREACH_COLORS: Record<string, string> = {
  ransomware:          "#ef4444",
  phishing:            "#f97316",
  unauthorized_access: "#3b82f6",
  exfiltration:        "#a855f7",
  insider:             "#eab308",
};

export default function Dashboard() {
  const navigate = useNavigate();

  const { data: cases, isLoading } = useQuery({
    queryKey: ["cases"],
    queryFn: () => getCases({ limit: 100 }),
    refetchInterval: 30_000,
  });

  if (isLoading) {
    return <div className="text-center text-slate-500 py-16">Loading...</div>;
  }

  const allCases = cases ?? [];

  // Compute stats
  const total    = allCases.length;
  const open     = allCases.filter((c) => c.status === "open").length;
  const critical = allCases.filter((c) => c.severity === "critical").length;
  const high     = allCases.filter((c) => c.severity === "high").length;

  // Breach type distribution for chart
  const breachCounts = allCases.reduce<Record<string, number>>((acc, c) => {
    acc[c.breach_type] = (acc[c.breach_type] ?? 0) + 1;
    return acc;
  }, {});
  const chartData = Object.entries(breachCounts).map(([name, value]) => ({ name, value }));

  // 5 most recent cases
  const recent = [...allCases]
    .sort((a, b) => new Date(b.detected_at).getTime() - new Date(a.detected_at).getTime())
    .slice(0, 5);

  return (
    <div className="space-y-6">

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard icon={FolderOpen}    label="Total Cases"      value={total}    color="blue"   />
        <StatCard icon={Activity}      label="Open"             value={open}     color="blue"   />
        <StatCard icon={AlertTriangle} label="Critical"         value={critical} color="red"    />
        <StatCard icon={Shield}        label="High Severity"    value={high}     color="orange" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">

        {/* Breach type chart */}
        <div className="bg-surface-800 rounded-xl border border-surface-700 p-6">
          <h3 className="text-sm font-semibold text-white mb-4">Breach Type Distribution</h3>
          {chartData.length === 0 ? (
            <p className="text-slate-500 text-sm text-center py-8">No data yet</p>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie
                  data={chartData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                  label={({ name, percent }) =>
                    `${name.replace("_", " ")} ${(percent * 100).toFixed(0)}%`
                  }
                  labelLine={false}
                >
                  {chartData.map((entry) => (
                    <Cell
                      key={entry.name}
                      fill={BREACH_COLORS[entry.name] ?? "#64748b"}
                    />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#1e293b",
                    border: "1px solid #334155",
                    borderRadius: "8px",
                    color: "#f1f5f9",
                    fontSize: "12px",
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Recent cases */}
        <div className="bg-surface-800 rounded-xl border border-surface-700 p-6">
          <h3 className="text-sm font-semibold text-white mb-4">Recent Cases</h3>
          {recent.length === 0 ? (
            <p className="text-slate-500 text-sm">No cases yet.</p>
          ) : (
            <div className="space-y-3">
              {recent.map((c) => (
                <div
                  key={c.id}
                  onClick={() => navigate(`/cases/${c.id}`)}
                  className="flex items-center justify-between gap-3 p-3
                             bg-surface-700 rounded-lg cursor-pointer
                             hover:bg-surface-600 transition-colors"
                >
                  <div className="min-w-0">
                    <p className="text-sm text-slate-200 truncate">{c.title}</p>
                    <p className="text-xs text-slate-500 font-mono mt-0.5">{c.id}</p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <SeverityBadge severity={c.severity} />
                    <StatusBadge status={c.status} />
                    <span className="text-xs text-slate-500">
                      {formatDistanceToNow(c.detected_at)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Stat card helper ────────────────────────────────────────────────────────

function StatCard({
  icon: Icon,
  label,
  value,
  color,
}: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  label: string;
  value: number;
  color: "blue" | "red" | "orange" | "green";
}) {
  const colorClass = {
    blue:   "text-blue-400",
    red:    "text-red-400",
    orange: "text-orange-400",
    green:  "text-green-400",
  }[color];

  return (
    <div className="bg-surface-800 rounded-xl border border-surface-700 p-5">
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs text-slate-400">{label}</p>
        <Icon size={16} className={colorClass} />
      </div>
      <p className={`text-2xl font-bold ${colorClass}`}>{value}</p>
    </div>
  );
}
```

---

### Task 5.2 — Create the Alert Feed page

Create `src/pages/Alerts.tsx`:

```tsx
// src/pages/Alerts.tsx
import { useQuery } from "@tanstack/react-query";
import { getAlerts } from "../api/client";
import { formatDistanceToNow } from "../components/utils/time";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { clsx } from "clsx";

const levelColor = (level: number) => {
  if (level >= 15) return "text-red-400";
  if (level >= 12) return "text-orange-400";
  if (level >= 8)  return "text-yellow-400";
  return "text-green-400";
};

export default function Alerts() {
  const { data: alerts, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["alerts"],
    queryFn:  () => getAlerts({ limit: 100 }),
    refetchInterval: 15_000,
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold text-white">Alert Feed</h2>
          <p className="text-sm text-slate-400 mt-1">
            Raw Wazuh alerts ingested into ZeroRespond.
          </p>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-2 text-xs text-slate-400
                     hover:text-slate-200 transition-colors"
        >
          <RefreshCw size={13} className={isFetching ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {isLoading ? (
        <div className="text-center text-slate-500 py-16">Loading alerts...</div>
      ) : !alerts || alerts.length === 0 ? (
        <div className="text-center text-slate-500 py-16">No alerts ingested yet.</div>
      ) : (
        <div className="bg-surface-800 rounded-xl border border-surface-700 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-700 text-slate-400 text-xs uppercase tracking-wide">
                <th className="text-left px-4 py-3">Level</th>
                <th className="text-left px-4 py-3">Alert ID</th>
                <th className="text-left px-4 py-3">Description</th>
                <th className="text-left px-4 py-3">Host</th>
                <th className="text-left px-4 py-3">Source IP</th>
                <th className="text-left px-4 py-3">Attack Type</th>
                <th className="text-left px-4 py-3">Received</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-700">
              {alerts.map((a) => (
                <tr key={a.id} className="hover:bg-surface-700 transition-colors">
                  <td className="px-4 py-3">
                    <span className={clsx("font-mono text-xs font-bold", levelColor(a.level))}>
                      L{a.level}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-400">
                    {a.id.slice(0, 20)}...
                  </td>
                  <td className="px-4 py-3 text-slate-200 max-w-xs truncate">
                    {a.description}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-400">
                    {a.host}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-400">
                    {a.source_ip ?? "—"}
                  </td>
                  <td className="px-4 py-3">
                    {a.attack_type ? (
                      <span className="text-xs text-blue-400 font-medium">
                        {a.attack_type.replace("_", " ")}
                      </span>
                    ) : (
                      <span className="text-xs text-slate-600 italic">pending AI</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-400">
                    {formatDistanceToNow(a.received_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
```

Commit:
```bash
git add frontend/src/
git commit -m "feat: dashboard with stats + breach type chart + recent cases, alert feed page"
```

---

## Day 6 — Polish + Vite Proxy + CORS Fix

### Task 6.1 — Configure Vite dev proxy

Right now the frontend calls `http://localhost:8000` directly. In production this will go through Nginx. For dev, configure a Vite proxy to avoid CORS issues:

Update `vite.config.ts`:

```ts
// vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
```

Update `src/api/client.ts` to use the proxy in dev:

```typescript
const api = axios.create({
  baseURL: import.meta.env.DEV ? "/api" : "http://localhost:8000",
  headers: { "Content-Type": "application/json" },
  timeout: 15000,
});
```

---

### Task 6.2 — Add loading skeletons

Create `src/components/ui/Skeleton.tsx`:

```tsx
// src/components/ui/Skeleton.tsx
export function SkeletonRow() {
  return (
    <tr className="animate-pulse">
      {Array.from({ length: 7 }).map((_, i) => (
        <td key={i} className="px-4 py-3">
          <div className="h-3 bg-surface-600 rounded w-3/4" />
        </td>
      ))}
    </tr>
  );
}

export function SkeletonCard() {
  return (
    <div className="bg-surface-800 rounded-xl border border-surface-700 p-6 animate-pulse">
      <div className="h-4 bg-surface-600 rounded w-1/3 mb-3" />
      <div className="h-8 bg-surface-600 rounded w-1/4" />
    </div>
  );
}
```

---

### Task 6.3 — Add error boundary for API failures

Create `src/components/ui/ErrorMessage.tsx`:

```tsx
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
```

Use it in Cases and Dashboard when `isError` is true:

```tsx
// In Cases.tsx
import ErrorMessage from "../components/ui/ErrorMessage";

// Add inside the component:
{isError && (
  <ErrorMessage message="Could not connect to the ZeroRespond API. Is the backend running on port 8000?" />
)}
```

---

### Task 6.4 — Add a page title to each route

Update `App.tsx` to use `document.title` per route. The simplest way is a custom hook:

```typescript
// src/hooks/usePageTitle.ts
import { useEffect } from "react";

export function usePageTitle(title: string) {
  useEffect(() => {
    document.title = `${title} — ZeroRespond`;
  }, [title]);
}
```

Use in each page:
```tsx
// In Dashboard.tsx
import { usePageTitle } from "../hooks/usePageTitle";
export default function Dashboard() {
  usePageTitle("Dashboard");
  // ...
}
```

Commit:
```bash
git add frontend/
git commit -m "feat: vite proxy, loading skeletons, error messages, page titles"
```

---

## Day 7 — Final Verification + Week 4 Completion Check

### Task 7.1 — Start the full stack and verify everything

```bash
# Terminal 1: PostgreSQL
docker start zr-postgres

# Terminal 2: Ollama
sudo systemctl start ollama

# Terminal 3: FastAPI backend
cd backend && source venv/bin/activate
uvicorn app.main:app --reload

# Terminal 4: React frontend
cd frontend
npm run dev
```

Open http://localhost:5173 in the browser.

---

### Task 7.2 — Run the Week 4 completion checklist

Go through each item manually in the browser:

```
✓ Dashboard loads and shows 4 stat cards with real counts
✓ Dashboard pie chart shows breach type distribution
✓ Dashboard recent cases list shows 5 cases with correct badges
✓ Cases page loads and shows all cases from seed data
✓ Severity filter works — selecting "critical" shows 1 case
✓ Status filter works — selecting "open" hides "investigating" cases
✓ Breach type filter works
✓ Clicking a case row navigates to /cases/{id}
✓ Case detail shows AI summary, MITRE code, confidence, immediate action
✓ MITRE code links to attack.mitre.org
✓ "Re-run AI" button triggers re-enrichment and updates after ~10s
✓ Status dropdown changes and Save button updates the case
✓ Notes textarea saves and persists on page reload
✓ Alerts page shows all 5 seed alerts with level colours
✓ Alerts marked with attack_type show the AI classification
✓ Alerts still pending show "pending AI" in italic
✓ TopBar AI status indicator shows green when Ollama is running
✓ TopBar AI status shows red when Ollama is stopped
```

---

### Task 7.3 — Test with a live alert

While the frontend is open, send a new alert from curl:

```bash
curl -X POST http://localhost:8000/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "id": "week4-live-test-001",
    "wazuh_rule_id": 92001,
    "level": 15,
    "description": "Ransomware signature detected — live frontend test",
    "source_ip": null,
    "host": "test-server-01",
    "groups": ["ransomware", "encrypt"],
    "raw_json": {"rule_id": "92001", "level": 15}
  }'
```

Then:
1. Go to the Cases page — the new case should appear immediately (case ID format `IR-YYYYMMDD-XXXX`)
2. Click into it — `ai_summary` will be `null` at first
3. Wait 15-30 seconds and refresh the case — AI fields should now be populated
4. Go to the Alerts page — the new alert should appear with `attack_type: "ransomware"` after enrichment

---

### Task 7.4 — Final commit and tag

```bash
git add .
git commit -m "feat: week 4 complete — react dashboard, case list, case detail, alert feed"
git tag v0.4.0-week4
git push origin main --tags
```

---

## Week 4 Summary

| Day | What you built | Verification |
|-----|----------------|-------------|
| 1 | Vite + React + TypeScript scaffold, Tailwind config, TypeScript types matching backend, Axios API client, React Query setup, React Router | `npm run dev` boots, `/api` proxy works |
| 2 | Sidebar navigation, TopBar with live AI status indicator, SeverityBadge / StatusBadge / BreachTypeBadge components | All badges render with correct colours |
| 3 | CaseList component with 3 filters (severity, status, breach type), confidence bar, sortable rows, click-to-navigate | Filters work, table shows all seed data |
| 4 | CaseDetail with AI summary panel, immediate action highlight, DPDP section, status/notes update form, re-enrich button | PATCH saves, re-enrich updates AI fields |
| 5 | Dashboard with 4 stat cards, Recharts pie chart, recent cases list. Alert feed table with level colouring and AI status | All data pulls from real API |
| 6 | Vite dev proxy, skeleton loaders, error messages, page titles | No CORS errors, graceful failure states |
| 7 | Full checklist: 19 manual checks + live alert test end-to-end | New alert appears in UI and gets AI-enriched in real time |

**You are now ready for Week 5 — Authentication + DPDP Report Generation.**

---

*ZeroRespond · Manikandan · KCT 2023–2027*
