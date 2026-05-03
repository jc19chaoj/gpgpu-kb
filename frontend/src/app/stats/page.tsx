"use client";

import { useEffect, useState } from "react";
import { getStats } from "@/lib/api";
import { Stats } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { BookOpen, CheckCircle, Star } from "lucide-react";
import Link from "next/link";
import { useT } from "@/lib/i18n/provider";
import type { TranslationKey } from "@/lib/i18n/translations";

const TYPE_LABEL_KEYS: Record<string, TranslationKey> = {
  paper: "stats.byType.paper",
  blog: "stats.byType.blog",
  project: "stats.byType.project",
  talk: "stats.byType.talk",
};

export default function StatsPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const t = useT();

  useEffect(() => {
    getStats().then(setStats).finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto p-4 sm:p-6 space-y-4">
        <Skeleton className="h-32 w-full bg-card" />
        <Skeleton className="h-48 w-full bg-card" />
      </div>
    );
  }

  if (!stats) return null;

  return (
    <div className="max-w-3xl mx-auto p-4 sm:p-6">
      <h1 className="text-base sm:text-lg font-semibold mb-4">{t("stats.title")}</h1>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <Card className="bg-card border-border">
          <CardContent className="p-4 text-center">
            <BookOpen className="h-5 w-5 text-muted-foreground mx-auto mb-1" />
            <div className="text-2xl font-bold">{stats.total_papers}</div>
            <div className="text-xs text-muted-foreground">{t("stats.totalItems")}</div>
          </CardContent>
        </Card>
        <Card className="bg-card border-border">
          <CardContent className="p-4 text-center">
            <CheckCircle className="h-5 w-5 text-primary mx-auto mb-1" />
            <div className="text-2xl font-bold">{stats.processed}</div>
            <div className="text-xs text-muted-foreground">{t("stats.processed")}</div>
          </CardContent>
        </Card>
        {Object.entries(stats.by_type).map(([type, count]) => {
          const labelKey = TYPE_LABEL_KEYS[type];
          return (
            <Card key={type} className="bg-card border-border">
              <CardContent className="p-4 text-center">
                <div className="text-2xl font-bold">{count}</div>
                <div className="text-xs text-muted-foreground capitalize">
                  {labelKey ? t(labelKey) : `${type}s`}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Card className="bg-card border-border mb-6">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Star className="h-4 w-4 text-amber-500" />
            {t("stats.topImpact")}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {stats.top_impact.map((p) => (
              <Link key={p.id} href={`/paper/${p.id}`}>
                <div className="flex items-center justify-between text-sm hover:text-primary transition-colors">
                  <span className="truncate flex-1">{p.title}</span>
                  <Badge className="ml-2 shrink-0 bg-primary/15 text-primary border border-primary/30 text-xs">
                    {p.impact_score.toFixed(1)}
                  </Badge>
                </div>
              </Link>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
