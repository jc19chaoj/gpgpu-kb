"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { getReport } from "@/lib/api";
import { DailyReport } from "@/lib/types";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Calendar } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Link from "next/link";
import { useLocale } from "@/lib/i18n/provider";
import { formatLongDate } from "@/lib/i18n/format";

export default function ReportDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [report, setReport] = useState<DailyReport | null>(null);
  const [loading, setLoading] = useState(true);
  const { locale, t } = useLocale();

  useEffect(() => {
    if (!id) return;
    getReport(Number(id)).then(setReport).finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto p-6 space-y-4">
        <Skeleton className="h-8 w-3/4 bg-card" />
        <Skeleton className="h-96 w-full bg-card" />
      </div>
    );
  }

  if (!report) {
    return (
      <div className="max-w-3xl mx-auto p-6 text-center py-16 text-muted-foreground">
        <p>{t("reports.notFound")}</p>
        <Link href="/reports" className="text-sm text-primary hover:underline mt-2 inline-block">
          {t("reports.back")}
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto p-6">
      <Link href="/reports" className="text-xs text-muted-foreground hover:text-foreground mb-4 inline-block">
        {t("reports.back")}
      </Link>
      <div className="flex items-center gap-3 mb-6">
        <Calendar className="h-5 w-5 text-primary" />
        <div>
          <h1 className="text-lg font-semibold">{report.title}</h1>
          <p className="text-sm text-muted-foreground">
            {formatLongDate(report.date, locale)}
          </p>
        </div>
      </div>
      <Card className="bg-card border-border">
        <CardContent className="p-6">
          {/* prose-invert is dark-mode-only; gate with Tailwind's dark: variant
              so the light theme uses the standard prose colors that auto-pick
              foreground from current text color. */}
          <div className="prose prose-sm dark:prose-invert max-w-none text-foreground/85">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {report.content}
            </ReactMarkdown>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
