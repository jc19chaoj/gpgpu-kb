"use client";

import { useEffect, useState } from "react";
import { listReports } from "@/lib/api";
import { DailyReport } from "@/lib/types";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Calendar } from "lucide-react";
import Link from "next/link";
import { useLocale } from "@/lib/i18n/provider";
import { formatLongDate } from "@/lib/i18n/format";

export default function ReportsPage() {
  const [reports, setReports] = useState<DailyReport[]>([]);
  const [loading, setLoading] = useState(true);
  const { locale, t } = useLocale();

  useEffect(() => {
    listReports(30).then(setReports).finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto p-4 sm:p-6 space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-20 w-full bg-card" />
        ))}
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto p-4 sm:p-6">
      <h1 className="text-base sm:text-lg font-semibold mb-4">{t("reports.title")}</h1>
      <div className="space-y-3">
        {reports.map((report) => (
          <Link key={report.id} href={`/reports/${report.id}`}>
            <Card className="bg-card border-border hover:border-primary/40 transition-colors cursor-pointer">
              <CardContent className="p-4">
                <div className="flex items-center gap-3">
                  <Calendar className="h-4 w-4 text-primary shrink-0" />
                  <div>
                    <h3 className="text-sm font-medium">{report.title}</h3>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {formatLongDate(report.date, locale)}
                      {" · "}
                      {t("reports.papersCovered", { count: report.paper_ids.length })}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
        {reports.length === 0 && (
          <p className="text-muted-foreground text-center py-12">{t("reports.empty")}</p>
        )}
      </div>
    </div>
  );
}
