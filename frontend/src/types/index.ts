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