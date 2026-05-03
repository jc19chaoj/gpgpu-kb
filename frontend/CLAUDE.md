# frontend/ — Next.js 16 / React 19 UI

[← 返回根](../CLAUDE.md) > **frontend**

> 由 `init-architect` 于 `2026-04-25 09:59:45` 自动生成，
> 于 `2026-04-25 15:26:48` 增量刷新（Playwright e2e / CI / Bearer Token 警示），
> 于 `2026-05-02 08:57:04` 增量刷新（Next 16 standalone build / `/api/*` 反向代理 / Universal Score Axes / Docker 镜像 / `/search` 永久重定向到首页），
> 于 `2026-05-02 20:12:04` 增量刷新（多轮 Chat 对话历史（localStorage 持久化）/ Source pin 锚定模式 / `/chat?paperId=` 深链 / 移动端响应式聊天输入条 / 错误状态 transient 标记），
> 于 `2026-05-02 21:18:53` 增量刷新（**SSE 流式聊天 `chatStream` async generator + Stop 按钮（`AbortController`）+ `streaming` placeholder 增量 token 渲染 + 切换会话/卸载/deep-link 自动 abort + `enterKeyHint="send"` 移动键盘提示**）。
> 于 **`2026-05-03 22:34:43`** 增量刷新（**Themed i18n shell + reports 页 Run-Now SSE 进度面板**）：① 全新 i18n 模块 `src/lib/i18n/{provider.tsx,translations.ts,format.ts}`（`LocaleProvider` / `useLocale` / `useT` + en/zh 双语字典 ~110 keys + locale-aware `formatDate` / `formatLongDate`）；② 全新 theme 模块 `src/lib/theme/provider.tsx`（`ThemeProvider` / `useTheme`，layout 头部 inline FOUC-prevention 脚本，**Cream Linen**（light）+ **Walnut Hearth**（dark）双主题，`globals.css` 改为 `@theme inline` + oklch CSS variables）；③ Header 加入 `<ThemeSwitcher />` + `<LanguageSwitcher />` 两组 segmented control；Sidebar 全部走 `t("nav.*")`；④ Reports 页（`src/app/reports/page.tsx`）加入 "Run pipeline now" 按钮 → `runDailyStream({ signal })` async generator → 渲染 4-stage 进度条 + 实时日志面板（`MAX_LOG_LINES=2000`）+ 跨 tab `getDailyStatus()` 探测；⑤ 前端 API 客户端新增 `getDailyStatus()` / `runDailyStream()` / `DailyConflictError` / `_parseDailyFrame`（跳过 `:` keepalive 注释帧），`DailyStatus` / `DailyStageName` / `DailyStreamEvent` 加进 `types.ts`。聊天 `chat?paperId` 深链 / 多轮 chat / SSE 流式聊天行为不变。
>
> ⚠️ 必读：`frontend/AGENTS.md` 提示 **这是最新版 Next.js（16.x），API 与约定可能与旧版本不同**。在写代码前先阅读 `frontend/node_modules/next/dist/docs/` 中的相应文档。

---

## 一、模块职责

提供 GPGPU Knowledge Base 的浏览器 UI：

- **Browse**：分页、按类型过滤、按多维度排序的论文/博客/项目列表（默认按 `total_score`）
- **Search**：URL `?q=...` 触发，调后端语义检索，自动回退关键字搜索
- **Chat（流式）**：**多轮 RAG 对话** + **Source pin 锚定模式** + **SSE 增量 token 流式渲染** + Stop 按钮 + `/chat?paperId=` 深链
- **Paper detail**：单条详情，含双维 0-10 分（按 `source_type` 切换标签）与 rationale；可触发 "Open in Chat" 跳到 `/chat?paperId=...`
- **Reports（本轮增强）**：每日 Markdown 报告列表与详情；**新增"Run pipeline now"按钮 → SSE 实时进度面板**（4-stage 进度条 + 实时日志面板 + 完成后 Reload 按钮）
- **Stats**：知识库整体统计

整套界面采用**双主题**（Cream Linen light / Walnut Hearth dark，oklch 调色板）+ **双语**（en / zh），每个用户偏好都通过 localStorage 持久化（`gpgpu-kb.theme.v1` / `gpgpu-kb.locale.v1`）。`<html>` 在 SSR / first paint 永远是 `lang="en" class="dark"` 默认值，再由 `app/layout.tsx` 头部 inline `<script>` 在 React 挂载前先按 localStorage 切 `<html>` class 防 FOUC，然后 `LocaleProvider` / `ThemeProvider` 在 `useEffect` 内调和到持久化值。

---

## 二、入口与启动

| 入口 | 作用 |
| --- | --- |
| `src/app/layout.tsx` | RootLayout：`<html lang="en" className="h-full antialiased dark" suppressHydrationWarning>`、inline `THEME_INIT_SCRIPT` FOUC-prevention、`<ThemeProvider><LocaleProvider><AppShell>` 嵌套；`viewport.themeColor` dual-mode（跟系统 `prefers-color-scheme` 切换地址栏 tint） |
| `src/app/page.tsx` | `/` Browse 页（含 `?q` → search）；外层套 `<Suspense>` |
| `src/app/chat/page.tsx` | `/chat` 多轮 **流式** RAG / source-anchored 聊天页；外层 `<Suspense>` 包 `useSearchParams("paperId")` |
| `src/app/paper/[id]/page.tsx` | `/paper/:id` 论文详情；`SCORE_LABELS` 按 `source_type` 切换显示 |
| `src/app/reports/page.tsx`（**本轮重写**） | 报告列表 + **"Run pipeline now" 按钮** + SSE 进度面板（4-stage `StagePill` + log 面板 with `MAX_LOG_LINES=2000` 截尾 + Reload 按钮 + 跨 tab in-flight 探测）；用 `useLocale().t(...)` 全 i18n 化 |
| `src/app/reports/[id]/page.tsx` | 报告详情（Markdown via `react-markdown` + `remark-gfm`）|
| `src/app/stats/page.tsx` | `/stats` 统计 |
| `src/lib/i18n/provider.tsx`（**新**） | `LocaleProvider` + `useLocale` + `useT` Context；localStorage `gpgpu-kb.locale.v1`；SSR 期间永远 `DEFAULT_LOCALE="en"`，mount 后才反水到持久化值；`useEffect` 同步 `document.documentElement.lang = "zh-CN"\|"en"` |
| `src/lib/i18n/translations.ts`（**新**） | en / zh 双语字典 ~110 keys；`TranslationKey = keyof typeof translations.en`；`{name}` / `{count}` 占位符通过 `_interpolate` 替换（**不支持 ICU plurals**） |
| `src/lib/i18n/format.ts`（**新**） | `formatDate` / `formatLongDate` / `localeTag`：`Date.toLocaleDateString` 包成 locale-aware（`en-US` / `zh-CN`）|
| `src/lib/theme/provider.tsx`（**新**） | `ThemeProvider` + `useTheme` Context；`THEME_STORAGE_KEY = "gpgpu-kb.theme.v1"`；`DEFAULT_THEME = "dark"`；`useEffect` 同步 `document.documentElement.classList.toggle("dark", ...)` |
| `src/components/layout/app-shell.tsx` | Sidebar + Header dashboard 布局；React 19 "在 render 中 derive state from path" 模式（`if (pathname !== lastPath) setOpen(false)`，避免 useEffect 副作用） |
| `src/components/layout/sidebar.tsx` | 全部走 `t("nav.*")` + 版本号读 `package.json::version` |
| `src/components/layout/header.tsx`（**本轮加入两组 switcher**） | `<ThemeSwitcher />` + `<LanguageSwitcher />` segmented control |
| `src/components/theme-switcher.tsx`（**新**） | Sun/Moon segmented control，pill + 滑动 thumb（`style={{ left: \`${activeIndex * 1.75}rem\` }}`）；hydrated 前 thumb opacity=0 防 SSR snapshot painted under wrong tab |
| `src/components/language-switcher.tsx`（**新**） | EN / 中 segmented control，与 ThemeSwitcher 视觉对称 |
| `src/hooks/use-conversation-history.ts` | localStorage 持久化对话（`gpgpu-kb.chat.conversations.v1`）|
| `src/components/chat/chat-right-sidebar.tsx` | 右侧 sidebar（History / Source 两个 Tab） |
| `src/components/chat/source-picker.tsx` | Pick source 弹窗（防抖 300 ms） |
| `next.config.ts` | **Next 16 关键配置**：`output: "standalone"` + `/api/*` 反代 + `/search → /` 重定向 |
| `playwright.config.ts` | e2e（chromium / `npx next start -p 3000`） |
| `Dockerfile` | 三阶段（deps / builder / runner）；非 root；`server.js` 启动 |

启动命令同上一轮。

---

## 三、对外接口（前端 → 后端 API 客户端）

文件：`src/lib/api.ts`，`API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""`（默认空串走同源 `/api/*` 经 Next 反代到 backend）。

| 函数 | 后端端点 | 用途 |
| --- | --- | --- |
| `listPapers(params)` | `GET /api/papers` | 列表 + 过滤/排序。`params.source_name?: string[]` 多选时**前端 join `","`** 再发，后端 split 成 `IN (...)` |
| **`listSources()`**（**本轮新增**） | **`GET /api/sources`** | 浏览页 SourceFilter 数据源；返回 `{ sources: Source[] }`，每条 `{ name, type, count }` |
| `getPaper(id)` | `GET /api/papers/{id}` | 详情；deep-link 进 chat 时也调它解析 `?paperId=` |
| `searchPapers(q, params)` | `GET /api/papers/search` | 语义/关键字检索；SourcePicker 强制 `semantic:false` |
| `chat(request)` | `POST /api/chat` | **非流式** RAG / source-anchored；通过 `_chatPayload(request)` 清理 undefined / null 后再 POST |
| `chatStream(request, { signal? })` | `POST /api/chat/stream` | **SSE 流式 async generator**。`response.body.getReader()` + `TextDecoder` 累积 → 按 `\n\n` 分帧 → `_parseSSEFrame` 解码为 `ChatStreamEvent` discriminated union |
| **`getDailyStatus()`**（**本轮新增**） | **`GET /api/daily/status`** | 返回 `{ running, started_at, current_stage }` 快照。`/reports` 页 mount 时调用，决定 Run-Now 按钮的初始 enabled/disabled 状态——避免他 tab 已经在跑时本 tab 还允许发出第二个 POST 拿 409 |
| **`runDailyStream({ signal? })`**（**本轮新增**） | **`POST /api/daily/stream`** | **SSE 流式 async generator**，与 `chatStream` 对称。`Accept: text/event-stream`，body `"{}"`；`_parseDailyFrame` 解码（**注意：跳过 `:` keepalive 注释帧**）；HTTP 409 → 抛 **`DailyConflictError`**（专用错误类，前端在 catch 内识别这个类型并切到 "another run in progress" UI）。**取消 fetch 不会 abort 服务端 pipeline**——daemon thread 会跑完 |
| `listReports(limit?)` | `GET /api/reports` | 报告列表 |
| `getReport(id)` | `GET /api/reports/{id}` | 报告详情 |
| `getStats()` | `GET /api/stats` | 统计 |

类型定义集中在 `src/lib/types.ts`：

| 字段 / 接口 | 类型 | 备注 |
| --- | --- | --- |
| `originality_score` / `impact_score` / `impact_rationale` | number / string | legacy 字段 |
| `quality_score` / `relevance_score` / `score_rationale` | number / string | universal axes |
| `Stats.top_overall?` | `{id, title, source_type, quality_score, relevance_score}[]` | 跨类型 Top-5 |
| `ChatMessage` | `{ role: "user" \| "assistant"; content: string }` | 没有 system role |
| `ChatRequest` | `{ query, top_k?, paper_id?, history? }` | – |
| `ChatStreamEvent` | discriminated union `sources \| token \| error \| done` | 与后端 `_sse_event` 镜像 |
| **`Source`**（**新**） | `{ name: string; type: string; count: number }` | `type` 与后端 `SourceType` enum value 镜像（`"paper" \| "blog" \| "project" \| "talk"`） |
| **`SourcesResponse`**（**新**） | `{ sources: Source[] }` | `listSources()` 返回值 |
| **`DailyStatus`**（**新**） | `{ running: boolean; started_at: string \| null; current_stage: DailyStageName \| null }` | `getDailyStatus()` 返回值 |
| **`DailyStageName`**（**新**） | `"ingestion" \| "processing" \| "embedding" \| "report"` | 与后端 `_STAGE_NAMES` 镜像 |
| **`DailyStreamEvent`**（**新**） | discriminated union `started \| stage \| log \| error \| done` | `runDailyStream()` yield 的事件；`stage` 含 `index: 1\|2\|3\|4` 与 `name: DailyStageName`；与后端 `_sse_event` 镜像，新增事件类型时**两侧都要加**且更新 `_parseDailyFrame` |

> 部署到生产 / 使用 cpolar 暴露时，若后端启用了 Bearer Token 守卫，需要扩展 `fetchJSON` / `chatStream` / `getDailyStatus` / `runDailyStream` 接受 token——本轮新增的两个 daily 端点也受 `verify_chat_token` 守卫，这一坑同样存在。

---

## 四、Next.js 16 特殊配置（`next.config.ts`）

```ts
output: "standalone"  // 生成 .next/standalone/server.js
async redirects() {
  return [{ source: "/search", destination: "/", permanent: false }];
}
async rewrites() {
  return [{ source: "/api/:path*", destination: `${KB_BACKEND_URL}/api/:path*` }];
}
```

> **keep-alive + SSE 注意**：backend 已加 `--timeout-keep-alive 75`；SSE 流式响应（`/api/chat/stream` 与 **本轮新增的 `/api/daily/stream`**）天然依赖长 keep-alive。任何中间反代（cpolar / nginx）都必须**关闭 `text/event-stream` 的 buffering**。后端发 `X-Accel-Buffering: no` + `Cache-Control: no-cache`；nginx 还需要 `proxy_buffering off; proxy_read_timeout 3600;`（daily pipeline 整个跑完可能 30+ 分钟）。

---

## 五、关键依赖与配置

`package.json` 摘录（无新增依赖；本轮 i18n / theme 全用 React Context + localStorage 自实现）：

| 依赖 | 版本 | 说明 |
| --- | --- | --- |
| `next` | 16.2.x | App Router |
| `react` / `react-dom` | 19.x | React 19 |
| `@base-ui/react` | ^1.x | shadcn/ui 底层原语 |
| `shadcn` | ^4.x | shadcn 组件 CLI |
| `class-variance-authority` / `clsx` / `tailwind-merge` | – | 样式工具链 |
| `lucide-react` | ^1.x | 图标（含 `Square` / `Languages` / `Sun` / `Moon` / `Play` / `Loader2` / `RotateCcw` / `Check` / `AlertCircle`） |
| `react-markdown` + `remark-gfm` | ^10 / ^4 | Markdown 渲染 |
| `tailwindcss` / `@tailwindcss/postcss` | ^4 | Tailwind v4 |
| `tw-animate-css` | ^1.x | 动画扩展 |
| `eslint` + `eslint-config-next` | ^9 / 16.x | flat config Lint |
| `typescript` | ^5 | strict |
| `@playwright/test` | ^1.x | e2e（devDep） |

环境变量（不变）：`NEXT_PUBLIC_API_URL` / `KB_BACKEND_URL` / `NPM_REGISTRY` / `NEXT_PUBLIC_CHAT_TOKEN`（建议，未实现）。

---

## 六、目录结构

```
frontend/
├─ AGENTS.md                # ⚠️ Next.js 16 警示
├─ CLAUDE.md                # 本文件
├─ package.json
├─ tsconfig.json
├─ next.config.ts           # output: standalone + /api 反代 + /search 重定向
├─ playwright.config.ts
├─ eslint.config.* / postcss.config.*
├─ Dockerfile               # 三阶段
├─ .dockerignore
├─ tests/
│  └─ e2e/                  # Playwright 用例
└─ src/
   ├─ app/                  # App Router
   │  ├─ layout.tsx         # 根布局：ThemeProvider + LocaleProvider + AppShell + inline FOUC-prevention 脚本 + viewport.themeColor dual-mode
   │  ├─ page.tsx           # Browse / Search
   │  ├─ chat/page.tsx      # 多轮流式 RAG + source-anchored
   │  ├─ paper/[id]/page.tsx
   │  ├─ reports/page.tsx   # ★ 本轮重写：Run-Now 按钮 + SSE 进度面板
   │  ├─ reports/[id]/page.tsx
   │  ├─ stats/page.tsx
   │  └─ globals.css        # ★ 本轮重写：@theme inline + oklch tokens（:root = Cream Linen, .dark = Walnut Hearth）
   ├─ components/
   │  ├─ layout/
   │  │  ├─ app-shell.tsx
   │  │  ├─ sidebar.tsx     # ★ 本轮 i18n 化
   │  │  └─ header.tsx      # ★ 本轮加入 ThemeSwitcher + LanguageSwitcher
   │  ├─ ui/                # shadcn/ui 原语
   │  ├─ chat/              # chat 子组件
   │  ├─ paper-card.tsx
   │  ├─ search-bar.tsx
   │  ├─ source-filter.tsx      # ★ 本轮新增：分组折叠 + tag 多选 SourceFilter
   │  ├─ language-switcher.tsx  # ★ 新
   │  └─ theme-switcher.tsx     # ★ 新
   ├─ hooks/
   │  └─ use-conversation-history.ts
   └─ lib/
      ├─ api.ts             # ★ 本轮新增 getDailyStatus / runDailyStream / DailyConflictError / _parseDailyFrame
      ├─ types.ts           # ★ 本轮新增 DailyStatus / DailyStageName / DailyStreamEvent
      ├─ utils.ts           # cn / clsx
      ├─ i18n/              # ★ 新
      │  ├─ provider.tsx    # LocaleProvider / useLocale / useT
      │  ├─ translations.ts # en + zh ~110 keys
      │  └─ format.ts       # formatDate / formatLongDate / localeTag
      └─ theme/             # ★ 新
         └─ provider.tsx    # ThemeProvider / useTheme / THEME_STORAGE_KEY / DEFAULT_THEME
```

---

## 七、Universal Score Axes（前端镜像后端，不变）

详见上一轮文档。

---

## 八、Chat 模块（流式版本细节，不变）

详见上一轮文档（`chatStream` async generator / `abortRef` / `streaming` placeholder / `_chatPayload` / `_parseSSEFrame`）。

---

## 八.5、Browse 页 SourceFilter（本轮新增）

文件：`src/components/source-filter.tsx` + `src/app/page.tsx`（`BrowseContent`）。

**UI 形态**：左栏 type radio（All / Papers / Blogs / Talks / Projects）下方追加 SourceFilter 区块——按 `source_type` 分 4 组（paper/blog/project/talk），每组可折叠（chevron 旋转 90°），tag 用 shadcn `Badge`（selected = `default` solid，unselected = `outline`），格式 `name · count`。`onClick` 切 selected 集合，`onChange(names)` 上抛父级。

**type → source 联动**（**Decision 5**）：当 `typeFilter` 非空时，SourceFilter 只渲染对应那一组——其它组直接隐藏。同时父级 `onTypeChange` 在切 type 时**静默 drop** `selectedSources` 里 type 不匹配的条目（依据 `sources.find(s => s.name === name).type`，未知 source 暂时保留直到 `/api/sources` 解析完）。`?q=` 搜索模式下 SourceFilter **不渲染**（搜索路径忽略 type/source 过滤是后端契约现状）。

**URL state**（`?type=paper&source=arxiv,vLLM Blog`）：

- **初始读**：`useSearchParams()` 在首次渲染时取 `type` / `source`，喂进 `useState` 初值。
- **后续写**：filter 变化走 React `setState`，**URL 同步用 `window.history.replaceState`**——**不**用 `router.push/replace`。
- **为什么不用 router**：Next.js 16.2.x 已知 router cache 回归（vercel/next.js#92187）使 `router.push/replace` 在"同 pathname、不同 search"导航时**静默 no-op**——侧栏 `<Link href="/">` 被 prefetch 触发缓存命中即复现。`window.history.replaceState` 绕开整个 router 栈，URL 仍可分享，SSR/CSR 链接行为不变。
- **trade-off**：因为不走 router，浏览器后退 / 前进按钮**不会**自动重新渲染 BrowseContent（filter state 是 React 内部的）。如果未来 Next 修了这个 bug，改回 `router.replace` 即可获得 back/forward 同步。

**fetch 触发**：`useEffect([page, sortBy, sortDir, typeFilter, sourceKey, query])` 内 inline 调 `listPapers({ source_name: names })`；`sourceKey = selectedSources.join(",")` 是个**派生 primitive**，作 dependency 让 `Object.is` 比较稳定，**不要**直接把 `selectedSources` 数组放进 deps（React Compiler 会拒绝 + 引用每次 render 不稳）。

**i18n keys**：`browse.filter.sources` / `.expand` / `.collapse`（en + zh 两侧都加）。group label 复用既有 `browse.filter.papers` / `.blogs` / `.projects` / `.talks`。

---

## 九、Themed i18n shell（本轮重点新增）

### 9.1 i18n 模块（`src/lib/i18n/`）

`LocaleProvider`（`provider.tsx`）：

```tsx
const STORAGE_KEY = "gpgpu-kb.locale.v1";
const DEFAULT_LOCALE: Locale = "en";

useEffect(() => {
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (_isLocale(stored)) setLocaleState(stored);
  setHydrated(true);
}, []);

useEffect(() => {
  document.documentElement.lang = locale === "zh" ? "zh-CN" : "en";
}, [locale]);
```

要点：

- **SSR / first paint 永远渲染 `DEFAULT_LOCALE="en"`**，避免 hydration mismatch。React 19 会 flag setState-in-effect，标准修法是 server cookie，本项目刻意保留默认值 + mount 后调和的简单模式。
- `<html lang="...">` 通过 effect 同步——给 a11y / browser translation / `:lang()` selector 都跟进。
- `setLocale(next)` 写 localStorage 用 try/catch 包裹（隐私模式 / quota 满 silently 失败，UI 仍更新）。

`translations.ts`：

- `translations = { en: {...}, zh: {...} } as const` 双层对象。
- **en 是 source of truth**：`TranslationKey = keyof typeof translations.en`，TS 自动收紧 `t(...)` 的 key 类型。
- 当前 ~110 keys，覆盖：brand / shell / nav / lang / theme / search / browse / card / score / paper / **reports（含 reports.run.* 流水线触发相关 18 个 key）** / stats / chat / picker。
- **`zh` 必须保持与 `en` 完全相同的 key 集合**——CI 没有自动校验工具，靠 review 把关；如果 zh 漏 key，`useT()(missingKey)` 会回退到 `key` 字面量（视觉异常但不报错）。
- `_interpolate(template, params)` 只支持 `{name}` / `{count}` 等 placeholder 替换，**不支持 ICU plurals**——要复数就分多个 key（如 `card.morePeople` 用 `+{count} more` 单复用同一模板）。

`format.ts`：locale-aware 日期格式化。`formatLongDate("2026-04-25", "zh")` → "2026年4月25日 星期六"；`formatLongDate(..., "en")` → "Saturday, April 25, 2026"。所有调用点用 `useLocale().locale` 拿当前 locale 传进去。

### 9.2 theme 模块（`src/lib/theme/`）

`ThemeProvider`（`provider.tsx`）：

```tsx
export const THEME_STORAGE_KEY = "gpgpu-kb.theme.v1";
export const DEFAULT_THEME: Theme = "dark";
export const THEMES: readonly Theme[] = ["light", "dark"] as const;

useEffect(() => {
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
  if (_isTheme(stored)) setThemeState(stored);
  setHydrated(true);
}, []);

useEffect(() => {
  document.documentElement.classList.toggle("dark", theme === "dark");
}, [theme]);
```

**FOUC-prevention**（`app/layout.tsx` 头部）：

```tsx
const THEME_INIT_SCRIPT = `(function(){try{var t=localStorage.getItem("gpgpu-kb.theme.v1");var d=document.documentElement;if(t==="light"){d.classList.remove("dark");}else{d.classList.add("dark");}}catch(_){document.documentElement.classList.add("dark");}})();`;

return (
  <html lang="en" className="h-full antialiased dark" suppressHydrationWarning>
    <head>
      <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
    </head>
    ...
```

要点：

- **inline script 在 React 挂载前同步执行**：读 localStorage 切 `<html>` class，`body` 第一次 paint 就是正确主题——无闪烁。
- **storage key 字面量在两处硬编码**：`THEME_INIT_SCRIPT` 内的 `"gpgpu-kb.theme.v1"` 与 `provider.tsx::THEME_STORAGE_KEY`。改一处必须改两处——**这是写 raw HTML/JS，IDE 看不出错**。
- `<html lang="en" className="dark">` SSR 总是默认值，**`suppressHydrationWarning`** 静默 React 的 class / lang 属性 mismatch 告警（FOUC script 与 `LocaleProvider` 的 mount effect 都会改这两个属性，是有意为之的"server 渲染默认 + client 调和到 storage"）。
- `viewport.themeColor` dual-mode：跟系统 `prefers-color-scheme` 切地址栏 tint。**与 `<html class>` 是两套独立信号**——OS 级跟系统、UI 级跟 user toggle。

### 9.3 oklch 双主题（`globals.css`）

彻底替换原 `bg-zinc-950 text-zinc-100` 硬编码暗色：

- **Cream Linen**（light, `:root`）：parchment 米色背景 + caramel amber 主色 + chestnut brown 文字，长时间阅读护眼。
- **Walnut Hearth**（dark, `.dark`）：walnut bark 暗背景代替纯黑 + roasted cocoa 表面 + toasted amber 主色 + oat-mist 文字，温暖 fireside 风格。

`@theme inline` 把所有 shadcn 设计 token 映射到 CSS 变量：`--color-card` / `--color-primary` / `--color-sidebar` / `--color-chart-1..5` / `--color-destructive` / `--color-popover` / `--color-muted` / `--color-accent` / `--color-input` / `--color-ring` / `--color-border` 等，根据 `:root` / `.dark` 切换为 oklch 值。`@custom-variant dark (&:is(.dark *))` 显式声明 dark 变体，让 Tailwind v4 的 `dark:bg-...` 工作。

**编码规范**（重要）：从今天起**不要再用 `bg-zinc-...` / `text-zinc-...` 这种硬编码颜色**。新组件请用语义 token：`bg-background` / `text-foreground` / `bg-card` / `border-border` / `bg-sidebar` / `text-muted-foreground` / `bg-primary text-primary-foreground` 等。这些 token 在 `:root` / `.dark` 之间自动切换 oklch 值。例外：`Stop` 按钮专用 `red-600`（red 是中性危险信号，跨主题语义都成立）；`done` / `running` 状态分别用 `emerald-500/40` / `primary` 等。

### 9.4 LanguageSwitcher / ThemeSwitcher（`src/components/{language,theme}-switcher.tsx`）

视觉对称的 segmented control：

- 容器：`h-7 rounded-full border bg-card/60 p-0.5` pill 框。
- 滑动 thumb：`pointer-events-none absolute w-7 rounded-full bg-gradient-to-b from-primary/30 to-primary/15 ring-1 ring-primary/40`，`style={{ left: \`${activeIndex * 1.75}rem\` }}` 切当前选项。`pointer-events-none` 让 thumb 不抢点击，**关键避免 thumb 盖住按钮的 a11y label**。
- ThemeSwitcher 的 thumb 在 `hydrated` 之前 `opacity-0`：SSR snapshot 里 `theme=DEFAULT_THEME=dark` 但持久化值可能是 light，hydration 完成前画 thumb 会把它定位在错误位置 → 闪烁。

### 9.5 Header / Sidebar 重构

- `header.tsx`：右侧 `<ThemeSwitcher />` + `<LanguageSwitcher />`（移动端 `gap-2 sm:gap-3`）；左侧菜单按钮（`md:hidden`）+ 移动端品牌名 + flex spacer。
- `sidebar.tsx`：导航 5 项 (`/` / `/chat` / `/reports` / `/stats`) 全部走 `t("nav.*")`；版本号 `{t("shell.version")}{pkg.version}`（`pkg.version` import 自 `package.json`，build-time inlined）。`navItems[].labelKey: TranslationKey` 类型保证 key 拼写不出错。

---

## 十、Reports 页 Run-Now 按钮 + SSE 进度面板（本轮新增重点）

### 10.1 状态机：`RunState`

```ts
type RunPhase = "idle" | "starting" | "running" | "done" | "error";
interface RunState {
  phase: RunPhase;
  startedAt: string | null;
  activeIndex: number;          // STAGE_ORDER 索引：< activeIndex 已完成、= 当前、> 未开始；-1 = 未开始任何 stage
  errorMessage: string | null;
  conflict: boolean;            // 他 tab 在跑 / HTTP 409；按钮永久 disable
}
```

`STAGE_ORDER = ["ingestion","processing","embedding","report"]` + `STAGE_LABEL_KEY: Record<DailyStageName, TranslationKey>` 映射到 `reports.run.stage.*` i18n key。

### 10.2 Mount 时跨 tab 探测

```tsx
useEffect(() => {
  let cancelled = false;
  listReports(30).then(...);

  getDailyStatus().then((status) => {
    if (cancelled || !status.running) return;
    // 他 tab 在跑：本 tab 不 reattach（SSE 流的所有权属于发起 POST 的连接），
    // 仅锁住按钮 + 显示 "another run in progress"
    const stageIdx = status.current_stage ? STAGE_ORDER.indexOf(status.current_stage) : -1;
    setRun({ phase: "running", startedAt: status.started_at, activeIndex: stageIdx, errorMessage: null, conflict: true });
  }).catch(() => { /* 探测失败非致命 */ });

  return () => {
    cancelled = true;
    abortRef.current?.abort();   // 离开页面时 abort 当前流（pipeline 后端继续跑）
  };
}, []);
```

要点：

- `getDailyStatus()` 失败（401 / 网络）静默 swallow——保留 idle 状态，让用户至少能看到报告列表。
- 卸载时 abort 当前流：**只是断 fetch 连接，pipeline 在 backend daemon thread 内继续跑到完**——下次回到页面会通过 `getDailyStatus()` 重新探测到。

### 10.3 `handleRun` 流程

```tsx
const controller = new AbortController();
abortRef.current = controller;

try {
  let sawTerminal = false;
  for await (const ev of runDailyStream({ signal: controller.signal })) {
    applyEvent(ev, { setRun, appendLog });
    if (ev.type === "done" || ev.type === "error") sawTerminal = true;
  }
  if (!sawTerminal) {
    // 服务端没发 done / error 就 EOF——多半是中间反代砍连接 / 网络挂了
    setRun((prev) => prev.phase === "running" ? {
      ...prev, phase: "error", errorMessage: t("reports.run.connectionLost"),
    } : prev);
  } else {
    listReports(30).then(setReports).catch(() => {});  // 刷新报告列表
  }
} catch (err) {
  if (err instanceof DailyConflictError) {
    // HTTP 409 - 他人在跑，切到 conflict UI
    setRun({ phase: "error", ..., errorMessage: t("reports.run.conflict"), conflict: true });
    return;
  }
  if ((err as { name?: string }).name === "AbortError") return;  // 用户主动取消，不进 error
  setRun((prev) => ({ ...prev, phase: "error", errorMessage: ... }));
} finally {
  if (abortRef.current === controller) abortRef.current = null;
}
```

### 10.4 `applyEvent` 调度

```tsx
function applyEvent(ev: DailyStreamEvent, ctx) {
  switch (ev.type) {
    case "started":
      ctx.setRun((p) => ({ ...p, phase: "running", startedAt: ev.started_at || p.startedAt }));
      return;
    case "stage": {
      const idx = STAGE_ORDER.indexOf(ev.name);
      ctx.setRun((p) => ({ ...p, phase: "running", activeIndex: idx >= 0 ? idx : p.activeIndex }));
      return;
    }
    case "log":
      if (ev.line) ctx.appendLog(ev.line);
      return;
    case "error":
      ctx.setRun((p) => ({ ...p, phase: "error", errorMessage: ev.message || "Pipeline failed" }));
      return;
    case "done":
      ctx.setRun((p) => ({ ...p, phase: "done", activeIndex: STAGE_ORDER.length }));  // 全部 stage 染绿
      return;
  }
}
```

新增事件类型时**这里要加 case，并同步 `DailyStreamEvent` union + 后端 `_sse_event(...)` + 前端 `_parseDailyFrame`**。

### 10.5 `appendLog` + `MAX_LOG_LINES` 截尾

```tsx
const MAX_LOG_LINES = 2000;  // 100k-line 冷启动跑也不会让 tab OOM
const appendLog = useCallback((line: string) => {
  setLogs((prev) => {
    const next = prev.length >= MAX_LOG_LINES
      ? prev.slice(prev.length - MAX_LOG_LINES + 1)
      : prev.slice();
    next.push(line);
    return next;
  });
}, []);
```

`<ScrollArea>` + `whitespace-pre-wrap break-words font-mono`；`logEndRef.current?.scrollIntoView({ behavior: "smooth" })` 在 `[logs, showLogs]` 变化时自动滚到底部。

### 10.6 RunPanel UI

- 状态行：`AlertCircle`（error）/ `Check`（done）/ `Loader2 animate-spin`（running）+ 文案 + 相对时间（`formatRelativeTime(iso, locale)` 4 桶简易实现：just now / Xm / Xh / Xd ago，对应中文）。
- 4 个 `StagePill`（`<li>`），状态四色：`pending` / `running` / `done` / `error`。
- "View logs" 折叠按钮（默认折叠，但 starting 时自动展开看初始化日志）。
- `done` / `error` 终态显示 "Reload reports" 按钮 → `listReports(30)` 刷新 + `setRun(INITIAL_RUN_STATE)` 复位。

### 10.7 `_parseDailyFrame` 跳过 keepalive 注释

```ts
function _parseDailyFrame(raw: string): DailyStreamEvent | null {
  let event = "";
  let data = "";
  for (const line of raw.split("\n")) {
    if (!line || line.startsWith(":")) continue;     // ★ 跳过 SSE comment
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) {
      if (data) data += "\n";
      data += line.slice(5).trim();
    }
  }
  if (!event) return null;
  try {
    const parsed = data ? JSON.parse(data) : {};
    if (event === "started") return { type: "started", started_at: parsed.started_at ?? "" };
    if (event === "stage") {
      const idx = parsed.index;
      if (idx !== 1 && idx !== 2 && idx !== 3 && idx !== 4) return null;
      return { type: "stage", index: idx, name: parsed.name };
    }
    if (event === "log") return { type: "log", line: parsed.line ?? "" };
    if (event === "error") return { type: "error", message: parsed.message ?? "" };
    if (event === "done") return { type: "done" };
  } catch {
    return null;
  }
  return null;
}
```

**与 `_parseSSEFrame`（chat 用）的关键区别**：daily 端点会发 `: keepalive\n\n` 注释帧（每 15s），如果不在 `_parseDailyFrame` 显式跳过，`event` 仍为空被 return null，但更稳妥是 **在 line 级直接 `continue`**（chat 端点不发注释帧所以 `_parseSSEFrame` 不需要这个分支）。新增"长任务 SSE 端点"也要发 keepalive 注释帧，对应的解码函数都要复制此分支。

---

## 十一、约定与坑位

1. **Next.js 16 是最新版本**：先读 `node_modules/next/dist/docs/`。
2. **React 19**：在 effect 内 setState 会被 flag；当前项目刻意 keep simple。`pinnedPaperIdRef` + `abortRef` + `AppShell::lastPath` 都是 strict-mode / render-derived state 的标准对策。
3. **Suspense 边界**：使用 `useSearchParams` 必须包 `<Suspense>`。
4. **双主题 + oklch**（**本轮新增**）：新组件用语义 token（`bg-background` / `bg-card` / `bg-sidebar` 等），不要硬编码 `bg-zinc-...`。新颜色加进 `globals.css` 的 `:root` 与 `.dark` 两组 oklch 变量。`globals.css` 用 Tailwind v4 的 `@theme inline`，**不要再写 `tailwind.config.*`**。
5. **i18n 全量化**（**本轮新增**）：新组件不要写裸字符串字面量，全部走 `useT()`。新加 key 在 `en` + `zh` 两侧同步加；`TranslationKey` 类型自动校验 `t(...)` 调用。`{name}` placeholder 用 `_interpolate`，**无 ICU plurals**。
6. **localStorage key 版本化**：theme `gpgpu-kb.theme.v1` / locale `gpgpu-kb.locale.v1` / chat history `gpgpu-kb.chat.conversations.v1`——schema 兼容性破坏时 bump 到 `v2`，避免污染老数据。**`THEME_INIT_SCRIPT`（layout.tsx 头部 inline）内的 storage key 字面量是硬编码**，改时两处同步。
7. **shadcn/ui 复用**：UI 原语都在 `components/ui/`，新增基础原语优先用 `npx shadcn add ...`。
8. **Markdown 渲染**：聊天与报告页用 `react-markdown + remark-gfm`，对 LLM 输出做受控渲染。**不要在不可信文本上启用 raw HTML**。
9. **聊天 history persistence**：`Conversation` 接口与 `_isConversation` 守卫必须同步演进。
10. **`/search` 已并入首页**：`next.config.ts` 用 302 重定向。
11. **API_BASE 空串是默认**：浏览器同源 `/api/*` → Next 反代 → backend；不要硬编码 `http://localhost:8000`。
12. **`_chatPayload` 复用**：`api.ts` 里 `chat()` 与 `chatStream()` 共用 `_chatPayload(request)`。
13. **role 白名单**：`ChatMessage.role` 仅 `"user" | "assistant"`。
14. **`abortRef` 生命周期**：`finally` 内只在 `abortRef.current === controller` 时清空。
15. **流式 Stop 按钮 vs Send**：用 `loading` 状态条件渲染。
16. **新加 SSE 长任务端点**（**本轮新增 pattern**）：① 后端必须 `dependencies=[Depends(verify_chat_token)]` + `_DailyRunState` 同款 try_start/lock/409；② 必须发 15s SSE keepalive 注释帧；③ 前端解码函数必须跳过 `:` 注释帧；④ event union + types.ts + 后端 `_sse_event` 同步加分支；⑤ Reports 页 `applyEvent` switch 新增事件 case；⑥ stage 检测正则 `r"\[([1-4])/4\]"` 是和 `kb/daily.py` banner 格式硬约定。
17. **跨 tab 任务探测**（**本轮新增**）：要不要 mount 时调 `/api/<task>/status` 取决于"任务能否被多个 client 同时观察"——daily pipeline 不能 reattach 流，所以 `/reports` 页 mount 时 `getDailyStatus()` 仅用于"显示按钮 disabled + 'running since X'"文案，不试图重连。新增类似端点请遵循同款"探测但不 reattach"模式。

---

## 十二、测试与质量

- **静态检查**：`npm run lint` / `npx tsc --noEmit`。
- **e2e 测试**：`npm run test:e2e` → Playwright（chromium-only）。
  - **流式 chat 路径建议补的用例**：① mock `text/event-stream` → placeholder 增量；② Stop 按钮 abort → partial 持久化；③ 切换会话期间正在流；④ deep-link 起新会话且 URL 被清空。
  - **本轮新增建议补的用例**：⑤ Reports 页 Run-Now 按钮 → mock `runDailyStream` 发 4-stage 序列 → 验证 4 个 `StagePill` 切换；⑥ HTTP 409 → conflict UI；⑦ `getDailyStatus().running=true` mount 时按钮锁住；⑧ 切语言 → header / sidebar 文案立即跟进；⑨ 切主题 → `<html>` class 切换 + 颜色不闪。
- **当前未配置**：jest / vitest；推荐补 vitest 单测覆盖 `_parseDailyFrame` 跳 keepalive 注释 / `_interpolate` placeholder 替换 / `useConversationHistory` localStorage 边界。

---

## 十三、CI 集成

`.github/workflows/ci.yml` 中包含两个前端 job：

| Job | 步骤 |
| --- | --- |
| `frontend-typecheck` | `setup-node@v4`（Node 20）→ `npm ci` → `npx tsc --noEmit` → `npx eslint src/` |
| `frontend-e2e` | `setup-node@v4` → `npm ci` → `npx playwright install --with-deps chromium` → `npm run build` → `npm run test:e2e` |

---

## 十四、Docker 镜像

`Dockerfile` 三阶段不变；`NEXT_PUBLIC_API_URL` 与 `KB_BACKEND_URL` 都是 build-time baked。

---

## 十五、常见问题 (FAQ)

- **空白页 / `API error: 0`？** 检查后端是否运行。
- **首次搜索 / 聊天明显延迟？** 正常。
- **CORS 报错？** 不应出现——前端默认走同源 `/api/*` 反代。
- **聊天页 token 不增量出现？** 中间反代在 buffer SSE。
- **聊天页随机 "Sorry, I couldn't process that query"？** 检查 keep-alive / Token / ML 依赖。
- **Stop 按钮按了之后 UI 没停？** 检查 `abortRef.current` 是否真指向当前 controller。
- **历史记录消失？** localStorage 被清。
- **`/chat?paperId=999` 是个坏链？** fetch 失败时 URL 不会被清掉（刻意保留）。
- **e2e 在 CI 失败？** 检查是否漏跑 `npm run build`。
- **Docker 构建后浏览器仍然请求 localhost:8000？** `NEXT_PUBLIC_API_URL` 被显式设过。
- **看到 `Error: Hydration failed`？** 详情页 / history sidebar 的非默认值才渲染（hydrated flag 守卫）。
- **首次访问页面闪了一下白色？**（**本轮新增**）多半是 `THEME_INIT_SCRIPT` 没成功执行（隐私模式 / CSP 禁 inline script）。检查浏览器 Console 看是否有 CSP 报错；后端 / 反代 `Content-Security-Policy: script-src 'unsafe-inline'` 是必须的（或者改 nonce 模式但 layout.tsx 也要改）。
- **切语言后部分文案没变？**（**本轮新增**）排查 ① 该文案是否硬编码字面量没走 `useT()`；② 该 key 是否在 `zh` 字典里漏了（`useT()(missingKey)` 回退到 key 字面量）；③ 该文案是否来自后端 API（如 `daily_reports.title` / `paper.summary` 是 LLM 输出，由 `KB_LANGUAGE` 在生成时定型，前端 locale 切不动它——是设计而非 bug）。
- **切主题后某些组件颜色没变？**（**本轮新增**）多半是组件用了硬编码 `bg-zinc-...` / `text-zinc-...` 而非语义 token。改用 `bg-background` / `bg-card` / `text-foreground` 等。
- **Reports 页 "Run pipeline now" 按钮永远 disabled？**（**本轮新增**）要么 `_DailyRunState._running=true` 但 worker thread 已死（重启 backend 进程清状态）；要么 `getDailyStatus()` 401（`KB_CHAT_TOKEN` 已设但前端没带 Bearer 头——目前 SDK 未实现 token 注入）。
- **Run-Now 进度条卡在 ingestion 不动？**（**本轮新增**）阶段切换依赖 `kb/daily.py` 的 `[N/4] <stage>` 启动 banner 通过 `print()` 触发 `_QueueStdoutWriter` 推 SSE log → 前端切换。如果 `kb/daily.py` 改了 banner 格式但 `_STAGE_PATTERN` 没同步改，前端永远看不到 stage 帧——但 log 帧仍会持续出现（说明 pipeline 在跑），可临时通过 log 面板看进度。

---

## 十六、相关文件清单（精选）

| 路径 | 用途 |
| --- | --- |
| `frontend/AGENTS.md` | Next.js 16 必读告警 |
| `frontend/package.json` | scripts / 依赖 |
| `frontend/next.config.ts` | standalone + `/api/*` 反代 + `/search → /` 重定向 |
| `frontend/playwright.config.ts` | e2e 配置 |
| `frontend/Dockerfile` | 多阶段镜像 |
| `frontend/src/app/layout.tsx` | 根布局 + ThemeProvider + LocaleProvider + inline FOUC 脚本 + viewport.themeColor dual-mode |
| `frontend/src/app/page.tsx` | Browse / Search |
| `frontend/src/app/chat/page.tsx` | 流式多轮 RAG / source-anchored / 深链 |
| `frontend/src/app/paper/[id]/page.tsx` | 详情页 |
| `frontend/src/app/reports/page.tsx` | **本轮重写**：Run-Now 按钮 + 4-stage 进度条 + 日志面板 + 跨 tab 探测 |
| `frontend/src/app/globals.css` | **本轮重写**：`@theme inline` + oklch tokens（Cream Linen / Walnut Hearth）|
| `frontend/src/components/layout/{app-shell,header,sidebar}.tsx` | dashboard 布局；**header 加入两组 switcher**；**sidebar i18n 化** |
| `frontend/src/components/{language,theme}-switcher.tsx` | **新**：segmented control |
| `frontend/src/components/paper-card.tsx` | 列表行（含 SCORE_LABELS） |
| `frontend/src/components/source-filter.tsx` | **本轮新增**：Browse 页 source_name 多选过滤组件 |
| `frontend/src/components/chat/{chat-right-sidebar,source-picker}.tsx` | 聊天侧栏与 picker |
| `frontend/src/hooks/use-conversation-history.ts` | localStorage CRUD |
| `frontend/src/lib/api.ts` | API 客户端（含 `chat()` + `chatStream()` + **`getDailyStatus`** + **`runDailyStream`** + **`DailyConflictError`**） |
| `frontend/src/lib/types.ts` | TS 类型（含 ChatStreamEvent + **`DailyStatus`** + **`DailyStageName`** + **`DailyStreamEvent`**） |
| `frontend/src/lib/i18n/{provider.tsx,translations.ts,format.ts}` | **新**：LocaleProvider / 双语字典 / locale-aware 日期 |
| `frontend/src/lib/theme/provider.tsx` | **新**：ThemeProvider / `THEME_STORAGE_KEY` / `DEFAULT_THEME` |

---

## 十七、变更记录 (Changelog)

| 时间 | 操作 | 说明 |
| --- | --- | --- |
| 2026-04-25 09:59:45 | 初始化 | 自动生成 frontend 模块 `CLAUDE.md` |
| 2026-04-25 15:26:48 | 增量刷新 | 新增 Playwright e2e / CI / Bearer Token 警示 |
| 2026-05-02 08:57:04 | 增量刷新 | Next 16 standalone build / `/api/*` 反代 / Universal Score Axes / Docker |
| 2026-05-02 20:12:04 | 增量刷新 | 多轮 Chat + Source pin + `/chat?paperId=` 深链 + 移动端响应式 |
| 2026-05-02 21:18:53 | 增量刷新 | SSE 流式聊天 `chatStream` async generator + Stop 按钮 + `streaming` placeholder + 切换会话/卸载/deep-link 自动 abort |
| **2026-05-03 23:00:00** | **增量刷新** | **Browse 页 Source 名称多选过滤**。① **新组件 `src/components/source-filter.tsx`**：按 `source_type` 分 4 组（paper/blog/project/talk），每组可折叠（chevron 旋转 90°），tag 用 shadcn `Badge`（selected = `default` solid，unselected = `outline`），`name · count` 文本；`onClick` 切 selected 集合，`onChange(names)` 上抛父级。`typeFilter` 非空时只渲染对应组（**Decision 5**）。`testid` 命名 `source-filter` / `source-tag-{name}` 给 e2e。② **types**（`src/lib/types.ts`）：新增 `Source { name; type; count }` + `SourcesResponse { sources: Source[] }`。③ **API 客户端**（`src/lib/api.ts`）：新增 `listSources()`（`GET /api/sources`）；`listPapers` 签名扩展 `source_name?: string[]`，**前端 `.join(",")`** 后再发 query string，后端 split 成 `IN (...)`。④ **Browse 页重构**（`src/app/page.tsx::BrowseContent`）：`typeFilter` / `selectedSources` 退回 React `useState`（初始值取自 `useSearchParams()`），URL 同步**改用 `window.history.replaceState`**——**绕开 Next.js 16.2.x 已知 router cache 回归 vercel/next.js#92187**（侧栏 `<Link href="/">` prefetch 触发缓存命中后 `router.push/replace` 在"同 pathname、不同 search"导航时会**静默 no-op**）。trade-off：浏览器 back/forward 不再自动重新渲染 BrowseContent；如未来 Next 修了这个 bug 改回 `router.replace` 即可。`onTypeChange` 切 type 时**静默 drop** `selectedSources` 里 type 不匹配的条目。`fetch` 走 `useEffect([page, sortBy, sortDir, typeFilter, sourceKey, query])`，`sourceKey = selectedSources.join(",")` 是派生 primitive 给 React Compiler 通过——**不要**直接把 `selectedSources` 数组放进 deps。`?q=` 搜索模式下 SourceFilter 不渲染。⑤ **i18n keys**（`src/lib/i18n/translations.ts`）：en + zh 各加 3 条 — `browse.filter.sources` / `browse.filter.sources.expand` / `browse.filter.sources.collapse`；group label 复用既有 `browse.filter.{papers,blogs,projects,talks}`。⑥ **测试**（`frontend/tests/e2e/browse.spec.ts`）：+2 例 — `source filter tag click updates URL & list` + `switching type silently drops mismatched sources`，都 mock 了 `/api/sources` + `/api/papers` 响应；为避免 Playwright 复用旧 `next start` 实例命中陈旧代码，e2e 实例显式跑在 port 3010 + `baseURL: 'http://127.0.0.1:3010'`（`playwright.config.ts` 中），与开发用的 3000 端口隔离。⑦ **gitignore**（`frontend/.gitignore`）：新增 `/test-results/` `/playwright-report/` `/playwright/.cache/` 避免 Playwright 产物污染 git。⑧ **不影响**：theme / locale / chat / reports / stats / paper detail / 移动端响应式 / hooks / 既有 paper-card / search-bar 全部不动。所有 delta 已通过直接读取 `frontend/src/components/source-filter.tsx` / `frontend/src/app/page.tsx` / `frontend/src/lib/{api,types}.ts` / `frontend/src/lib/i18n/translations.ts` / `frontend/tests/e2e/browse.spec.ts` 源码核对。 |
| **2026-05-03 22:34:43** | **增量刷新** | **Themed i18n shell + reports 页 Run-Now SSE 进度面板**。① **i18n 模块（新）**：`src/lib/i18n/{provider.tsx,translations.ts,format.ts}`。`LocaleProvider` 用 React Context + localStorage `gpgpu-kb.locale.v1` 持久化；SSR 期间永远 `DEFAULT_LOCALE="en"`，mount 后才反水到持久化值；`useEffect` 内同步 `document.documentElement.lang`。`translations.ts` 是 `en` / `zh` 双层对象（~110 keys）+ `TranslationKey = keyof typeof translations.en`（**en 是 source of truth**）。`format.ts::formatLongDate(value, locale)` 用 `Date.toLocaleDateString(LOCALE_TAG[locale], opts)` 包成 locale-aware 长日期。`_interpolate` 仅支持 `{name}` placeholder，**不支持 ICU plurals**。② **theme 模块（新）**：`src/lib/theme/provider.tsx`。`THEME_STORAGE_KEY="gpgpu-kb.theme.v1"` / `DEFAULT_THEME="dark"` / `THEMES=["light","dark"]`。`useEffect` 同步 `document.documentElement.classList.toggle("dark", ...)`。**FOUC-prevention**：`app/layout.tsx` 头部 inline `<script dangerouslySetInnerHTML={{__html: THEME_INIT_SCRIPT}}>` 在 React 挂载前先读 localStorage 切 `<html>` class——painted body 永远不闪。这段 inline script 与 `THEME_STORAGE_KEY` 字面量都是硬编码，改时两处同步。`<html lang="en" className="dark" suppressHydrationWarning>` 静默 React 关于 class/lang mismatch 的告警。③ **新主题：Cream Linen + Walnut Hearth**（`src/app/globals.css`）：彻底替换原 `bg-zinc-950 text-zinc-100` 硬编码暗色为 oklch 双主题。`@theme inline` 把所有 shadcn 设计 token（`--color-card` / `--color-primary` / `--color-sidebar` / `--color-chart-1..5` / `--color-destructive` / 等）映射到 `:root` (Cream Linen, parchment + caramel amber + chestnut) 与 `.dark` (Walnut Hearth, walnut bark + roasted cocoa + toasted amber + oat-mist) 两套 oklch 变量。`@custom-variant dark (&:is(.dark *))` 显式声明 dark 变体。`viewport.themeColor` dual-mode 跟系统 `prefers-color-scheme` 切换地址栏 tint（与 `<html class>` 是两套独立信号）。**编码规范变更**：从此不要再用 `bg-zinc-...` 硬编码，统一用语义 token（`bg-background` / `bg-card` / `bg-sidebar` 等）。④ **AppShell 重构**（`src/components/layout/{app-shell,header,sidebar}.tsx`）：根 `layout.tsx` 包 `<ThemeProvider><LocaleProvider><AppShell>`；`AppShell` 用 React 19 的"在 render 中 derive state from path"模式（`if (pathname !== lastPath) setOpen(false)`）。`Header` 加入 `<ThemeSwitcher />` + `<LanguageSwitcher />` 两组 segmented control（pill + 滑动 thumb，`pointer-events-none` 不抢点击；ThemeSwitcher 的 thumb hydrated 前 opacity=0 防 SSR snapshot painted under wrong tab）。`Sidebar` 全部 `t("nav.*")` + 版本号读 `package.json::version`。⑤ **后端：手动触发 daily pipeline + SSE 进度（新端点，详见 `backend/CLAUDE.md`）**：`GET /api/daily/status` + `POST /api/daily/stream`，**都挂 `verify_chat_token`**；事件序列 `started → stage(≤4) → log(N) → done\|error`，15s idle 发 `: keepalive\n\n` SSE comment 帧；并发第二个 POST → HTTP 409。⑥ **前端 reports 页重写**（`src/app/reports/page.tsx`）：新增 `RunPhase = "idle"\|"starting"\|"running"\|"done"\|"error"` + `RunState`（`phase / startedAt / activeIndex / errorMessage / conflict`）。Mount 时 `getDailyStatus()` 探测他 tab in-flight run（命中则 phase=running + conflict=true，按钮永久 disable）。`handleRun` 起 `AbortController` 串到 `runDailyStream({signal})`，`for await` 跑 events；`applyEvent` switch 5 个事件（`started\|stage\|log\|error\|done`）切状态 + appendLog。`MAX_LOG_LINES=2000` 防冷启动 100k 行 OOM。终止三态：done → 刷新 reports；error → 红色 RunPanel + log 面板；AbortError → 静默（用户主动取消）。`RunPanel` 含状态 header + 4 个 `StagePill`（pending/running/done/error 四色）+ 折叠 log 面板（`<pre whitespace-pre-wrap break-words font-mono>`）+ 完成后的 Reload 按钮。`formatRelativeTime(iso, locale)` 4 桶简易实现（just now / Xm / Xh / Xd ago，对应中文）。⑦ **前端 API 客户端扩展**（`src/lib/api.ts`）：新增 `getDailyStatus()`（`GET /api/daily/status`）+ `runDailyStream({ signal? })` async generator（`POST /api/daily/stream`，body `"{}"`，`Accept: text/event-stream`）+ `DailyConflictError extends Error`（HTTP 409 时抛）+ `_parseDailyFrame`（**关键：跳过 `:` 开头的 keepalive 注释帧 + 跳过空行**，否则 `JSON.parse` 会在 keepalive 帧上 throw）。`reader.releaseLock()` 仍在 try/catch 内调（abort 后 releaseLock throws，安全 swallow）。⑧ **前端 types 扩展**（`src/lib/types.ts`）：新增 `DailyStatus { running, started_at, current_stage }` / `DailyStageName = "ingestion"\|"processing"\|"embedding"\|"report"` / `DailyStreamEvent` discriminated union（`started\|stage\|log\|error\|done`）。`Stats.top_overall` 字段不变。⑨ **i18n key 覆盖**：translations.ts 新增 `reports.run.*` 18 个 key（button / busy / startedAt / alreadyRunning / conflict / failed / connectionLost / complete / reload / viewLogs / hideLogs / logsEmpty / stage.{ingestion,processing,embedding,report}）+ `theme.{switch,light,dark}` + `lang.{switch,english,chinese}` + `shell.{openMenu,closeMenu,version}` + `nav.primary` 等 shell-level keys。所有 zh 翻译就位（暗黑/明亮 / 数据采集 / 摘要与评分 / 向量化 / 生成简报 / 立即运行流水线 / 流水线运行中…… 等）。⑩ **不影响**：`/api/chat` / `/api/chat/stream` 多轮 / source-anchored / fast-expert 双角色 / SSE 流式 chat / per-source ingest 冷启动 / sitemap blog / DB schema / migration / Docker / 已有 provider 行为全部不动。所有 delta 已通过直接读取 `frontend/src/app/reports/page.tsx` / `frontend/src/lib/api.ts` / `frontend/src/lib/types.ts` / `frontend/src/lib/i18n/{provider.tsx,translations.ts,format.ts}` / `frontend/src/lib/theme/provider.tsx` / `frontend/src/app/layout.tsx` / `frontend/src/app/globals.css` / `frontend/src/components/layout/{app-shell,header,sidebar}.tsx` / `frontend/src/components/{language-switcher,theme-switcher}.tsx` / `backend/kb/main.py` / `backend/tests/test_api_smoke.py` 源码核对。 |
