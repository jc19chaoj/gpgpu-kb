// src/lib/types.ts
export interface Paper {
  id: number;
  title: string;
  authors: string[];
  organizations: string[];
  abstract: string;
  url: string;
  pdf_url: string;
  source_type: "paper" | "blog" | "talk" | "project";
  source_name: string;
  published_date: string | null;
  ingested_date: string;
  categories: string[];
  venue: string;
  citation_count: number;
  summary: string;
  originality_score: number;
  impact_score: number;
  impact_rationale: string;
  // Universal score axes used by all source_types. Per-type display labels
  // live in components/paper-card.tsx; for papers these mirror originality
  // and impact respectively.
  quality_score: number;
  relevance_score: number;
  score_rationale: string;
}

export interface PaperListResponse {
  papers: Paper[];
  total: number;
  page: number;
  page_size: number;
}

export interface DailyReport {
  id: number;
  date: string;
  title: string;
  content: string;
  paper_ids: number[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatRequest {
  query: string;
  top_k?: number;
  // When set, anchor the conversation to a single source. The backend skips
  // semantic retrieval and feeds the full source content as the only context
  // (downloads the arxiv PDF on demand).
  paper_id?: number;
  // Prior conversation turns from this client-side session, in chronological
  // order. The backend keeps the most recent ~12 turns when building the
  // prompt.
  history?: ChatMessage[];
}

export interface ChatResponse {
  answer: string;
  sources: Paper[];
}

// SSE events emitted by /api/chat/stream. Decoded by `chatStream()` in
// lib/api.ts; keep in sync with backend `_sse_event(...)` in kb/main.py.
export type ChatStreamEvent =
  | { type: "sources"; sources: Paper[] }
  | { type: "token"; content: string }
  | { type: "error"; message: string }
  | { type: "done" };

// Daily pipeline status (snapshot from GET /api/daily/status). Used by the
// /reports page to render the right initial button state on page load —
// crucially, a refresh while a run is in-flight should show "running" not
// "idle".
export interface DailyStatus {
  running: boolean;
  started_at: string | null;
  current_stage: DailyStageName | null;
}

export type DailyStageName = "ingestion" | "processing" | "embedding" | "report";

// SSE events emitted by /api/daily/stream. Mirrors backend `_sse_event(...)`
// in kb/main.py::daily_stream. Adding a new event variant requires updating
// both sides + `_parseDailyFrame` in lib/api.ts.
export type DailyStreamEvent =
  | { type: "started"; started_at: string }
  | { type: "stage"; index: 1 | 2 | 3 | 4; name: DailyStageName }
  | { type: "log"; line: string }
  | { type: "error"; message: string }
  | { type: "done" };

export interface Stats {
  total_papers: number;
  processed: number;
  by_type: Record<string, number>;
  top_impact: { id: number; title: string; impact_score: number }[];
  top_overall?: {
    id: number;
    title: string;
    source_type: string;
    quality_score: number;
    relevance_score: number;
  }[];
}

// Distinct source_name bucket from GET /api/sources. Surfaces what source
// values exist in the knowledge base so the browse page can render filter
// tags without hardcoding the (growing) RSS / sitemap source list.
export interface Source {
  name: string;
  type: string; // "paper" | "blog" | "project" | "talk"
  count: number;
}

export interface SourcesResponse {
  sources: Source[];
}
