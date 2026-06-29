// src/api/client.ts
import axios from "axios";
import type { CaseListItem, CaseDetail, CaseUpdate, AlertOut } from "../types";

const TOKEN_KEY = "zr_access_token";

const api = axios.create({
  baseURL: import.meta.env.DEV ? "/api" : "http://localhost:8000",
  headers: { "Content-Type": "application/json" },
  timeout: 15000,
});

// Automatically attach JWT token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// On 401 response — clear token and redirect to login
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem(TOKEN_KEY);
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

// ─── Cases ───────────────────────────────────────────────────────────────────

export const getCases = async (params?: {
  skip?: number; limit?: number;
  status?: string; severity?: string; breach_type?: string;
}): Promise<CaseListItem[]> => {
  const { data } = await api.get("/cases", { params });
  return data;
};

export const getCase = async (id: string): Promise<CaseDetail> => {
  const { data } = await api.get(`/cases/${id}`);
  return data;
};

export const updateCase = async (id: string, payload: CaseUpdate): Promise<CaseDetail> => {
  const { data } = await api.patch(`/cases/${id}`, payload);
  return data;
};

export const reEnrichCase = async (id: string): Promise<CaseDetail> => {
  const { data } = await api.post(`/cases/${id}/re-enrich`);
  return data;
};

// ─── Alerts ──────────────────────────────────────────────────────────────────

export const getAlerts = async (params?: {
  skip?: number; limit?: number; host?: string;
}): Promise<AlertOut[]> => {
  const { data } = await api.get("/alerts", { params });
  return data;
};

// ─── Reports ─────────────────────────────────────────────────────────────────

export const generateReport = async (case_id: string): Promise<Blob> => {
  const { data } = await api.post(`/reports/${case_id}`, {}, { responseType: "blob" });
  return data;
};

// ─── Health ──────────────────────────────────────────────────────────────────

export const getHealth    = async () => { const { data } = await api.get("/health");    return data; };
export const getAiHealth  = async () => { const { data } = await api.get("/health/ai"); return data; };

// ─── Playbooks ────────────────────────────────────────────────────────────────

export const getPlaybooks = async () => {
  const { data } = await api.get("/playbooks");
  return data;
};

export const getPlaybook = async (attackType: string) => {
  const { data } = await api.get(`/playbooks/${attackType}`);
  return data;
};

export const getCasePlaybook = async (caseId: string) => {
  const { data } = await api.get(`/cases/${caseId}/playbook`);
  return data;
};

export const completeStep = async (caseId: string, stepId: number) => {
  const { data } = await api.post(`/cases/${caseId}/steps/${stepId}/complete`);
  return data;
};

// ─── Org ─────────────────────────────────────────────────────────────────────

export const getOrg = async () => {
  const { data } = await api.get("/org");
  return data;
};

export const updateOrg = async (payload: {
  name?: string;
  dpo_name?: string;
  dpo_email?: string;
  address?: string;
  cert_in_email?: string;
}) => {
  const { data } = await api.put("/org", payload);
  return data;
};