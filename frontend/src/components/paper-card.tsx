"use client";

import { Paper } from "@/lib/types";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import Link from "next/link";
import { ExternalLink, FileText, GitFork, Video } from "lucide-react";
import { useLocale } from "@/lib/i18n/provider";
import { formatDate } from "@/lib/i18n/format";
import type { TranslationKey } from "@/lib/i18n/translations";

const sourceIcons: Record<string, React.ReactNode> = {
  paper: <FileText className="h-3 w-3" />,
  blog: <FileText className="h-3 w-3" />,
  talk: <Video className="h-3 w-3" />,
  project: <GitFork className="h-3 w-3" />,
};

// Per-source-type score label *keys*. The two values map onto the universal
// quality_score and relevance_score fields; mirrors backend kb/reports.py.
// Resolved through the t() helper so we render them in the active locale.
export const SCORE_LABEL_KEYS: Record<string, [TranslationKey, TranslationKey]> = {
  paper: ["score.originality", "score.impact"],
  blog: ["score.depth", "score.actionability"],
  talk: ["score.depth", "score.actionability"],
  project: ["score.innovation", "score.maturity"],
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
  // Score ramp tuned to the warm theme: lime (positive) → amber (mid) →
  // rose (low). All three sit in the warm half of the wheel so they don't
  // clash with Cream Linen / Walnut Hearth backgrounds.
  const color =
    score >= 7 ? "bg-lime-600 dark:bg-lime-500"
    : score >= 4 ? "bg-amber-500"
    : "bg-rose-500";
  return (
    <div className="flex items-center gap-2 text-[11px] sm:text-xs">
      <span className="text-muted-foreground w-16 sm:w-20 shrink-0 truncate">{label}</span>
      <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${width}%` }} />
      </div>
      <span className="text-foreground/80 w-8 text-right tabular-nums">{score.toFixed(1)}</span>
    </div>
  );
}

export function PaperCard({ paper }: { paper: Paper }) {
  const { locale, t } = useLocale();
  const [qKey, rKey] = SCORE_LABEL_KEYS[paper.source_type] ?? [
    "score.quality",
    "score.relevance",
  ];
  const qLabel = t(qKey);
  const rLabel = t(rKey);
  const { quality, relevance } = _resolveScores(paper);
  return (
    <Card className="bg-card border-border hover:border-primary/40 transition-colors">
      <CardContent className="p-3 sm:p-4">
        <div className="flex items-start justify-between gap-2 sm:gap-3">
          <div className="flex-1 min-w-0">
            <Link href={`/paper/${paper.id}`} className="hover:text-primary transition-colors">
              <h3 className="font-medium text-sm leading-snug line-clamp-2 break-words">{paper.title}</h3>
            </Link>
            <p className="text-[11px] sm:text-xs text-muted-foreground mt-1 line-clamp-1">
              {paper.authors.slice(0, 3).join(", ")}
              {paper.authors.length > 3
                ? t("card.morePeople", { count: paper.authors.length - 3 })
                : ""}
              {paper.venue ? ` \u00b7 ${paper.venue}` : ""}
            </p>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <Badge variant="outline" className="text-[10px] h-5 px-1.5 gap-1 border-border text-muted-foreground max-w-[90px] sm:max-w-none truncate">
              {sourceIcons[paper.source_type]}
              <span className="truncate">{paper.source_name}</span>
            </Badge>
          </div>
        </div>

        {paper.summary ? (
          <p className="text-xs text-muted-foreground mt-2 line-clamp-2">{paper.summary}</p>
        ) : (
          <p className="text-xs text-muted-foreground/70 mt-2 line-clamp-2 italic">{t("card.processing")}</p>
        )}

        <div className="mt-3 space-y-1">
          <ScoreBar label={qLabel} score={quality} />
          <ScoreBar label={rLabel} score={relevance} />
        </div>

        <div className="flex items-center gap-3 mt-3">
          {paper.url && (
            <a href={paper.url} target="_blank" rel="noopener noreferrer"
               className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1">
              <ExternalLink className="h-3 w-3" /> {t("card.source")}
            </a>
          )}
          {paper.pdf_url && (
            <a href={paper.pdf_url} target="_blank" rel="noopener noreferrer"
               className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1">
              <FileText className="h-3 w-3" /> {t("card.pdf")}
            </a>
          )}
          <span className="text-[10px] text-muted-foreground/70 ml-auto">
            {formatDate(paper.published_date, locale)}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
