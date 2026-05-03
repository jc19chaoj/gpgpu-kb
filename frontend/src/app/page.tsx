"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
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
  // Read URL only as the *initial* hydration source. We can't use
  // `router.push("/?type=...")` here because Next.js 16.2.x has a known
  // regression that ignores same-pathname-different-search-params navigations
  // when a prefetched route cache entry exists for that path
  // (vercel/next.js#92187). Workaround: keep filter state in React, drive
  // the address bar via `window.history.replaceState` so URLs remain
  // shareable, and let `useSearchParams()` handle only the initial read.
  const searchParams = useSearchParams();
  const query = searchParams.get("q") || undefined;
  const t = useT();

  // Initial values from URL — only used on first render. Subsequent updates
  // go through React state and `window.history.replaceState` to dodge the
  // Next 16.2 router cache bug.
  const [typeFilter, setTypeFilter] = useState<string>(
    () => searchParams.get("type") || "",
  );
  const [selectedSources, setSelectedSources] = useState<string[]>(
    () => (searchParams.get("source") || "").split(",").filter(Boolean),
  );

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

  // Sync browser URL whenever the local filter state changes. We use
  // `window.history.replaceState` directly to avoid the Next 16.2 router
  // cache regression (see comment at top of BrowseContent). The query (`?q=`)
  // and any unrelated search params are preserved.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const sp = new URLSearchParams(window.location.search);
    if (typeFilter) sp.set("type", typeFilter);
    else sp.delete("type");
    if (selectedSources.length > 0) sp.set("source", selectedSources.join(","));
    else sp.delete("source");
    const qs = sp.toString();
    const next = qs ? `${window.location.pathname}?${qs}` : window.location.pathname;
    if (next !== window.location.pathname + window.location.search) {
      window.history.replaceState({}, "", next);
    }
  }, [typeFilter, selectedSources]);

  const onTypeChange = (newType: string) => {
    // Decision 5: drop selected source names whose type no longer matches.
    const validNames = newType
      ? selectedSources.filter((name) => {
          const s = sources.find((x) => x.name === name);
          return s ? s.type === newType : true; // unknown source: keep until /api/sources fully resolves
        })
      : selectedSources;
    setTypeFilter(newType);
    setSelectedSources(validNames);
    setPage(1);
  };

  const onSourcesChange = (names: string[]) => {
    setSelectedSources(names);
    setPage(1);
  };

  // Fetch on any state change. Inlined into useEffect (no useCallback) so
  // React Compiler doesn't trip on the array dep `selectedSources` — using
  // `.join(",")` collapses it to a primitive that Object.is can compare.
  const sourceKey = selectedSources.join(",");
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
          const names = sourceKey ? sourceKey.split(",") : [];
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
  }, [page, sortBy, sortDir, typeFilter, sourceKey, query]);

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
