"use client";

import { useEffect, useState, useCallback, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { listPapers, searchPapers } from "@/lib/api";
import { PaperListResponse } from "@/lib/types";
import { PaperCard } from "@/components/paper-card";
import { SearchBar } from "@/components/search-bar";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowDown, ArrowUp } from "lucide-react";
import { useT } from "@/lib/i18n/provider";
import type { TranslationKey } from "@/lib/i18n/translations";

const SORT_OPTIONS: { value: string; labelKey: TranslationKey }[] = [
  { value: "total_score", labelKey: "browse.sort.score" },
  { value: "published_date", labelKey: "browse.sort.date" },
];

const TYPE_FILTERS: { value: string; labelKey: TranslationKey }[] = [
  { value: "", labelKey: "browse.filter.all" },
  { value: "paper", labelKey: "browse.filter.papers" },
  { value: "blog", labelKey: "browse.filter.blogs" },
  { value: "project", labelKey: "browse.filter.projects" },
  { value: "talk", labelKey: "browse.filter.talks" },
];

function BrowseContent() {
  const searchParams = useSearchParams();
  const query = searchParams.get("q") || undefined;
  const t = useT();

  const [data, setData] = useState<PaperListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState("total_score");
  const [sortDir, setSortDir] = useState("desc");
  const [typeFilter, setTypeFilter] = useState("");

  const fetchPapers = useCallback(async () => {
    setLoading(true);
    try {
      let res: PaperListResponse;
      if (query) {
        res = await searchPapers(query, { page, sort_by: sortBy, sort_dir: sortDir });
      } else {
        res = await listPapers({
          page,
          source_type: typeFilter || undefined,
          sort_by: sortBy,
          sort_dir: sortDir,
        });
      }
      setData(res);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [page, sortBy, sortDir, typeFilter, query]);

  // Standard data-fetch-on-params pattern. React 19's set-state-in-effect rule
  // flags this; the canonical fix is React Query / SWR, which is out of scope here.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { fetchPapers(); }, [fetchPapers]);

  return (
    <div className="max-w-4xl mx-auto p-4 sm:p-6">
      <div className="space-y-4 mb-6">
        <div className="flex items-baseline gap-3 flex-wrap">
          <h1 className="text-base sm:text-lg font-semibold truncate">
            {query ? `${t("browse.search")} "${query}"` : t("browse.title")}
          </h1>
          {data && (
            <span className="text-xs sm:text-sm text-muted-foreground">
              {t("browse.items", { count: data.total })}
            </span>
          )}
        </div>

        <SearchBar />

        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex gap-1">
            {TYPE_FILTERS.map((f) => (
              <Badge
                key={f.value}
                variant={typeFilter === f.value ? "default" : "outline"}
                className="cursor-pointer text-xs"
                onClick={() => { setTypeFilter(f.value); setPage(1); }}
              >
                {t(f.labelKey)}
              </Badge>
            ))}
          </div>

          <div className="h-4 w-px bg-border" />

          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>{t("browse.sort")}</span>
            {SORT_OPTIONS.map((opt) => (
              <Button
                key={opt.value}
                variant={sortBy === opt.value ? "secondary" : "ghost"}
                size="sm"
                className="h-7 text-xs px-2"
                onClick={() => {
                  if (sortBy === opt.value) {
                    setSortDir((d) => (d === "desc" ? "asc" : "desc"));
                  } else {
                    setSortBy(opt.value);
                    setSortDir("desc");
                  }
                  setPage(1);
                }}
              >
                {t(opt.labelKey)}
                {sortBy === opt.value && (
                  sortDir === "desc" ? <ArrowDown className="ml-1 h-3 w-3" /> : <ArrowUp className="ml-1 h-3 w-3" />
                )}
              </Button>
            ))}
          </div>
        </div>
      </div>

      {loading && (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-32 w-full bg-card" />
          ))}
        </div>
      )}

      {!loading && data && (
        <>
          <div className="space-y-3">
            {data.papers.map((paper) => (
              <PaperCard key={paper.id} paper={paper} />
            ))}
          </div>

          {data.total > data.page_size && (
            <div className="flex items-center justify-center gap-2 mt-6">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                {t("browse.pagination.previous")}
              </Button>
              <span className="text-sm text-muted-foreground">
                {t("browse.pagination.page", {
                  page: data.page,
                  total: Math.ceil(data.total / data.page_size),
                })}
              </span>
              <Button variant="outline" size="sm" disabled={page >= Math.ceil(data.total / data.page_size)} onClick={() => setPage((p) => p + 1)}>
                {t("browse.pagination.next")}
              </Button>
            </div>
          )}
        </>
      )}

      {!loading && data?.papers.length === 0 && (
        <div className="text-center py-16 text-muted-foreground">
          <p className="text-lg mb-2">{t("browse.empty.title")}</p>
          <p className="text-sm">{t("browse.empty.hint")}</p>
        </div>
      )}
    </div>
  );
}

export default function BrowsePage() {
  return (
    <Suspense fallback={<div className="max-w-4xl mx-auto p-4 sm:p-6 space-y-3">{Array.from({length:5}).map((_,i)=><Skeleton key={i} className="h-32 w-full bg-card"/>)}</div>}>
      <BrowseContent />
    </Suspense>
  );
}
