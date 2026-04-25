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

export interface ChatRequest {
  query: string;
  top_k?: number;
}

export interface ChatResponse {
  answer: string;
  sources: Paper[];
}

export interface Stats {
  total_papers: number;
  processed: number;
  by_type: Record<string, number>;
  top_impact: { id: number; title: string; impact_score: number }[];
}
