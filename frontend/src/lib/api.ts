// src/lib/api.ts
import {
  Paper,
  PaperListResponse,
  DailyReport,
  ChatRequest,
  ChatResponse,
  ChatStreamEvent,
  DailyStatus,
  DailyStreamEvent,
  SourcesResponse,
  Stats,
} from "./types";

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
  source_name?: string[]; // multi-select, joined with comma before sending
  sort_by?: string;
  sort_dir?: string;
}): Promise<PaperListResponse> {
  const sp = new URLSearchParams();
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v === undefined) return;
      if (k === "source_name") {
        const names = v as string[];
        if (names.length > 0) sp.set("source_name", names.join(","));
        return;
      }
      sp.set(k, String(v));
    });
  }
  return fetchJSON<PaperListResponse>(`/api/papers?${sp.toString()}`);
}

export async function listSources(): Promise<SourcesResponse> {
  return fetchJSON<SourcesResponse>(`/api/sources`);
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

function _chatPayload(request: ChatRequest): Record<string, unknown> {
  // Strip undefined / null fields so the backend's optional-with-default
  // pydantic schema sees a clean payload.
  const payload: Record<string, unknown> = { query: request.query };
  if (request.top_k !== undefined) payload.top_k = request.top_k;
  if (request.paper_id !== undefined && request.paper_id !== null) payload.paper_id = request.paper_id;
  if (request.history && request.history.length > 0) payload.history = request.history;
  return payload;
}

export async function chat(request: ChatRequest): Promise<ChatResponse> {
  return fetchJSON<ChatResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify(_chatPayload(request)),
  });
}

/**
 * Stream chat tokens from /api/chat/stream as an async generator of SSE
 * events. Pass `signal` to cancel the in-flight request (e.g. user-initiated
 * Stop button or component unmount).
 *
 * Throws on non-2xx responses or abort. The generator ends naturally when
 * the backend emits `done`. Callers should treat `error` events as terminal.
 */
export async function* chatStream(
  request: ChatRequest,
  options?: { signal?: AbortSignal },
): AsyncGenerator<ChatStreamEvent> {
  const resp = await fetch(`${API_BASE}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(_chatPayload(request)),
    signal: options?.signal,
  });
  if (!resp.ok || !resp.body) {
    throw new Error(`API error: ${resp.status} ${resp.statusText}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE frames are separated by a blank line ("\n\n"). Drain every
      // complete frame in the buffer; the trailing partial waits for more
      // bytes from the network.
      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const raw = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const event = _parseSSEFrame(raw);
        if (event) yield event;
      }
    }
    // Drain any final frame the server didn't terminate with \n\n.
    if (buffer.trim()) {
      const event = _parseSSEFrame(buffer);
      if (event) yield event;
    }
  } finally {
    try {
      reader.releaseLock();
    } catch {
      // releaseLock throws if the stream is already errored or cancelled —
      // safe to ignore here, we're tearing down.
    }
  }
}

function _parseSSEFrame(raw: string): ChatStreamEvent | null {
  let event = "";
  let data = "";
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    // Per SSE spec, consecutive `data:` lines concatenate with a literal
    // "\n". Today the backend only emits single-line frames, but joining
    // explicitly future-proofs against an LLM token containing a raw
    // newline (which would otherwise glue two JSON objects together and
    // make JSON.parse drop the frame silently).
    else if (line.startsWith("data:")) {
      if (data) data += "\n";
      data += line.slice(5).trim();
    }
  }
  if (!event) return null;
  try {
    const parsed = data ? JSON.parse(data) : {};
    if (event === "sources") return { type: "sources", sources: parsed.sources ?? [] };
    if (event === "token") return { type: "token", content: parsed.content ?? "" };
    if (event === "error") return { type: "error", message: parsed.message ?? "" };
    if (event === "done") return { type: "done" };
  } catch {
    return null;
  }
  return null;
}

export async function getDailyStatus(): Promise<DailyStatus> {
  return fetchJSON<DailyStatus>("/api/daily/status");
}

/**
 * Trigger `python -m kb.daily` (in-process on the backend) and stream
 * progress as SSE. Mirrors `chatStream()`: returns an async generator that
 * yields decoded events; pass `signal` to cancel the in-flight fetch (note:
 * cancelling the fetch does NOT abort the pipeline server-side — the
 * pipeline runs on a daemon thread and finishes on its own).
 *
 * Throws `DailyConflictError` if another run is already in flight (HTTP
 * 409). Other non-2xx responses throw a generic Error.
 */
export class DailyConflictError extends Error {
  constructor(message = "A daily pipeline run is already in progress.") {
    super(message);
    this.name = "DailyConflictError";
  }
}

export async function* runDailyStream(
  options?: { signal?: AbortSignal },
): AsyncGenerator<DailyStreamEvent> {
  const resp = await fetch(`${API_BASE}/api/daily/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: "{}",
    signal: options?.signal,
  });
  if (resp.status === 409) {
    // Drain the body so the connection can be reused.
    try { await resp.text(); } catch { /* best-effort */ }
    throw new DailyConflictError();
  }
  if (!resp.ok || !resp.body) {
    throw new Error(`API error: ${resp.status} ${resp.statusText}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const raw = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const event = _parseDailyFrame(raw);
        if (event) yield event;
      }
    }
    if (buffer.trim()) {
      const event = _parseDailyFrame(buffer);
      if (event) yield event;
    }
  } finally {
    try {
      reader.releaseLock();
    } catch {
      // releaseLock throws if the stream is already errored or cancelled —
      // safe to ignore here, we're tearing down.
    }
  }
}

function _parseDailyFrame(raw: string): DailyStreamEvent | null {
  let event = "";
  let data = "";
  for (const line of raw.split("\n")) {
    // Skip SSE comment frames (`: keepalive`) and any blank lines.
    if (!line || line.startsWith(":")) continue;
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) {
      if (data) data += "\n";
      data += line.slice(5).trim();
    }
  }
  if (!event) return null;
  try {
    const parsed = data ? JSON.parse(data) : {};
    if (event === "started") return { type: "started", started_at: parsed.started_at ?? "" };
    if (event === "stage") {
      const idx = parsed.index;
      if (idx !== 1 && idx !== 2 && idx !== 3 && idx !== 4) return null;
      return { type: "stage", index: idx, name: parsed.name };
    }
    if (event === "log") return { type: "log", line: parsed.line ?? "" };
    if (event === "error") return { type: "error", message: parsed.message ?? "" };
    if (event === "done") return { type: "done" };
  } catch {
    return null;
  }
  return null;
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
