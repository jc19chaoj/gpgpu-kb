"use client";

import { useCallback, useEffect, useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { listPapers, listSources, searchPapers } from "@/lib/api";
import { PaperListResponse, Source } from "@/lib/types";
import { PaperCard } from "@/components/paper-card";
import { SearchBar } from "@/components/search-bar";
import { SourceFilter } from "@/components/source-filter";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowDown, ArrowUp } from "lucide-react";
import { useT } from "@/lib/i18n/provider";
import type { TranslationKey } from "@/lib/i18n/translations";

function BrowseContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const query = searchParams.get("q") || undefined;
  const typeFilter = searchParams.get("type") || "";
  // Keep the raw URL string as the canonical dep — it's a primitive, so
  // useCallback's Object.is comparison is stable across renders. The
  // derived array is recomputed locally where it's used.
  const sourceParam = searchParams.get("source") || "";
  const selectedSources = sourceParam.split(",").filter(Boolean);
  const t = useT();

  const [data, setData] = useState<PaperListResponse | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState("total_score");
  const [sortDir, setSortDir] = useState("desc");

  // Load the source list once (independent of query / filters).
  useEffect(() => {
    listSources()
      .then((r) => setSources(r.sources))
      .catch(() => setSources([]));
  }, []);

  const updateParams = useCallback(
    (next: { type?: string; source?: string[] }) => {
      const sp = new URLSearchParams(searchParams.toString());
      if ("type" in next) {
        if (next.type) sp.set("type", next.type);
        else sp.delete("type");
      }
      if ("source" in next) {
        if (next.source && next.source.length > 0) {
          sp.set("source", next.source.join(","));
        } else {
          sp.delete("source");
        }
      }
      const qs = sp.toString();
      router.replace(qs ? `/?${qs}` : "/");
    },
    [router, searchParams],
  );

  const onTypeChange = (newType: string) => {
    // Decision 5: drop selected source names whose type no longer matches.
    const validNames = newType
      ? selectedSources.filter((name) => {
          const s = sources.find((x) => x.name === name);
          return s ? s.type === newType : true; // unknown source: keep until /api/sources fully resolves
        })
      : selectedSources;
    updateParams({ type: newType, source: validNames });
    setPage(1);
  };

  const onSourcesChange = (names: string[]) => {
    updateParams({ source: names });
    setPage(1);
  };

  // Fetch on any param change. Inlined into useEffect (rather than wrapping
  // in useCallback) because `sourceParam` is derived from
  // `searchParams.get(...)` on every render — React Compiler can't prove
  // that's referentially stable, so the useCallback shape would trip the
  // `react-hooks/preserve-manual-memoization` rule.
  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    (async () => {
      try {
        let res: PaperListResponse;
        if (query) {
          // Search mode ignores type / source filters today (parity with the
          // existing pre-source-filter behavior); SourceFilter is hidden below.
          res = await searchPapers(query, { page, sort_by: sortBy, sort_dir: sortDir });
        } else {
          const names = sourceParam.split(",").filter(Boolean);
          res = await listPapers({
            page,
            source_type: typeFilter || undefined,
            source_name: names.length > 0 ? names : undefined,
            sort_by: sortBy,
            sort_dir: sortDir,
          });
        }
        if (!cancelled) setData(res);
      } catch {
        if (!cancelled) setData(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [page, sortBy, sortDir, typeFilter, sourceParam, query]);

  const TYPE_FILTERS: { value: string; labelKey: TranslationKey }[] = [
    { value: "", labelKey: "browse.filter.all" },
    { value: "paper", labelKey: "browse.filter.papers" },
    { value: "blog", labelKey: "browse.filter.blogs" },
    { value: "project", labelKey: "browse.filter.projects" },
    { value: "talk", labelKey: "browse.filter.talks" },
  ];

  const SORT_OPTIONS: { value: string; labelKey: TranslationKey }[] = [
    { value: "total_score", labelKey: "browse.sort.score" },
    { value: "published_date", labelKey: "browse.sort.date" },
  ];

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
                onClick={() => onTypeChange(f.value)}
                data-testid={`type-filter-${f.value || "all"}`}
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

        {/* Source filter only renders in non-query (browse) mode; search mode
            ignores type/source filters today and the UI hides them to avoid
            misleading the user. */}
        {!query && sources.length > 0 && (
          <SourceFilter
            sources={sources}
            selected={selectedSources}
            onChange={onSourcesChange}
            typeFilter={typeFilter}
          />
        )}
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
