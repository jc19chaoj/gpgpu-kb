// src/lib/api.ts
import { Paper, PaperListResponse, DailyReport, ChatRequest, ChatResponse, Stats } from "./types";

// Default to a relative URL so the browser hits the same origin it loaded from
// and lets the Next server proxy /api/* to the backend (see next.config.ts
// rewrites). Set NEXT_PUBLIC_API_URL only if you want to bypass that proxy and
// hit the backend directly (must be reachable from every client browser).
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
  return res.json();
}

export async function listPapers(params?: {
  page?: number;
  page_size?: number;
  source_type?: string;
  sort_by?: string;
  sort_dir?: string;
}): Promise<PaperListResponse> {
  const sp = new URLSearchParams();
  if (params) Object.entries(params).forEach(([k, v]) => { if (v !== undefined) sp.set(k, String(v)); });
  return fetchJSON<PaperListResponse>(`/api/papers?${sp.toString()}`);
}

export async function getPaper(id: number): Promise<Paper> {
  return fetchJSON<Paper>(`/api/papers/${id}`);
}

export async function searchPapers(q: string, params?: {
  page?: number;
  page_size?: number;
  semantic?: boolean;
  sort_by?: string;
  sort_dir?: string;
}): Promise<PaperListResponse> {
  const sp = new URLSearchParams({ q });
  if (params) Object.entries(params).forEach(([k, v]) => { if (v !== undefined) sp.set(k, String(v)); });
  return fetchJSON<PaperListResponse>(`/api/papers/search?${sp.toString()}`);
}

export async function chat(request: ChatRequest): Promise<ChatResponse> {
  return fetchJSON<ChatResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export async function listReports(limit?: number): Promise<DailyReport[]> {
  const sp = new URLSearchParams();
  if (limit) sp.set("limit", String(limit));
  return fetchJSON<DailyReport[]>(`/api/reports?${sp.toString()}`);
}

export async function getReport(id: number): Promise<DailyReport> {
  return fetchJSON<DailyReport>(`/api/reports/${id}`);
}

export async function getStats(): Promise<Stats> {
  return fetchJSON<Stats>("/api/stats");
}
