"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { getPaper } from "@/lib/api";
import { Paper } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ExternalLink, FileText, Calendar, Users, Building2, Tag, Trophy } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Link from "next/link";

// Per-source-type score labels. Mirrors components/paper-card.tsx and
// backend kb/reports.py::SCORE_LABELS.
const SCORE_LABELS: Record<string, [string, string]> = {
  paper: ["Originality", "Impact"],
  blog: ["Depth", "Actionability"],
  talk: ["Depth", "Actionability"],
  project: ["Innovation", "Maturity"],
};

function resolveScores(paper: Paper): { quality: number; relevance: number } {
  if (paper.source_type === "paper") {
    return {
      quality: paper.quality_score || paper.originality_score,
      relevance: paper.relevance_score || paper.impact_score,
    };
  }
  return { quality: paper.quality_score, relevance: paper.relevance_score };
}

function ScoreCircle({ value, label, color }: { value: number; label: string; color: string }) {
  const radius = 28;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (value / 10) * circumference;
  return (
    <div className="flex flex-col items-center gap-1">
      <svg width="72" height="72" viewBox="0 0 72 72">
        <circle cx="36" cy="36" r={radius} fill="none" stroke="rgb(39,39,42)" strokeWidth="5" />
        <circle
          cx="36" cy="36" r={radius} fill="none" stroke={color} strokeWidth="5"
          strokeLinecap="round" strokeDasharray={circumference} strokeDashoffset={offset}
          transform="rotate(-90 36 36)" className="transition-all duration-700"
        />
        <text x="36" y="36" textAnchor="middle" dy="6" className="text-sm font-bold fill-zinc-100">
          {value.toFixed(1)}
        </text>
      </svg>
      <span className="text-[10px] text-zinc-500">{label}</span>
    </div>
  );
}

export default function PaperDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [paper, setPaper] = useState<Paper | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    getPaper(Number(id)).then(setPaper).finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto p-6 space-y-4">
        <Skeleton className="h-8 w-3/4 bg-zinc-900" />
        <Skeleton className="h-4 w-1/2 bg-zinc-900" />
        <Skeleton className="h-64 w-full bg-zinc-900" />
      </div>
    );
  }

  if (!paper) {
    return (
      <div className="max-w-3xl mx-auto p-6 text-center py-16">
        <p className="text-zinc-500">Paper not found.</p>
        <Link href="/" className="text-sm text-emerald-400 hover:underline mt-2 inline-block">
          Back to browse
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto p-6">
      <Link href="/" className="text-xs text-zinc-500 hover:text-zinc-300 mb-4 inline-block">
        ← Back to browse
      </Link>

      <div className="mb-6">
        <div className="flex items-start justify-between gap-4">
          <h1 className="text-xl font-semibold leading-snug">{paper.title}</h1>
          <Badge variant="outline" className="shrink-0 border-zinc-700 text-zinc-400 text-xs">
            {paper.source_type}
          </Badge>
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 mt-3 text-sm text-zinc-400">
          {paper.authors.length > 0 && (
            <span className="flex items-center gap-1.5">
              <Users className="h-3.5 w-3.5" />
              {paper.authors.slice(0, 4).join(", ")}
              {paper.authors.length > 4 ? ` +${paper.authors.length - 4}` : ""}
            </span>
          )}
          {paper.organizations.length > 0 && (
            <span className="flex items-center gap-1.5">
              <Building2 className="h-3.5 w-3.5" />
              {paper.organizations.join(", ")}
            </span>
          )}
          {paper.published_date && (
            <span className="flex items-center gap-1.5">
              <Calendar className="h-3.5 w-3.5" />
              {new Date(paper.published_date).toLocaleDateString()}
            </span>
          )}
          {paper.venue && (
            <span className="flex items-center gap-1.5 text-emerald-400">
              <Trophy className="h-3.5 w-3.5" />
              {paper.venue}
            </span>
          )}
        </div>

        <div className="flex items-center gap-4 mt-3">
          {paper.url && (
            <a href={paper.url} target="_blank" rel="noopener noreferrer"
               className="text-sm text-emerald-400 hover:underline flex items-center gap-1">
              <ExternalLink className="h-3.5 w-3.5" /> Open source
            </a>
          )}
          {paper.pdf_url && (
            <a href={paper.pdf_url} target="_blank" rel="noopener noreferrer"
               className="text-sm text-emerald-400 hover:underline flex items-center gap-1">
              <FileText className="h-3.5 w-3.5" /> PDF
            </a>
          )}
        </div>

        {paper.categories.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-3">
            {paper.categories.map((cat, i) => (
              <Badge key={i} variant="secondary" className="text-[10px] bg-zinc-800 text-zinc-400">
                <Tag className="h-3 w-3 mr-1" /> {cat}
              </Badge>
            ))}
          </div>
        )}
      </div>

      {(() => {
        const [qLabel, rLabel] = SCORE_LABELS[paper.source_type] ?? ["Quality", "Relevance"];
        const { quality, relevance } = resolveScores(paper);
        const rationale = paper.score_rationale || paper.impact_rationale;
        return (
          <Card className="bg-zinc-900 border-zinc-800 mb-6">
            <CardContent className="p-4">
              <div className="flex items-center justify-center gap-12">
                <ScoreCircle value={quality} label={qLabel} color="#10b981" />
                <ScoreCircle value={relevance} label={rLabel} color="#3b82f6" />
              </div>
              {rationale && (
                <p className="text-sm text-zinc-400 mt-4 text-center italic">{rationale}</p>
              )}
            </CardContent>
          </Card>
        );
      })()}

      {paper.summary ? (
        <Card className="bg-zinc-900 border-zinc-800 mb-6">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Summary</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="prose prose-invert prose-sm max-w-none text-zinc-300">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {paper.summary}
              </ReactMarkdown>
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card className="bg-zinc-900 border-zinc-800 mb-6">
          <CardContent className="p-6 text-center text-zinc-500">
            <p>This item is still being processed. Summary coming soon.</p>
          </CardContent>
        </Card>
      )}

      {paper.abstract && (
        <Card className="bg-zinc-900 border-zinc-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">
              {paper.source_type === "paper" ? "Original Abstract" : "Original Excerpt"}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-zinc-400 leading-relaxed">{paper.abstract}</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
