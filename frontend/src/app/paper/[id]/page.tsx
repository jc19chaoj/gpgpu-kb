"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { getPaper } from "@/lib/api";
import { Paper } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ExternalLink, FileText, Calendar, Users, Building2, Tag, Trophy, MessageSquare } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Link from "next/link";
import { useLocale } from "@/lib/i18n/provider";
import { formatDate } from "@/lib/i18n/format";
import { SCORE_LABEL_KEYS } from "@/components/paper-card";

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
        {/* Track and label colors come from the active theme via currentColor.
            We set text-muted on the outer <svg> and stroke="currentColor" on
            the rail so it follows light / dark automatically. The progress
            arc still uses the explicit hue passed in for the score axis. */}
        <g className="text-muted">
          <circle cx="36" cy="36" r={radius} fill="none" stroke="currentColor" strokeWidth="5" />
        </g>
        <circle
          cx="36" cy="36" r={radius} fill="none" stroke={color} strokeWidth="5"
          strokeLinecap="round" strokeDasharray={circumference} strokeDashoffset={offset}
          transform="rotate(-90 36 36)" className="transition-all duration-700"
        />
        <text x="36" y="36" textAnchor="middle" dy="6" className="text-sm font-bold fill-foreground">
          {value.toFixed(1)}
        </text>
      </svg>
      <span className="text-[10px] text-muted-foreground">{label}</span>
    </div>
  );
}

export default function PaperDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [paper, setPaper] = useState<Paper | null>(null);
  const [loading, setLoading] = useState(true);
  const { locale, t } = useLocale();

  useEffect(() => {
    if (!id) return;
    getPaper(Number(id)).then(setPaper).finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto p-4 sm:p-6 space-y-4">
        <Skeleton className="h-8 w-3/4 bg-card" />
        <Skeleton className="h-4 w-1/2 bg-card" />
        <Skeleton className="h-64 w-full bg-card" />
      </div>
    );
  }

  if (!paper) {
    return (
      <div className="max-w-3xl mx-auto p-4 sm:p-6 text-center py-16">
        <p className="text-muted-foreground">{t("paper.notFound")}</p>
        <Link href="/" className="text-sm text-primary hover:underline mt-2 inline-block">
          {t("paper.back")}
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto p-4 sm:p-6">
      <Link href="/" className="text-xs text-muted-foreground hover:text-foreground mb-4 inline-block">
        {t("paper.back")}
      </Link>

      <div className="mb-6">
        <div className="flex items-start justify-between gap-3">
          <h1 className="text-lg sm:text-xl font-semibold leading-snug break-words min-w-0">{paper.title}</h1>
          <Badge variant="outline" className="shrink-0 border-border text-muted-foreground text-xs">
            {paper.source_type}
          </Badge>
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 mt-3 text-sm text-muted-foreground">
          {paper.authors.length > 0 && (
            <span className="flex items-center gap-1.5">
              <Users className="h-3.5 w-3.5" />
              {paper.authors.slice(0, 4).join(", ")}
              {paper.authors.length > 4
                ? t("paper.morePeople", { count: paper.authors.length - 4 })
                : ""}
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
              {formatDate(paper.published_date, locale)}
            </span>
          )}
          {paper.venue && (
            <span className="flex items-center gap-1.5 text-primary">
              <Trophy className="h-3.5 w-3.5" />
              {paper.venue}
            </span>
          )}
        </div>

        <div className="flex items-center gap-4 mt-3">
          {paper.url && (
            <a href={paper.url} target="_blank" rel="noopener noreferrer"
               className="text-sm text-primary hover:underline flex items-center gap-1">
              <ExternalLink className="h-3.5 w-3.5" /> {t("paper.openSource")}
            </a>
          )}
          {paper.pdf_url && (
            <a href={paper.pdf_url} target="_blank" rel="noopener noreferrer"
               className="text-sm text-primary hover:underline flex items-center gap-1">
              <FileText className="h-3.5 w-3.5" /> {t("paper.pdf")}
            </a>
          )}
          <Link
            href={`/chat?paperId=${paper.id}`}
            className="text-sm text-primary hover:underline flex items-center gap-1"
          >
            <MessageSquare className="h-3.5 w-3.5" /> {t("paper.chatAbout")}
          </Link>
        </div>

        {paper.categories.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-3">
            {paper.categories.map((cat, i) => (
              <Badge key={i} variant="secondary" className="text-[10px] bg-muted text-muted-foreground">
                <Tag className="h-3 w-3 mr-1" /> {cat}
              </Badge>
            ))}
          </div>
        )}
      </div>

      {(() => {
        const [qKey, rKey] = SCORE_LABEL_KEYS[paper.source_type] ?? [
          "score.quality",
          "score.relevance",
        ];
        const { quality, relevance } = resolveScores(paper);
        const rationale = paper.score_rationale || paper.impact_rationale;
        return (
          <Card className="bg-card border-border mb-6">
            <CardContent className="p-4">
              <div className="flex items-center justify-center gap-8 sm:gap-12">
                {/* Two distinct warm hues for the two score axes — caramel
                    amber pairs with sage olive. Both have enough chroma to
                    read on Cream Linen and Walnut Hearth alike. */}
                <ScoreCircle value={quality} label={t(qKey)} color="#c89058" />
                <ScoreCircle value={relevance} label={t(rKey)} color="#7ea05a" />
              </div>
              {rationale && (
                <p className="text-sm text-muted-foreground mt-4 text-center italic">{rationale}</p>
              )}
            </CardContent>
          </Card>
        );
      })()}

      {paper.summary ? (
        <Card className="bg-card border-border mb-6">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">{t("paper.summary")}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="prose prose-sm dark:prose-invert max-w-none text-foreground/85">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {paper.summary}
              </ReactMarkdown>
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card className="bg-card border-border mb-6">
          <CardContent className="p-6 text-center text-muted-foreground">
            <p>{t("paper.processingHint")}</p>
          </CardContent>
        </Card>
      )}

      {paper.abstract && (
        <Card className="bg-card border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">
              {paper.source_type === "paper"
                ? t("paper.originalAbstract")
                : t("paper.originalExcerpt")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground leading-relaxed">{paper.abstract}</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
