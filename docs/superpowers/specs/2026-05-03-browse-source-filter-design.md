# Browse 页 Source 名称过滤 — 设计文档

- 日期：2026-05-03
- 作者：autopilot session（brainstorming workflow）
- 状态：待实现
- 关联文件：`backend/kb/main.py`、`backend/kb/schemas.py`、`frontend/src/app/page.tsx`、`frontend/src/lib/api.ts`、`frontend/src/lib/types.ts`

## 一、目标与背景

当前浏览页 (`frontend/src/app/page.tsx`) 已有 4 个 `source_type` tag (All / Papers / Blogs / Projects / Talks)，但用户无法按具体的 `source_name` 过滤——比如"只看 arxiv"或"只看 SemiAnalysis + OpenAI 这两个博客"。库里活跃的 `source_name` 大约 14+ 个（`arxiv`、`github`、12 个 RSS 源、1 个 sitemap 源），未来还会增加。

本特性新增第二条过滤维度：可多选的 `source_name` tag 行，与现有 type filter AND 组合，让用户能精细到具体来源站点。

## 二、决策摘要

| # | 决策点 | 选择 |
| --- | --- | --- |
| 1 | 单选 vs 多选 | **多选**（toggle 多个 source_name 并集） |
| 2 | source 列表来源 | **新加 `GET /api/sources`** 端点（自描述 + 真实计数） |
| 3 | 与 type filter 关系 | **AND 组合，两条 filter 并存独立 toggle** |
| 4 | 14+ tag 排版 | **按 source_type 分 4 组，可折叠** |
| 5 | type filter 选定时 | **隐藏不匹配的组**（type=Papers → 只渲染 Papers 组）；同时把 `selected` 里 type 不匹配的项静默 drop |
| 6 | URL 持久化 + tag 计数 | **都要**：`?type=...&source=arxiv,openai`；tag 文字 `arxiv · 1284` |

## 三、后端改动

### 3.1 新端点 `GET /api/sources`

放在 `backend/kb/main.py` 的 `/api/stats` 旁（无路径冲突）。

```python
from sqlalchemy import func

@app.get("/api/sources", response_model=SourcesOut)
def list_sources(db: Session = Depends(get_db)):
    rows = (
        db.query(Paper.source_name, Paper.source_type, func.count(Paper.id))
          .filter(Paper.is_processed == 1)
          .group_by(Paper.source_name, Paper.source_type)
          .order_by(func.count(Paper.id).desc())
          .all()
    )
    return SourcesOut(sources=[
        SourceItem(
            name=name,
            type=stype.value if hasattr(stype, "value") else str(stype),
            count=cnt,
        )
        for name, stype, cnt in rows
        if name  # 防御空 source_name
    ])
```

仅统计 `is_processed=1` 的行（与 `/api/papers` 默认行为一致；低质量 / 待处理行不应出现在过滤选项里）。

### 3.2 新增 schema

`backend/kb/schemas.py`：

```python
class SourceItem(BaseModel):
    name: str
    type: str  # "paper" | "blog" | "project" | "talk"
    count: int

class SourcesOut(BaseModel):
    sources: list[SourceItem]
```

### 3.3 扩展 `GET /api/papers`

新增 `source_name` 查询参数（多值用逗号分隔）：

```python
@app.get("/api/papers", response_model=PaperListOut)
def list_papers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source_type: str | None = None,
    source_name: str | None = Query(None, max_length=500),  # 新增
    sort_by: str = Query("total_score", pattern=...),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    include_low_quality: bool = Query(False),
    db: Session = Depends(get_db),
):
    q = db.query(Paper)
    if not include_low_quality:
        q = q.filter(Paper.is_processed == 1)
    if source_type:
        q = q.filter(Paper.source_type == source_type)
    if source_name:
        names = [n.strip() for n in source_name.split(",") if n.strip()][:50]  # cap 50 防 DoS
        if names:
            q = q.filter(Paper.source_name.in_(names))
    # ... rest unchanged
```

`max_length=500` + 50 项上限：粗略估算单个 source_name 平均 ~10 字符，14+ 个常见来源最长合并 ~200 字符，500 留 buffer 但防滥用。

### 3.4 不动 `/api/papers/search`

保持与现有 `source_type` 在搜索路径同样被忽略的行为：搜索模式按相关性出全部来源，避免误导用户"只在某来源里搜索却得到看似空集合的相关性结果"。前端在 query 模式下隐藏 SourceFilter（见 4.4）。

## 四、前端改动

### 4.1 新增类型 `frontend/src/lib/types.ts`

```ts
export interface Source {
  name: string;
  type: string;  // "paper" | "blog" | "project" | "talk"
  count: number;
}

export interface SourcesResponse {
  sources: Source[];
}
```

### 4.2 API 客户端 `frontend/src/lib/api.ts`

```ts
export async function listSources(): Promise<SourcesResponse> {
  return fetchJSON<SourcesResponse>(`/api/sources`);
}

// listPapers 增加 source_name 参数（数组，前端 join 成逗号）
export async function listPapers(params: {
  page?: number;
  source_type?: string;
  source_name?: string[];  // 新增
  sort_by?: string;
  sort_dir?: string;
}): Promise<PaperListResponse> {
  const sp = new URLSearchParams();
  // ... 其它参数
  if (params.source_name && params.source_name.length > 0) {
    sp.set("source_name", params.source_name.join(","));
  }
  return fetchJSON<PaperListResponse>(`/api/papers?${sp.toString()}`);
}
```

### 4.3 新组件 `frontend/src/components/source-filter.tsx`

```tsx
"use client";
import { useState } from "react";
import { Source } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { ChevronRight } from "lucide-react";
import { useT } from "@/lib/i18n/provider";

const GROUP_ORDER = ["paper", "blog", "project", "talk"] as const;

export function SourceFilter({
  sources,
  selected,
  onChange,
  typeFilter,
}: {
  sources: Source[];
  selected: string[];
  onChange: (names: string[]) => void;
  typeFilter: string;  // "" = All
}) {
  const t = useT();
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const grouped = GROUP_ORDER.map((type) => ({
    type,
    items: sources.filter((s) => s.type === type),
  })).filter((g) => g.items.length > 0);

  const visibleGroups = typeFilter
    ? grouped.filter((g) => g.type === typeFilter)
    : grouped;

  const toggle = (name: string) => {
    onChange(
      selected.includes(name)
        ? selected.filter((n) => n !== name)
        : [...selected, name]
    );
  };

  return (
    <div className="space-y-2">
      {visibleGroups.map((group) => {
        const isCollapsed = collapsed[group.type] ?? false;
        return (
          <div key={group.type} className="space-y-1">
            <button
              type="button"
              onClick={() => setCollapsed({ ...collapsed, [group.type]: !isCollapsed })}
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              <ChevronRight
                className={`h-3 w-3 transition-transform ${isCollapsed ? "" : "rotate-90"}`}
              />
              {t(`browse.filter.${group.type}s` as any)}
              <span className="text-[10px] opacity-60">({group.items.length})</span>
            </button>
            {!isCollapsed && (
              <div className="flex flex-wrap gap-1 pl-4">
                {group.items.map((s) => (
                  <Badge
                    key={s.name}
                    variant={selected.includes(s.name) ? "default" : "outline"}
                    className="cursor-pointer text-[10px] gap-1"
                    onClick={() => toggle(s.name)}
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

### 4.4 Browse 页 `frontend/src/app/page.tsx`

URL 持久化关键改动：

```tsx
const searchParams = useSearchParams();
const router = useRouter();
const query = searchParams.get("q") || undefined;
const typeFilter = searchParams.get("type") || "";
const selectedSources = (searchParams.get("source") || "")
  .split(",")
  .filter(Boolean);

// 写 URL helper
const updateParams = (next: { type?: string; source?: string[] }) => {
  const sp = new URLSearchParams(searchParams.toString());
  if ("type" in next) {
    if (next.type) sp.set("type", next.type);
    else sp.delete("type");
  }
  if ("source" in next) {
    if (next.source && next.source.length > 0) sp.set("source", next.source.join(","));
    else sp.delete("source");
  }
  router.replace(`/?${sp.toString()}`);
};

// type 切换时清理不匹配的 selected source（决策 5 自然推论）
const onTypeChange = (newType: string) => {
  const validNames = newType
    ? selectedSources.filter(
        (name) => sources.find((s) => s.name === name)?.type === newType
      )
    : selectedSources;
  updateParams({ type: newType, source: validNames });
  setPage(1);
};

// 拉 sources（一次即可，不随 query/type 变化）
const [sources, setSources] = useState<Source[]>([]);
useEffect(() => {
  listSources().then((r) => setSources(r.sources)).catch(() => {});
}, []);

// fetchPapers 把 selectedSources 传给 listPapers（只在非 query 模式）
```

`SourceFilter` 仅在非 query 模式（即 `!query`）下渲染，与现有 type filter 在搜索模式被忽略保持一致。

### 4.5 i18n 新增

`frontend/src/lib/i18n/translations.ts` 新增：

- `browse.sourceFilter.title`：默认 "Sources" / 中文 "来源"（标签上方分隔小标题，可选）
- `browse.sourceFilter.collapse`：aria-label "Collapse" / "折叠"
- `browse.sourceFilter.expand`：aria-label "Expand" / "展开"

4 个组标题复用现成 key：`browse.filter.papers` / `browse.filter.blogs` / `browse.filter.projects` / `browse.filter.talks`。

## 五、数据流

```
页面加载
  ├─ listSources() → setSources([{name, type, count}, ...])
  └─ fetchPapers(typeFilter, selectedSources, page, sort) ← from URL

用户点 source tag
  ├─ toggle: onChange(newSelected)
  ├─ updateParams({ source: newSelected }) → URL 改变
  └─ useSearchParams 触发 useEffect → fetchPapers 重新请求

用户切 type filter
  ├─ onTypeChange(newType)
  ├─ 清理 selectedSources 里 type 不匹配的项
  ├─ updateParams({ type, source: cleanedSelected }) → URL 改变
  └─ fetchPapers 重新请求 + SourceFilter 只渲染 newType 组
```

## 六、边界处理

1. **空库** (`/api/sources` 返回 `sources: []`)：SourceFilter 不渲染任何分组（`visibleGroups` 为空数组）；不报错、不显示空状态。
2. **URL 含库里不存在的 source**（旧链接 / 手敲 `?source=foobar`）：后端 `Paper.source_name.in_([...])` 自然返回 0 行；前端不存在的名字不出现在 tag 里但保留在 selected 里——下次用户清掉就消失。可接受，无需特殊处理。
3. **type-切换清理时机**：`onTypeChange` 触发时若 `sources` 还没加载完（首次极短窗口），跳过清理——此时 UI 还没显示给用户点，不会出现 mismatch。
4. **URL 干净**：空值 key 不写入（`type=` 空串 delete `type`；`source=[]` delete `source`），分享链接最简洁。
5. **多选上限**：后端 cap 50 项（防 SQL `IN (...)` 过长）；前端不强制，用户极难触及（库里 source 总数远少于 50）。
6. **Query 模式**（`?q=` 走 search）：SourceFilter 不渲染。Type filter 现状是渲染但被 search 忽略——本特性不动现状，保持与原有行为对称（避免误改非本特性范围）。
7. **`/api/sources` 失败**（网络错误）：catch 静默 + sources 保持空数组；SourceFilter 不渲染；其它过滤照常工作。

## 七、测试

### 7.1 后端 (`backend/tests/test_api_smoke.py`)

新增 4 例：

1. `test_list_sources_returns_distinct_names_with_counts`：seed 3 papers (`arxiv`, `arxiv`, `OpenAI`)，断言 `/api/sources` 返回 `[{name:"arxiv", count:2, ...}, {name:"OpenAI", count:1, ...}]`，按 count desc。
2. `test_list_sources_excludes_low_quality_and_pending`：seed `is_processed=2` 与 `is_processed=0` 行，断言不在结果里。
3. `test_list_papers_filters_by_single_source_name`：`?source_name=arxiv` 仅返 `source_name == "arxiv"` 的 paper。
4. `test_list_papers_filters_by_multiple_source_names`：`?source_name=arxiv,OpenAI` 命中两者并集，不返回 `SemiAnalysis` 等其它行。

### 7.2 前端 e2e (`frontend/tests/e2e/`)

新增 2 例（在 mock 后端的现有套路下）：

1. `test_source_filter_toggle_updates_url_and_list`：mock `/api/sources` 返 `[{arxiv,paper,10}, {SemiAnalysis,blog,5}]`；mock `/api/papers` 收到 `source_name=arxiv` 时返只含 arxiv 的列表。点 `arxiv` tag → 断言 URL 含 `?source=arxiv`、列表只剩 arxiv。
2. `test_type_filter_drops_mismatched_source`：先点 `SemiAnalysis`（blog），再切 type 到 Papers → 断言 URL 里 `source` 被清空（SemiAnalysis 不是 paper，被静默 drop）。

## 八、文件清单

**新增**：

- `frontend/src/components/source-filter.tsx`

**改动**：

- `backend/kb/main.py`（+ `list_sources` 端点 / `list_papers` 新增 `source_name` 参数）
- `backend/kb/schemas.py`（+ `SourceItem` / `SourcesOut`）
- `backend/tests/test_api_smoke.py`（+4 例）
- `frontend/src/lib/types.ts`（+ `Source` / `SourcesResponse`）
- `frontend/src/lib/api.ts`（+ `listSources` / `listPapers` 新增 `source_name`）
- `frontend/src/app/page.tsx`（URL 状态接管 typeFilter + selectedSources、SourceFilter 接入、type-切换清理）
- `frontend/src/lib/i18n/translations.ts`（+3 条 key）
- `frontend/tests/e2e/`（+2 例）

**不动**：

- `/api/papers/search`、`SearchBar`、`PaperCard`、`paper/[id]/page.tsx`、Chat 相关、Reports、Stats（本特性范围外）。

## 九、不影响项 / 显式 non-goals

- 不改 ingestion / processing / scoring / chat / reports 流水线。
- 不改 SQLite schema（`Paper.source_name` 列已存在并已写入数据，无 migration）。
- 不在搜索路径 (`/api/papers/search`) 加 source 过滤——保留现状对称性。
- 不做"按 source 排序"——只过滤；排序仍走现有 `sort_by` 选项。
- 不做"保存我喜欢的来源组合"等高阶用法——URL 共享已足够。

## 十、实施顺序建议（写 plan 时细化）

1. 后端 schema + 端点 + 单测 → `pytest tests/ -x -q` 通过。
2. 前端 types + api 客户端 + listSources 调用。
3. SourceFilter 组件 + 接入 Browse 页 URL 状态。
4. e2e 测试 + 类型检查 + lint。
5. CLAUDE.md 增量刷新（根 + backend + frontend），记录新端点 / URL 参数 / SourceFilter 组件位置 / 测试套件计数 (203 → 207 / e2e +2)。
