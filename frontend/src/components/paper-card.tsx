"use client";

import { Paper } from "@/lib/types";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import Link from "next/link";
import { ExternalLink, FileText, GitFork, Video } from "lucide-react";

const sourceIcons: Record<string, React.ReactNode> = {
  paper: <FileText className="h-3 w-3" />,
  blog: <FileText className="h-3 w-3" />,
  talk: <Video className="h-3 w-3" />,
  project: <GitFork className="h-3 w-3" />,
};

// Per-source-type score labels. The two values map onto the universal
// quality_score and relevance_score fields; mirrors backend kb/reports.py.
const SCORE_LABELS: Record<string, [string, string]> = {
  paper: ["Originality", "Impact"],
  blog: ["Depth", "Actionability"],
  talk: ["Depth", "Actionability"],
  project: ["Innovation", "Maturity"],
};

function _resolveScores(paper: Paper): { quality: number; relevance: number } {
  // Papers: prefer the universal fields (canonical post-migration), fall back
  // to legacy originality/impact only if universal is exactly zero (true for
  // pre-migration rows that were scored before the universal-axis schema).
  // Mirrors backend/kb/reports.py::_score_line.
  if (paper.source_type === "paper") {
    return {
      quality: paper.quality_score || paper.originality_score,
      relevance: paper.relevance_score || paper.impact_score,
    };
  }
  return { quality: paper.quality_score, relevance: paper.relevance_score };
}

function ScoreBar({ label, score }: { label: string; score: number }) {
  const width = Math.round(score * 10);
  const color = score >= 7 ? "bg-emerald-500" : score >= 4 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2 text-[11px] sm:text-xs">
      <span className="text-zinc-500 w-16 sm:w-20 shrink-0 truncate">{label}</span>
      <div className="flex-1 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${width}%` }} />
      </div>
      <span className="text-zinc-400 w-8 text-right tabular-nums">{score.toFixed(1)}</span>
    </div>
  );
}

export function PaperCard({ paper }: { paper: Paper }) {
  const [qLabel, rLabel] = SCORE_LABELS[paper.source_type] ?? ["Quality", "Relevance"];
  const { quality, relevance } = _resolveScores(paper);
  return (
    <Card className="bg-zinc-900 border-zinc-800 hover:border-zinc-700 transition-colors">
      <CardContent className="p-3 sm:p-4">
        <div className="flex items-start justify-between gap-2 sm:gap-3">
          <div className="flex-1 min-w-0">
            <Link href={`/paper/${paper.id}`} className="hover:text-emerald-400 transition-colors">
              <h3 className="font-medium text-sm leading-snug line-clamp-2 break-words">{paper.title}</h3>
            </Link>
            <p className="text-[11px] sm:text-xs text-zinc-400 mt-1 line-clamp-1">
              {paper.authors.slice(0, 3).join(", ")}
              {paper.authors.length > 3 ? ` +${paper.authors.length - 3} more` : ""}
              {paper.venue ? ` \u00b7 ${paper.venue}` : ""}
            </p>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <Badge variant="outline" className="text-[10px] h-5 px-1.5 gap-1 border-zinc-700 text-zinc-400 max-w-[90px] sm:max-w-none truncate">
              {sourceIcons[paper.source_type]}
              <span className="truncate">{paper.source_name}</span>
            </Badge>
          </div>
        </div>

        {paper.summary ? (
          <p className="text-xs text-zinc-400 mt-2 line-clamp-2">{paper.summary}</p>
        ) : (
          <p className="text-xs text-zinc-500 mt-2 line-clamp-2 italic">Processing...</p>
        )}

        <div className="mt-3 space-y-1">
          <ScoreBar label={qLabel} score={quality} />
          <ScoreBar label={rLabel} score={relevance} />
        </div>

        <div className="flex items-center gap-3 mt-3">
          {paper.url && (
            <a href={paper.url} target="_blank" rel="noopener noreferrer"
               className="text-xs text-zinc-500 hover:text-zinc-300 flex items-center gap-1">
              <ExternalLink className="h-3 w-3" /> Source
            </a>
          )}
          {paper.pdf_url && (
            <a href={paper.pdf_url} target="_blank" rel="noopener noreferrer"
               className="text-xs text-zinc-500 hover:text-zinc-300 flex items-center gap-1">
              <FileText className="h-3 w-3" /> PDF
            </a>
          )}
          <span className="text-[10px] text-zinc-600 ml-auto">
            {paper.published_date ? new Date(paper.published_date).toLocaleDateString() : ""}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
