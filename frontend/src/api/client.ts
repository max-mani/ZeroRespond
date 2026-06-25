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