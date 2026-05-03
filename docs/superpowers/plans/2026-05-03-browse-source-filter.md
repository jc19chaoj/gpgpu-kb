# Browse 页 Source 名称过滤 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a multi-select `source_name` tag filter to the Browse page, grouped by `source_type` and AND-combined with the existing type filter; selection persists in URL (`?type=...&source=arxiv,openai`).

**Architecture:** New backend endpoint `GET /api/sources` returns distinct `(name, type, count)` tuples for `is_processed=1` rows; `GET /api/papers` gains a `source_name` query parameter accepting comma-separated values that map to a SQL `IN (...)` filter. Frontend adds a `SourceFilter` component rendering 4 collapsible groups (paper / blog / project / talk); when the existing type filter is active, only that group renders and selected names with mismatched types are silently dropped. URL state replaces component state for both `type` and `source` so links are shareable.

**Tech Stack:** FastAPI / SQLAlchemy 2 / Pydantic 2 (backend); Next.js 16 App Router / React 19 / Tailwind v4 / shadcn/ui Badge (frontend); pytest (backend tests); Playwright (frontend e2e).

**Reference spec:** [`docs/superpowers/specs/2026-05-03-browse-source-filter-design.md`](../specs/2026-05-03-browse-source-filter-design.md)

---

## Task 1: Backend schemas — `SourceItem` and `SourcesOut`

**Files:**
- Modify: `backend/kb/schemas.py` (append at end of file, after `SearchRequest`)

- [ ] **Step 1.1: Add the two Pydantic models**

Append to `backend/kb/schemas.py`:

```python
class SourceItem(BaseModel):
    """One distinct (source_name, source_type) bucket with its row count.

    Surfaces what `source_name` values exist in the knowledge base so the
    frontend can render filter tags without hardcoding the RSS / sitemap
    source list. Only `is_processed=1` rows are counted.
    """
    name: str
    type: str  # mirrors SourceType enum value: "paper" | "blog" | "project" | "talk"
    count: int


class SourcesOut(BaseModel):
    sources: list[SourceItem]
```

- [ ] **Step 1.2: Verify import / typing**

Run: `cd backend && python -c "from kb.schemas import SourceItem, SourcesOut; print(SourceItem(name='arxiv', type='paper', count=1).model_dump())"`
Expected: `{'name': 'arxiv', 'type': 'paper', 'count': 1}` printed, no traceback.

- [ ] **Step 1.3: Commit**

```bash
git add backend/kb/schemas.py
git commit -m "feat(backend): add SourceItem and SourcesOut schemas"
```

---

## Task 2: Backend — `GET /api/sources` endpoint (TDD)

**Files:**
- Test: `backend/tests/test_api_smoke.py` (append; new section header `# ─── Source list endpoint ───`)
- Modify: `backend/kb/main.py` (import schemas; add route after `/api/stats` block)

- [ ] **Step 2.1: Write the failing tests**

Append to `backend/tests/test_api_smoke.py`:

```python
# ─── Source list endpoint (browse page tag filter) ────────────────

def _seed_source_papers() -> None:
    """Insert 5 papers across 3 source_names so /api/sources can group/count.

    Layout: 2 arxiv (paper, processed=1), 1 OpenAI (blog, processed=1),
    1 SemiAnalysis (blog, processed=2 → low quality, must be hidden),
    1 github (project, processed=0 → pending, must be hidden).
    """
    import datetime
    from kb.database import SessionLocal
    from kb.models import Paper, SourceType

    db = SessionLocal()
    try:
        for i, (sname, stype, processed) in enumerate([
            ("arxiv", SourceType.PAPER, 1),
            ("arxiv", SourceType.PAPER, 1),
            ("OpenAI", SourceType.BLOG, 1),
            ("SemiAnalysis", SourceType.BLOG, 2),
            ("trending-repo", SourceType.PROJECT, 0),
        ]):
            db.add(Paper(
                title=f"src-{i}",
                abstract="",
                summary="s" if processed else "",
                authors=[],
                organizations=[],
                source_type=stype,
                source_name=sname,
                url=f"https://example.test/sources/{i}",
                published_date=datetime.datetime(2026, 4, 25, tzinfo=datetime.UTC),
                is_processed=processed,
                quality_score=8.0 if processed == 1 else 0.0,
                relevance_score=8.0 if processed == 1 else 0.0,
            ))
        db.commit()
    finally:
        db.close()


def test_list_sources_returns_distinct_names_with_counts(client):
    _seed_source_papers()
    r = client.get("/api/sources")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "sources" in body
    by_name = {s["name"]: s for s in body["sources"]}
    # arxiv: 2 active rows, OpenAI: 1 active row.
    assert by_name["arxiv"]["count"] == 2
    assert by_name["arxiv"]["type"] == "paper"
    assert by_name["OpenAI"]["count"] == 1
    assert by_name["OpenAI"]["type"] == "blog"


def test_list_sources_excludes_low_quality_and_pending(client):
    _seed_source_papers()
    r = client.get("/api/sources")
    body = r.json()
    names = {s["name"] for s in body["sources"]}
    assert "SemiAnalysis" not in names  # is_processed=2
    assert "trending-repo" not in names  # is_processed=0


def test_list_sources_orders_by_count_desc(client):
    _seed_source_papers()
    r = client.get("/api/sources")
    body = r.json()
    counts = [s["count"] for s in body["sources"]]
    assert counts == sorted(counts, reverse=True), body
```

- [ ] **Step 2.2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_api_smoke.py::test_list_sources_returns_distinct_names_with_counts tests/test_api_smoke.py::test_list_sources_excludes_low_quality_and_pending tests/test_api_smoke.py::test_list_sources_orders_by_count_desc -x -v`
Expected: All 3 FAIL with 404 / `assert 404 == 200` (route doesn't exist).

- [ ] **Step 2.3: Implement the endpoint**

In `backend/kb/main.py`:

1. Update the import block (line 25-31) to include the new schemas:

```python
from kb.schemas import (
    PaperOut,
    PaperListOut,
    DailyReportOut,
    ChatRequest,
    ChatResponse,
    SourceItem,
    SourcesOut,
)
```

2. Add the route. Find the existing `/api/stats` route (search for `def get_stats` in main.py) and add this **right before it**:

```python
@app.get("/api/sources", response_model=SourcesOut)
def list_sources(db: Session = Depends(get_db)):
    """Distinct source_name buckets with row counts for the browse-page filter.

    Only counts is_processed=1 rows so low-quality / pending entries don't
    appear as filter tags. Ordered by count desc so the busiest sources
    surface first in the UI.
    """
    rows = (
        db.query(Paper.source_name, Paper.source_type, func.count(Paper.id))
          .filter(Paper.is_processed == 1)
          .group_by(Paper.source_name, Paper.source_type)
          .order_by(func.count(Paper.id).desc())
          .all()
    )
    items: list[SourceItem] = []
    for name, stype, cnt in rows:
        if not name:
            continue
        type_str = stype.value if hasattr(stype, "value") else str(stype)
        items.append(SourceItem(name=name, type=type_str, count=cnt))
    return SourcesOut(sources=items)
```

(`func` is already imported at the top of `main.py`.)

- [ ] **Step 2.4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_api_smoke.py::test_list_sources_returns_distinct_names_with_counts tests/test_api_smoke.py::test_list_sources_excludes_low_quality_and_pending tests/test_api_smoke.py::test_list_sources_orders_by_count_desc -x -v`
Expected: All 3 PASS.

- [ ] **Step 2.5: Commit**

```bash
git add backend/kb/main.py backend/tests/test_api_smoke.py
git commit -m "feat(backend): add GET /api/sources for browse-page filter tags"
```

---

## Task 3: Backend — `source_name` query param on `/api/papers` (TDD)

**Files:**
- Test: `backend/tests/test_api_smoke.py` (append after Task 2's tests)
- Modify: `backend/kb/main.py` (`list_papers` signature + filter clause)

- [ ] **Step 3.1: Write the failing tests**

Append to `backend/tests/test_api_smoke.py`:

```python
def test_list_papers_filters_by_single_source_name(client):
    _seed_source_papers()
    r = client.get("/api/papers", params={"source_name": "arxiv"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    assert all(p["source_name"] == "arxiv" for p in body["papers"])


def test_list_papers_filters_by_multiple_source_names(client):
    _seed_source_papers()
    r = client.get("/api/papers", params={"source_name": "arxiv,OpenAI"})
    assert r.status_code == 200, r.text
    body = r.json()
    # 2 arxiv + 1 OpenAI = 3 active rows.
    assert body["total"] == 3
    names = {p["source_name"] for p in body["papers"]}
    assert names == {"arxiv", "OpenAI"}


def test_list_papers_source_name_empty_value_is_ignored(client):
    """Defensive: ?source_name= (empty string) must NOT filter to zero rows.
    The frontend may emit an empty value during URL rewrite races; this test
    locks in the 'empty == no filter' behavior."""
    _seed_source_papers()
    r = client.get("/api/papers", params={"source_name": ""})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] >= 3  # all active rows visible


def test_list_papers_source_name_combined_with_source_type(client):
    """AND combination with the existing source_type filter."""
    _seed_source_papers()
    r = client.get(
        "/api/papers",
        params={"source_type": "blog", "source_name": "arxiv,OpenAI"},
    )
    body = r.json()
    # arxiv is type=paper, so the AND should leave only OpenAI.
    assert body["total"] == 1
    assert body["papers"][0]["source_name"] == "OpenAI"
```

- [ ] **Step 3.2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_api_smoke.py::test_list_papers_filters_by_single_source_name tests/test_api_smoke.py::test_list_papers_filters_by_multiple_source_names tests/test_api_smoke.py::test_list_papers_source_name_empty_value_is_ignored tests/test_api_smoke.py::test_list_papers_source_name_combined_with_source_type -x -v`
Expected: First 2 FAIL (returns all 3 rows because filter is missing); empty-value passes; combined-filter also FAILS.

- [ ] **Step 3.3: Add the parameter and filter clause**

In `backend/kb/main.py`, modify `list_papers`:

1. Add `source_name` to the signature, right after `source_type`:

```python
@app.get("/api/papers", response_model=PaperListOut)
def list_papers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source_type: str | None = None,
    source_name: str | None = Query(None, max_length=500),
    sort_by: str = Query(
        "total_score",
        pattern="^(published_date|impact_score|originality_score|quality_score|relevance_score|total_score|ingested_date)$",
    ),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    include_low_quality: bool = Query(False),
    db: Session = Depends(get_db),
):
```

2. Add the filter clause **right after** the existing `source_type` filter (search for `q = q.filter(Paper.source_type == source_type)`). Place this immediately below it:

```python
    if source_name:
        # Comma-separated multi-select: ?source_name=arxiv,OpenAI → SQL IN (...).
        # 50-item cap is defensive; the UI today exposes ~14 distinct sources.
        names = [n.strip() for n in source_name.split(",") if n.strip()][:50]
        if names:
            q = q.filter(Paper.source_name.in_(names))
```

- [ ] **Step 3.4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_api_smoke.py -x -v -k "source_name or list_sources"`
Expected: All 7 source-related tests PASS (3 from Task 2 + 4 new).

- [ ] **Step 3.5: Run the full backend suite to catch regressions**

Run: `cd backend && python -m pytest tests/ -x -q`
Expected: All tests PASS (203 + 7 = 210, or whatever the current count is + 7).

- [ ] **Step 3.6: Commit**

```bash
git add backend/kb/main.py backend/tests/test_api_smoke.py
git commit -m "feat(backend): filter /api/papers by source_name (comma-separated multi-select)"
```

---

## Task 4: Frontend types — `Source` and `SourcesResponse`

**Files:**
- Modify: `frontend/src/lib/types.ts` (append after `Stats` interface)

- [ ] **Step 4.1: Add the two interfaces**

Append to `frontend/src/lib/types.ts`:

```ts
// Distinct source_name bucket from GET /api/sources. Surfaces what source
// values exist in the knowledge base so the browse page can render filter
// tags without hardcoding the (growing) RSS / sitemap source list.
export interface Source {
  name: string;
  type: string; // "paper" | "blog" | "project" | "talk"
  count: number;
}

export interface SourcesResponse {
  sources: Source[];
}
```

- [ ] **Step 4.2: Verify no TS errors**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors.

- [ ] **Step 4.3: Commit**

```bash
git add frontend/src/lib/types.ts
git commit -m "feat(frontend): add Source and SourcesResponse types"
```

---

## Task 5: Frontend API client — `listSources` + `listPapers` `source_name` param

**Files:**
- Modify: `frontend/src/lib/api.ts` (`listPapers` signature; new `listSources`)

- [ ] **Step 5.1: Update imports**

In `frontend/src/lib/api.ts`, expand the import on line 2-12 to include `SourcesResponse`:

```ts
import {
  Paper,
  PaperListResponse,
  DailyReport,
  ChatRequest,
  ChatResponse,
  ChatStreamEvent,
  DailyStatus,
  DailyStreamEvent,
  SourcesResponse,
  Stats,
} from "./types";
```

- [ ] **Step 5.2: Extend `listPapers` to accept `source_name`**

Replace the existing `listPapers` (currently `frontend/src/lib/api.ts:29-39`) with:

```ts
export async function listPapers(params?: {
  page?: number;
  page_size?: number;
  source_type?: string;
  source_name?: string[]; // multi-select, joined with comma before sending
  sort_by?: string;
  sort_dir?: string;
}): Promise<PaperListResponse> {
  const sp = new URLSearchParams();
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v === undefined) return;
      if (k === "source_name") {
        const names = v as string[];
        if (names.length > 0) sp.set("source_name", names.join(","));
        return;
      }
      sp.set(k, String(v));
    });
  }
  return fetchJSON<PaperListResponse>(`/api/papers?${sp.toString()}`);
}
```

- [ ] **Step 5.3: Add `listSources`**

Add this function right after `listPapers`:

```ts
export async function listSources(): Promise<SourcesResponse> {
  return fetchJSON<SourcesResponse>(`/api/sources`);
}
```

- [ ] **Step 5.4: Verify types + lint**

Run: `cd frontend && npx tsc --noEmit && npx eslint src/lib/api.ts`
Expected: No errors.

- [ ] **Step 5.5: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat(frontend): add listSources + source_name param on listPapers"
```

---

## Task 6: i18n keys for SourceFilter

**Files:**
- Modify: `frontend/src/lib/i18n/translations.ts` (English + Chinese blocks)

- [ ] **Step 6.1: Add English keys**

In `frontend/src/lib/i18n/translations.ts`, find the `// Browse` section (around line 50-66) and add these keys right after `"browse.filter.talks"` and before `"browse.empty.title"`:

```ts
    "browse.filter.sources": "Sources",
    "browse.filter.sources.expand": "Expand group",
    "browse.filter.sources.collapse": "Collapse group",
```

- [ ] **Step 6.2: Add Chinese keys**

In the same file, find the matching position in the `zh:` block (after `"browse.filter.talks": "演讲"`) and add:

```ts
    "browse.filter.sources": "来源",
    "browse.filter.sources.expand": "展开分组",
    "browse.filter.sources.collapse": "折叠分组",
```

- [ ] **Step 6.3: Verify TS picks up the new keys**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors. (`TranslationKey` is `keyof typeof translations.en` — adding to `en` automatically widens it.)

- [ ] **Step 6.4: Commit**

```bash
git add frontend/src/lib/i18n/translations.ts
git commit -m "i18n(frontend): add source-filter translation keys"
```

---

## Task 7: SourceFilter component

**Files:**
- Create: `frontend/src/components/source-filter.tsx`

- [ ] **Step 7.1: Create the component file**

Write to `frontend/src/components/source-filter.tsx`:

```tsx
"use client";

import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { Source } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { useT } from "@/lib/i18n/provider";
import type { TranslationKey } from "@/lib/i18n/translations";

const GROUP_ORDER = ["paper", "blog", "project", "talk"] as const;
type GroupType = (typeof GROUP_ORDER)[number];

const GROUP_LABEL_KEY: Record<GroupType, TranslationKey> = {
  paper: "browse.filter.papers",
  blog: "browse.filter.blogs",
  project: "browse.filter.projects",
  talk: "browse.filter.talks",
};

export function SourceFilter({
  sources,
  selected,
  onChange,
  typeFilter,
}: {
  sources: Source[];
  selected: string[];
  onChange: (names: string[]) => void;
  typeFilter: string; // "" = All
}) {
  const t = useT();
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const grouped = GROUP_ORDER.map((type) => ({
    type,
    items: sources.filter((s) => s.type === type),
  })).filter((g) => g.items.length > 0);

  // Decision 5: when type filter is active, render only that group.
  const visibleGroups = typeFilter
    ? grouped.filter((g) => g.type === typeFilter)
    : grouped;

  if (visibleGroups.length === 0) return null;

  const toggle = (name: string) => {
    onChange(
      selected.includes(name)
        ? selected.filter((n) => n !== name)
        : [...selected, name],
    );
  };

  return (
    <div className="space-y-2" data-testid="source-filter">
      {visibleGroups.map((group) => {
        const isCollapsed = collapsed[group.type] ?? false;
        const labelKey = GROUP_LABEL_KEY[group.type];
        const ariaKey: TranslationKey = isCollapsed
          ? "browse.filter.sources.expand"
          : "browse.filter.sources.collapse";
        return (
          <div key={group.type} className="space-y-1">
            <button
              type="button"
              onClick={() =>
                setCollapsed({ ...collapsed, [group.type]: !isCollapsed })
              }
              aria-label={t(ariaKey)}
              aria-expanded={!isCollapsed}
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              <ChevronRight
                className={`h-3 w-3 transition-transform ${
                  isCollapsed ? "" : "rotate-90"
                }`}
              />
              {t(labelKey)}
              <span className="text-[10px] opacity-60">
                ({group.items.length})
              </span>
            </button>
            {!isCollapsed && (
              <div className="flex flex-wrap gap-1 pl-4">
                {group.items.map((s) => (
                  <Badge
                    key={s.name}
                    variant={selected.includes(s.name) ? "default" : "outline"}
                    className="cursor-pointer text-[10px] gap-1"
                    onClick={() => toggle(s.name)}
                    data-testid={`source-tag-${s.name}`}
                    data-selected={selected.includes(s.name) ? "true" : "false"}
                  >
                    {s.name}
                    <span className="opacity-60">·{s.count}</span>
                  </Badge>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
```

`data-testid` attributes are deliberate hooks for the e2e tests in Task 9.

- [ ] **Step 7.2: Verify types + lint**

Run: `cd frontend && npx tsc --noEmit && npx eslint src/components/source-filter.tsx`
Expected: No errors.

- [ ] **Step 7.3: Commit**

```bash
git add frontend/src/components/source-filter.tsx
git commit -m "feat(frontend): SourceFilter component with collapsible groups"
```

---

## Task 8: Browse page URL state + SourceFilter integration

**Files:**
- Modify: `frontend/src/app/page.tsx` (entire `BrowseContent` body — significant refactor)

- [ ] **Step 8.1: Extend imports**

At the top of `frontend/src/app/page.tsx`, replace the existing imports block:

```tsx
"use client";

import { useEffect, useState, useCallback, Suspense } from "react";
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
```

- [ ] **Step 8.2: Replace `BrowseContent` body**

Replace the entire `BrowseContent` function (lines 29-171 of the current file) with:

```tsx
function BrowseContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const query = searchParams.get("q") || undefined;
  const typeFilter = searchParams.get("type") || "";
  const selectedSources = (searchParams.get("source") || "")
    .split(",")
    .filter(Boolean);
  const t = useT();

  const [data, setData] = useState<PaperListResponse | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState("total_score");
  const [sortDir, setSortDir] = useState("desc");

  // Load the source list once (independent of query / filters).
  // eslint-disable-next-line react-hooks/set-state-in-effect
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

  const fetchPapers = useCallback(async () => {
    setLoading(true);
    try {
      let res: PaperListResponse;
      if (query) {
        // Search mode ignores type / source filters today (parity with the
        // existing pre-source-filter behavior); SourceFilter is hidden below.
        res = await searchPapers(query, { page, sort_by: sortBy, sort_dir: sortDir });
      } else {
        res = await listPapers({
          page,
          source_type: typeFilter || undefined,
          source_name: selectedSources.length > 0 ? selectedSources : undefined,
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
  }, [page, sortBy, sortDir, typeFilter, selectedSources.join(","), query]);

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { fetchPapers(); }, [fetchPapers]);

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
```

Note: `selectedSources.join(",")` is the dependency key in `useCallback` — it converts the array to a primitive so React's `Object.is` comparison works.

- [ ] **Step 8.3: Verify types + lint**

Run: `cd frontend && npx tsc --noEmit && npx eslint src/app/page.tsx`
Expected: No errors. Existing `react-hooks/set-state-in-effect` disable comments are preserved; one new disable for the sources-load `useEffect`.

- [ ] **Step 8.4: Manual smoke (sanity-check before e2e)**

Run: `cd frontend && npm run dev` (in one shell), `cd backend && ./run_api.sh` (in another).
Open `http://localhost:3000/`. With at least one ingested paper:
1. SourceFilter row should render below the type filter.
2. Click an `arxiv` tag → URL gains `?source=arxiv`, list filters to arxiv only.
3. Click `Papers` type tag → only the Papers source group remains visible.
4. Click an existing `OpenAI` tag (blog), then click `Papers` type → URL `source` is cleared (because OpenAI is a blog, not paper).
5. Refresh with `?source=arxiv` in URL → tag is selected on load.

Stop both dev servers when done.

- [ ] **Step 8.5: Commit**

```bash
git add frontend/src/app/page.tsx
git commit -m "feat(frontend): URL-driven source filter on browse page"
```

---

## Task 9: Playwright e2e — source filter toggle

**Files:**
- Modify: `frontend/tests/e2e/browse.spec.ts` (append two test cases at the end)

- [ ] **Step 9.1: Inspect existing browse spec to match style**

Run: `cd frontend && head -80 tests/e2e/browse.spec.ts`
Expected: file shows the project's mock pattern (`page.route('/api/papers*', ...)` etc.). Note the existing route handler structure; the new tests will reuse the same mocking approach.

- [ ] **Step 9.2: Append the two e2e tests**

Append to `frontend/tests/e2e/browse.spec.ts` (use the existing imports from the top of the file; if `test, expect` are already imported there, do not redeclare):

```ts
test("source filter: clicking a tag updates URL and filters list", async ({ page }) => {
  // Mock /api/sources with 2 sources of different types.
  await page.route("**/api/sources", async (route) => {
    await route.fulfill({
      json: {
        sources: [
          { name: "arxiv", type: "paper", count: 10 },
          { name: "SemiAnalysis", type: "blog", count: 5 },
        ],
      },
    });
  });

  // Mock /api/papers — return arxiv-only list when source_name=arxiv,
  // otherwise return both. We assert by inspecting the URL the page requested.
  let lastRequestedSourceName: string | null = null;
  await page.route("**/api/papers*", async (route) => {
    const url = new URL(route.request().url());
    lastRequestedSourceName = url.searchParams.get("source_name");
    const arxivPaper = {
      id: 1, title: "ArXiv paper", authors: ["A"], organizations: [],
      abstract: "", url: "https://arxiv.org/abs/1", pdf_url: "",
      source_type: "paper", source_name: "arxiv",
      published_date: "2026-04-25T00:00:00Z", ingested_date: "2026-04-25T00:00:00Z",
      categories: [], venue: "", citation_count: 0, summary: "S",
      originality_score: 8, impact_score: 8, impact_rationale: "",
      quality_score: 8, relevance_score: 8, score_rationale: "",
    };
    const blogPaper = { ...arxivPaper, id: 2, title: "SemiAnalysis post", source_type: "blog", source_name: "SemiAnalysis" };
    const papers = lastRequestedSourceName === "arxiv" ? [arxivPaper] : [arxivPaper, blogPaper];
    await route.fulfill({
      json: { papers, total: papers.length, page: 1, page_size: 20 },
    });
  });

  await page.goto("/");
  await expect(page.getByTestId("source-filter")).toBeVisible();
  await expect(page.getByTestId("source-tag-arxiv")).toBeVisible();

  // Click the arxiv tag.
  await page.getByTestId("source-tag-arxiv").click();

  // URL gains ?source=arxiv.
  await expect(page).toHaveURL(/[?&]source=arxiv\b/);

  // Last /api/papers fetch carried source_name=arxiv.
  await expect.poll(() => lastRequestedSourceName).toBe("arxiv");

  // Tag is now in selected state.
  await expect(page.getByTestId("source-tag-arxiv")).toHaveAttribute(
    "data-selected",
    "true",
  );
});

test("source filter: switching type drops mismatched selected sources", async ({ page }) => {
  await page.route("**/api/sources", async (route) => {
    await route.fulfill({
      json: {
        sources: [
          { name: "arxiv", type: "paper", count: 10 },
          { name: "SemiAnalysis", type: "blog", count: 5 },
        ],
      },
    });
  });
  await page.route("**/api/papers*", async (route) => {
    await route.fulfill({
      json: { papers: [], total: 0, page: 1, page_size: 20 },
    });
  });

  // Pre-select the SemiAnalysis blog source via URL.
  await page.goto("/?source=SemiAnalysis");
  await expect(page.getByTestId("source-tag-SemiAnalysis")).toHaveAttribute(
    "data-selected",
    "true",
  );

  // Now click the Papers type filter — SemiAnalysis (a blog) must be dropped.
  await page.getByTestId("type-filter-paper").click();
  await expect(page).toHaveURL(/[?&]type=paper\b/);
  await expect(page).not.toHaveURL(/[?&]source=/);
});
```

- [ ] **Step 9.3: Run the new e2e tests**

Run: `cd frontend && npm run build && npx playwright test tests/e2e/browse.spec.ts --reporter=line`
Expected: All browse.spec tests PASS, including the two new ones.

(If you haven't installed playwright browsers yet: `npx playwright install chromium` once.)

- [ ] **Step 9.4: Commit**

```bash
git add frontend/tests/e2e/browse.spec.ts
git commit -m "test(frontend): e2e for source filter toggle and type cleanup"
```

---

## Task 10: Update CLAUDE.md docs

**Files:**
- Modify: `CLAUDE.md` (root) — add changelog entry, optionally update the architecture diagram comment
- Modify: `backend/CLAUDE.md` — add `/api/sources` row to the API table; add `source_name` to `list_papers` description; add changelog entry
- Modify: `frontend/CLAUDE.md` — add `SourceFilter` to the components list; document URL params; add changelog entry

- [ ] **Step 10.1: Append root CLAUDE.md changelog**

In `/home/robin/gpgpu-kb/CLAUDE.md`, locate the most recent entry in the "九、变更记录" table and add a new row beneath the latest one (use a timestamp later than the current latest — `backend/CLAUDE.md` and `frontend/CLAUDE.md` already carry `2026-05-03 22:34:43` for the daily-pipeline-endpoint refresh, so use **`2026-05-03 23:00:00`** here):

```markdown
| **2026-05-03 23:00:00** | **增量刷新** | **Browse 页 Source 名称过滤**。① **后端**：新端点 `GET /api/sources` 返回 `[{name, type, count}, ...]`（仅统计 `is_processed=1`，按 count desc）；`schemas.py` 新增 `SourceItem` / `SourcesOut`。`GET /api/papers` 增加 `source_name: str | None`（逗号分隔多值，cap 50 项 + max_length=500），`Paper.source_name.in_([...])` 过滤；与 `source_type` AND 组合；空字符串透明忽略。`/api/papers/search` 不动，保持搜索路径忽略 type/source 过滤的现状。② **前端**：`src/components/source-filter.tsx` 新组件——按 `source_type` 分 4 组（paper/blog/project/talk），每组可折叠，tag 渲染 `name · count` Badge；`typeFilter` 非空时只渲染对应组。Browse 页 (`src/app/page.tsx`) 把 `typeFilter` 与 `selectedSources` 从组件 state 迁到 URL（`?type=...&source=arxiv,openai`），切 type 时 silently drop 不匹配的 source（决策 5 自然推论）。`src/lib/types.ts` 新增 `Source` / `SourcesResponse`；`src/lib/api.ts::listPapers` 接受 `source_name?: string[]`；新增 `listSources()`。i18n 加 3 条 key（`browse.filter.sources` / `.expand` / `.collapse`）。query 模式（`?q=`）下 SourceFilter 不渲染。③ **测试**：`backend/tests/test_api_smoke.py` +7 例（`/api/sources` 3 例 + `/api/papers?source_name=` 4 例）；`frontend/tests/e2e/browse.spec.ts` +2 例（点 tag → URL 与列表更新；切 type=paper → blog source 被静默 drop）。④ **不影响**：DB schema / migration / chat / reports / stats / ingestion / processing 全部不动；既有 paper-card / paper-detail / search / 移动端响应式不变。 |
```

- [ ] **Step 10.2: Update backend CLAUDE.md**

In `/home/robin/gpgpu-kb/backend/CLAUDE.md`:

1. In section "三、对外接口" find the API table; add this row right before `/api/reports`:

```markdown
| `GET  /api/sources` | `list_sources` | 浏览页 source_name tag 过滤数据源：返回 `[{name, type, count}, ...]`（仅 `is_processed=1`，按 count desc），group by `(source_name, source_type)`。空 `source_name` 行被跳过。 |
```

2. In the same table, edit the `GET /api/papers` row to mention the new param. Find the line starting with `` | `GET  /api/papers` | `list_papers` |`` and append to its description: `；`source_name`（逗号分隔多值，与 `source_type` AND 组合）多源过滤`.

3. Append a new changelog row at the bottom of "十二、变更记录" with timestamp **`2026-05-03 23:00:00`** (must be later than the existing `22:34:43` daily-pipeline-endpoint entry):

```markdown
| **2026-05-03 23:00:00** | **增量刷新** | **Browse 页 source_name 过滤后端支持**。① 新端点 `GET /api/sources` (`kb/main.py::list_sources`) — group by `(source_name, source_type)` filtered to `is_processed=1`，按 count desc 返回 `SourceItem` 列表。② `kb/schemas.py` 新增 `SourceItem { name, type, count }` / `SourcesOut { sources: list[SourceItem] }`。③ `list_papers` 新增 `source_name: str \| None = Query(None, max_length=500)` 参数，逗号分隔多值（前 50 项），`Paper.source_name.in_([...])` 与 `source_type` AND 组合；空字符串透明忽略。④ `/api/papers/search` 与既有 chat / reports / stats / `/api/daily/*` 路径不动。⑤ 测试：`tests/test_api_smoke.py` +7 例（端点 happy path + 排序 + 排除 is_processed!=1 + single source + multi source + 空字符串忽略 + 与 source_type AND）；套件总计 +7（实际基线在 daily-pipeline-endpoint 增量后约 209，本轮后约 216 — 以本地实测 `pytest tests/ -q` 为准）。 |
```

- [ ] **Step 10.3: Update frontend CLAUDE.md**

In `/home/robin/gpgpu-kb/frontend/CLAUDE.md`:

1. In section "三、对外接口" find the API client table; add a row for `listSources` just after `searchPapers`:

```markdown
| `listSources()` | `GET /api/sources` | 浏览页 source_name tag 过滤数据源；返回 `[{name, type, count}, ...]`，前端按 `source_type` 分 4 组渲染 |
```

2. Edit the `listPapers` row to mention the new param: append to its description: `；`source_name?: string[]` 数组在前端 `.join(",")` 后发送，多选过滤`.

3. In section "六、目录结构", under `src/components/`, add a line for the new component:

```markdown
   │  ├─ source-filter.tsx  # Browse 页按 source_name 过滤的多选 tag 条（4 组按 source_type 分组、可折叠）
```

4. Append a new changelog row at the bottom of "十五、变更记录" with timestamp **`2026-05-03 23:00:00`** (must be later than the existing `22:34:43` themed-shell entry):

```markdown
| **2026-05-03 23:00:00** | **增量刷新** | **Browse 页 source_name 多选过滤**。① 新组件 `src/components/source-filter.tsx`：按 `source_type` 分 4 组（paper/blog/project/talk）、每组可折叠、tag 渲染 `name · count` Badge；`typeFilter` 非空时只渲染对应那一组（决策 5）。② 新 API 客户端 `listSources()` + `listPapers` 增加 `source_name?: string[]` 参数（数组 `.join(",")` 后发送）。③ Browse 页 (`src/app/page.tsx`) 把 `typeFilter` + `selectedSources` 从组件 state 迁到 URL（`?type=...&source=arxiv,openai`），通过 `router.replace` 与 `useSearchParams` 双向绑定；切 type 时 silently drop 类型不匹配的 selected source（决策 5 自然推论）；query 模式（`?q=`）下 SourceFilter 不渲染（与 type filter 在搜索模式被忽略行为对称）。④ i18n 加 3 条 key（`browse.filter.sources` / `.expand` / `.collapse`）。⑤ e2e 测试 +2 例（点 tag → URL/列表更新；切 type=paper → blog source 被静默 drop）；现有 chat / paper-card / 移动端响应式 / `/reports` Run-Now 面板均不变。⑥ `src/lib/types.ts` 新增 `Source` / `SourcesResponse`。 |
```

- [ ] **Step 10.4: Verify CLAUDE.md edits compile (sanity)**

Run: `cd /home/robin/gpgpu-kb && grep -c "2026-05-03 23:00:00" CLAUDE.md backend/CLAUDE.md frontend/CLAUDE.md`
Expected: each file shows `1` (one new row each).

- [ ] **Step 10.5: Commit**

```bash
git add CLAUDE.md backend/CLAUDE.md frontend/CLAUDE.md
git commit -m "docs: log browse-page source filter changes in CLAUDE.md tree"
```

---

## Task 11: Final verification — full test suite + lint

**Files:** none (verification only)

- [ ] **Step 11.1: Backend full suite**

Run: `cd backend && python -m pytest tests/ -x -q`
Expected: All tests PASS, with exactly **+7** more passing tests than before this branch started. (Baseline pre-this-feature is `203 + ~6` = ~209 after the prior daily-pipeline-endpoint branch landed; this feature adds 7. Treat your local pre-branch count as ground truth — don't hard-code numbers.)

- [ ] **Step 11.2: Frontend type check + lint**

Run: `cd frontend && npx tsc --noEmit && npx eslint src/`
Expected: No errors.

- [ ] **Step 11.3: Frontend build (catches runtime issues e2e wouldn't)**

Run: `cd frontend && npm run build`
Expected: Build completes; output mentions standalone server in `.next/standalone`.

- [ ] **Step 11.4: Frontend e2e**

Run: `cd frontend && npx playwright test --reporter=line`
Expected: All e2e tests PASS, including chat.spec.ts (regression) and the 2 new browse.spec.ts cases.

- [ ] **Step 11.5: Summary commit (if there are stray no-op changes)**

If `git status` shows nothing, skip. Otherwise:

```bash
git add -A
git commit -m "chore: final verification artifacts"
```

---

## Self-Review Checklist (Done — recorded for traceability)

- **Spec coverage** — every section of the spec maps to a task:
  - Spec §3.1 (`/api/sources`) → Task 2
  - Spec §3.2 (schemas) → Task 1
  - Spec §3.3 (`source_name` param on `/api/papers`) → Task 3
  - Spec §3.4 (don't touch `/api/papers/search`) → Task 8 (frontend hides SourceFilter in query mode); no backend change needed.
  - Spec §4.1 (types) → Task 4
  - Spec §4.2 (API client) → Task 5
  - Spec §4.3 (`SourceFilter` component) → Task 7
  - Spec §4.4 (Browse page URL state + integration) → Task 8
  - Spec §4.5 (i18n keys) → Task 6
  - Spec §6 (edge cases) — covered: empty `source_name` (Task 3), unknown name in URL (preserved as-is in Task 8), type-switch cleanup (Task 8 `onTypeChange`), missing /api/sources (Task 8 `.catch`), query mode hides filter (Task 8 conditional).
  - Spec §7 (testing) → Tasks 2, 3, 9
  - Spec §8 (file list) — every file under "新增" has a Create step; every file under "改动" has a Modify step.
  - Spec §10 (实施顺序) — task order matches: backend schemas → backend endpoint → backend filter → frontend types → frontend API → i18n → component → integration → e2e → docs.

- **Placeholder scan** — searched for "TBD", "TODO", "fill in", "implement later", "appropriate error handling", "similar to": none present in this plan.

- **Type consistency** — `Source { name, type, count }` matches between Task 4 (frontend type), Task 1 (backend schema), Task 5 (`source_name?: string[]`), Task 7 (`sources: Source[]` prop). `selectedSources: string[]` consistent across Task 8 (URL parse) and Task 7 (`selected` prop). `data-testid="source-tag-${name}"` consistent between Task 7 (component) and Task 9 (e2e selectors).
