# frontend/ — Next.js 16 / React 19 UI

[← 返回根](../CLAUDE.md) > **frontend**

> 由 `init-architect` 于 `2026-04-25 09:59:45` 自动生成，
> 于 `2026-04-25 15:26:48` 增量刷新（Playwright e2e / CI / Bearer Token 警示），
> 于 `2026-05-02 08:57:04` 增量刷新（Next 16 standalone build / `/api/*` 反向代理 / Universal Score Axes / Docker 镜像 / `/search` 永久重定向到首页），
> 于 `2026-05-02 20:12:04` 增量刷新（多轮 Chat 对话历史（localStorage 持久化）/ Source pin 锚定模式 / `/chat?paperId=` 深链 / 移动端响应式聊天输入条 / 错误状态 transient 标记），
> 于 `2026-05-02 21:18:53` 增量刷新（**SSE 流式聊天 `chatStream` async generator + Stop 按钮（`AbortController`）+ `streaming` placeholder 增量 token 渲染 + 切换会话/卸载/deep-link 自动 abort + `enterKeyHint="send"` 移动键盘提示**）。
> 于 **`2026-05-03 22:34:43`** 增量刷新（**Themed i18n shell + reports 页 Run-Now SSE 进度面板**：详见上一版本）。
> 于 **`2026-05-06 00:04:43`** 自适应增量刷新（**docs-only re-sync, no code drift**）：本轮变更全部在 backend，前端无新增 / 无修改。已对照根 `CLAUDE.md` 与 `backend/CLAUDE.md` 关于 `Paper.full_text` 200K cap / chat prompt cap 200K / 评分用全文等修改的语义性影响：① `chat` 端拿到的 source-anchored 内容会更长，但前端不需要适配——后端裁剪在 `_SOURCE_TEXT_PROMPT_CAP` 里完成，对前端透明；② `Paper.full_text` 不出现在任何前端类型中（始终走 `paper.summary` / `paper.abstract` 显示），所以 200K cap 提升对 `paper-card.tsx` / `paper/[id]/page.tsx` 完全无感；③ 没有新 SSE 事件类型，`ChatStreamEvent` / `DailyStreamEvent` discriminated union 不动；④ 不需要新增 i18n key、不需要改 theme oklch 值。**仅刷新本文件顶部时间戳与下方 changelog 末尾追加 docs-only 条目**，所有结构 / API 客户端 / 类型 / Reports SSE 进度面板 / Browse SourceFilter / 双主题 / 双语 shell 等内容维持原状。
>
> ⚠️ 必读：`frontend/AGENTS.md` 提示 **这是最新版 Next.js（16.x），API 与约定可能与旧版本不同**。在写代码前先阅读 `frontend/node_modules/next/dist/docs/` 中的相应文档。

---

## 一、模块职责

提供 GPGPU Knowledge Base 的浏览器 UI：

- **Browse**：分页、按类型过滤、按多维度排序的论文/博客/项目列表（默认按 `total_score`）；含 SourceFilter（按 `source_type` 分组的 source_name 多选 tag）
- **Search**：URL `?q=...` 触发，调后端语义检索，自动回退关键字搜索
- **Chat（流式）**：**多轮 RAG 对话** + **Source pin 锚定模式** + **SSE 增量 token 流式渲染** + Stop 按钮 + `/chat?paperId=` 深链
- **Paper detail**：单条详情，含双维 0-10 分（按 `source_type` 切换标签）与 rationale；可触发 "Open in Chat" 跳到 `/chat?paperId=...`
- **Reports**：每日 Markdown 报告列表与详情；**"Run pipeline now"按钮 → SSE 实时进度面板**（4-stage 进度条 + 实时日志面板 + 完成后 Reload 按钮）
- **Stats**：知识库整体统计

整套界面采用**双主题**（Cream Linen light / Walnut Hearth dark，oklch 调色板）+ **双语**（en / zh），每个用户偏好都通过 localStorage 持久化（`gpgpu-kb.theme.v1` / `gpgpu-kb.locale.v1`）。`<html>` 在 SSR / first paint 永远是 `lang="en" class="dark"` 默认值，再由 `app/layout.tsx` 头部 inline `<script>` 在 React 挂载前先按 localStorage 切 `<html>` class 防 FOUC，然后 `LocaleProvider` / `ThemeProvider` 在 `useEffect` 内调和到持久化值。

---

## 二、入口与启动

| 入口 | 作用 |
| --- | --- |
| `src/app/layout.tsx` | RootLayout：`<html lang="en" className="h-full antialiased dark" suppressHydrationWarning>`、inline `THEME_INIT_SCRIPT` FOUC-prevention、`<ThemeProvider><LocaleProvider><AppShell>` 嵌套；`viewport.themeColor` dual-mode（跟系统 `prefers-color-scheme` 切换地址栏 tint） |
| `src/app/page.tsx` | `/` Browse 页（含 `?q` → search + `?type` + `?source` 多源过滤）；外层套 `<Suspense>` |
| `src/app/chat/page.tsx` | `/chat` 多轮 **流式** RAG / source-anchored 聊天页；外层 `<Suspense>` 包 `useSearchParams("paperId")` |
| `src/app/paper/[id]/page.tsx` | `/paper/:id` 论文详情；`SCORE_LABELS` 按 `source_type` 切换显示 |
| `src/app/reports/page.tsx` | 报告列表 + **"Run pipeline now" 按钮** + SSE 进度面板（4-stage `StagePill` + log 面板 with `MAX_LOG_LINES=2000` 截尾 + Reload 按钮 + 跨 tab in-flight 探测）；用 `useLocale().t(...)` 全 i18n 化 |
| `src/app/reports/[id]/page.tsx` | 报告详情（Markdown via `react-markdown` + `remark-gfm`）|
| `src/app/stats/page.tsx` | `/stats` 统计 |
| `src/lib/i18n/provider.tsx` | `LocaleProvider` + `useLocale` + `useT` Context；localStorage `gpgpu-kb.locale.v1`；SSR 期间永远 `DEFAULT_LOCALE="en"`，mount 后才反水到持久化值；`useEffect` 同步 `document.documentElement.lang = "zh-CN"\|"en"` |
| `src/lib/i18n/translations.ts` | en / zh 双语字典 ~110 keys；`TranslationKey = keyof typeof translations.en`；`{name}` / `{count}` 占位符通过 `_interpolate` 替换（**不支持 ICU plurals**） |
| `src/lib/i18n/format.ts` | `formatDate` / `formatLongDate` / `localeTag`：`Date.toLocaleDateString` 包成 locale-aware（`en-US` / `zh-CN`）|
| `src/lib/theme/provider.tsx` | `ThemeProvider` + `useTheme` Context；`THEME_STORAGE_KEY = "gpgpu-kb.theme.v1"`；`DEFAULT_THEME = "dark"`；`useEffect` 同步 `document.documentElement.classList.toggle("dark", ...)` |
| `src/components/layout/app-shell.tsx` | Sidebar + Header dashboard 布局；React 19 "在 render 中 derive state from path" 模式（`if (pathname !== lastPath) setOpen(false)`，避免 useEffect 副作用） |
| `src/components/layout/sidebar.tsx` | 全部走 `t("nav.*")` + 版本号读 `package.json::version` |
| `src/components/layout/header.tsx` | `<ThemeSwitcher />` + `<LanguageSwitcher />` segmented control |
| `src/components/theme-switcher.tsx` | Sun/Moon segmented control，pill + 滑动 thumb（`style={{ left: \`${activeIndex * 1.75}rem\` }}`）；hydrated 前 thumb opacity=0 防 SSR snapshot painted under wrong tab |
| `src/components/language-switcher.tsx` | EN / 中 segmented control，与 ThemeSwitcher 视觉对称 |
| `src/components/source-filter.tsx` | Browse 页 `source_name` 多选 tag 过滤组件（按 `source_type` 分组折叠） |
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
| `listSources()` | `GET /api/sources` | 浏览页 SourceFilter 数据源；返回 `{ sources: Source[] }`，每条 `{ name, type, count }` |
| `getPaper(id)` | `GET /api/papers/{id}` | 详情；deep-link 进 chat 时也调它解析 `?paperId=` |
| `searchPapers(q, params)` | `GET /api/papers/search` | 语义/关键字检索；SourcePicker 强制 `semantic:false` |
| `chat(request)` | `POST /api/chat` | **非流式** RAG / source-anchored；通过 `_chatPayload(request)` 清理 undefined / null 后再 POST |
| `chatStream(request, { signal? })` | `POST /api/chat/stream` | **SSE 流式 async generator**。`response.body.getReader()` + `TextDecoder` 累积 → 按 `\n\n` 分帧 → `_parseSSEFrame` 解码为 `ChatStreamEvent` discriminated union |
| `getDailyStatus()` | `GET /api/daily/status` | 返回 `{ running, started_at, current_stage }` 快照。`/reports` 页 mount 时调用，决定 Run-Now 按钮的初始 enabled/disabled 状态——避免他 tab 已经在跑时本 tab 还允许发出第二个 POST 拿 409 |
| `runDailyStream({ signal? })` | `POST /api/daily/stream` | **SSE 流式 async generator**，与 `chatStream` 对称。`Accept: text/event-stream`，body `"{}"`；`_parseDailyFrame` 解码（**注意：跳过 `:` keepalive 注释帧**）；HTTP 409 → 抛 **`DailyConflictError`**（专用错误类，前端在 catch 内识别这个类型并切到 "another run in progress" UI）。**取消 fetch 不会 abort 服务端 pipeline**——daemon thread 会跑完 |
| `listReports(limit?)` | `GET /api/reports` | 报告列表 |
| `getReport(id)` | `GET /api/reports/{id}` | 报告详情 |
| `getStats()` | `GET /api/stats` | 统计 |

类型定义集中在 `src/lib/types.ts`（mirror 后端 `kb/schemas.py` + `kb/main.py::_sse_event`）：

| 字段 / 接口 | 类型 | 备注 |
| --- | --- | --- |
| `originality_score` / `impact_score` / `impact_rationale` | number / string | legacy 字段 |
| `quality_score` / `relevance_score` / `score_rationale` | number / string | universal axes |
| `Stats.top_overall?` | `{id, title, source_type, quality_score, relevance_score}[]` | 跨类型 Top-5 |
| `ChatMessage` | `{ role: "user" \| "assistant"; content: string }` | 没有 system role |
| `ChatRequest` | `{ query, top_k?, paper_id?, history? }` | – |
| `ChatStreamEvent` | discriminated union `sources \| token \| error \| done` | 与后端 `_sse_event` 镜像 |
| `Source` | `{ name: string; type: string; count: number }` | `type` 与后端 `SourceType` enum value 镜像（`"paper" \| "blog" \| "project" \| "talk"`） |
| `SourcesResponse` | `{ sources: Source[] }` | `listSources()` 返回值 |
| `DailyStatus` | `{ running: boolean; started_at: string \| null; current_stage: DailyStageName \| null }` | `getDailyStatus()` 返回值 |
| `DailyStageName` | `"ingestion" \| "processing" \| "embedding" \| "report"` | 与后端 `_STAGE_NAMES` 镜像 |
| `DailyStreamEvent` | discriminated union `started \| stage \| log \| error \| done` | `runDailyStream()` yield 的事件；`stage` 含 `index: 1\|2\|3\|4` 与 `name: DailyStageName`；与后端 `_sse_event` 镜像，新增事件类型时**两侧都要加**且更新 `_parseDailyFrame` |

> 部署到生产 / 使用 cpolar 暴露时，若后端启用了 Bearer Token 守卫，需要扩展 `fetchJSON` / `chatStream` / `getDailyStatus` / `runDailyStream` 接受 token——这两个 daily 端点也受 `verify_chat_token` 守卫。

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

> **keep-alive + SSE 注意**：backend 已加 `--timeout-keep-alive 75`；SSE 流式响应（`/api/chat/stream` 与 `/api/daily/stream`）天然依赖长 keep-alive。任何中间反代（cpolar / nginx）都必须**关闭 `text/event-stream` 的 buffering**。后端发 `X-Accel-Buffering: no` + `Cache-Control: no-cache`；nginx 还需要 `proxy_buffering off; proxy_read_timeout 3600;`（daily pipeline 整个跑完可能 30+ 分钟）。

---

## 五、关键依赖与配置

`package.json` 摘录（无新增依赖；i18n / theme 全用 React Context + localStorage 自实现）：

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
   │  ├─ reports/page.tsx   # Run-Now 按钮 + SSE 进度面板
   │  ├─ reports/[id]/page.tsx
   │  ├─ stats/page.tsx
   │  └─ globals.css        # @theme inline + oklch tokens（:root = Cream Linen, .dark = Walnut Hearth）
   ├─ components/
   │  ├─ layout/
   │  │  ├─ app-shell.tsx
   │  │  ├─ sidebar.tsx
   │  │  └─ header.tsx
   │  ├─ ui/                # shadcn/ui 原语
   │  ├─ chat/              # chat 子组件
   │  ├─ paper-card.tsx
   │  ├─ search-bar.tsx
   │  ├─ source-filter.tsx
   │  ├─ language-switcher.tsx
   │  └─ theme-switcher.tsx
   ├─ hooks/
   │  └─ use-conversation-history.ts
   └─ lib/
      ├─ api.ts             # 含 chat() + chatStream() + getDailyStatus + runDailyStream + DailyConflictError + _parseDailyFrame
      ├─ types.ts           # 含 ChatStreamEvent + DailyStatus + DailyStageName + DailyStreamEvent
      ├─ utils.ts           # cn / clsx
      ├─ i18n/              # LocaleProvider / 双语字典 / locale-aware 日期
      │  ├─ provider.tsx
      │  ├─ translations.ts
      │  └─ format.ts
      └─ theme/             # ThemeProvider / THEME_STORAGE_KEY / DEFAULT_THEME
         └─ provider.tsx
```

---

## 七、Universal Score Axes（前端镜像后端，不变）

详见上一轮文档。

---

## 八、Chat 模块（流式版本细节，不变）

详见上一轮文档（`chatStream` async generator / `abortRef` / `streaming` placeholder / `_chatPayload` / `_parseSSEFrame`）。

---

## 八.5、Browse 页 SourceFilter（不变）

详见上一轮文档（按 `source_type` 分 4 组、`window.history.replaceState` 绕过 Next 16.2.x router cache 回归）。

---

## 九、Themed i18n shell（不变）

详见上一轮文档（i18n / theme / oklch 双主题 / FOUC-prevention / LanguageSwitcher / ThemeSwitcher）。

---

## 十、Reports 页 Run-Now 按钮 + SSE 进度面板（不变）

详见上一轮文档（`RunPhase` 状态机 / `getDailyStatus()` 跨 tab 探测 / `handleRun` / `applyEvent` / `appendLog` MAX_LOG_LINES / `_parseDailyFrame` 跳 keepalive 注释）。

---

## 十一、约定与坑位

1. **Next.js 16 是最新版本**：先读 `node_modules/next/dist/docs/`。
2. **React 19**：在 effect 内 setState 会被 flag；当前项目刻意 keep simple。`pinnedPaperIdRef` + `abortRef` + `AppShell::lastPath` 都是 strict-mode / render-derived state 的标准对策。
3. **Suspense 边界**：使用 `useSearchParams` 必须包 `<Suspense>`。
4. **双主题 + oklch**：新组件用语义 token（`bg-background` / `bg-card` / `bg-sidebar` 等），不要硬编码 `bg-zinc-...`。新颜色加进 `globals.css` 的 `:root` 与 `.dark` 两组 oklch 变量。`globals.css` 用 Tailwind v4 的 `@theme inline`，**不要再写 `tailwind.config.*`**。
5. **i18n 全量化**：新组件不要写裸字符串字面量，全部走 `useT()`。新加 key 在 `en` + `zh` 两侧同步加；`TranslationKey` 类型自动校验 `t(...)` 调用。`{name}` placeholder 用 `_interpolate`，**无 ICU plurals**。
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
16. **新加 SSE 长任务端点**（pattern）：① 后端必须 `dependencies=[Depends(verify_chat_token)]` + `_DailyRunState` 同款 try_start/lock/409；② 必须发 15s SSE keepalive 注释帧；③ 前端解码函数必须跳过 `:` 注释帧；④ event union + types.ts + 后端 `_sse_event` 同步加分支；⑤ Reports 页 `applyEvent` switch 新增事件 case；⑥ stage 检测正则 `r"\[([1-4])/4\]"` 是和 `kb/daily.py` banner 格式硬约定。
17. **跨 tab 任务探测**：要不要 mount 时调 `/api/<task>/status` 取决于"任务能否被多个 client 同时观察"——daily pipeline 不能 reattach 流，所以 `/reports` 页 mount 时 `getDailyStatus()` 仅用于"显示按钮 disabled + 'running since X'"文案，不试图重连。新增类似端点请遵循同款"探测但不 reattach"模式。

---

## 十二、测试与质量

- **静态检查**：`npm run lint` / `npx tsc --noEmit`。
- **e2e 测试**：`npm run test:e2e` → Playwright（chromium-only）。
  - **流式 chat 路径建议补的用例**：① mock `text/event-stream` → placeholder 增量；② Stop 按钮 abort → partial 持久化；③ 切换会话期间正在流；④ deep-link 起新会话且 URL 被清空。
  - **建议补的用例**：⑤ Reports 页 Run-Now 按钮 → mock `runDailyStream` 发 4-stage 序列 → 验证 4 个 `StagePill` 切换；⑥ HTTP 409 → conflict UI；⑦ `getDailyStatus().running=true` mount 时按钮锁住；⑧ 切语言 → header / sidebar 文案立即跟进；⑨ 切主题 → `<html>` class 切换 + 颜色不闪。
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
- **首次访问页面闪了一下白色？** 多半是 `THEME_INIT_SCRIPT` 没成功执行（隐私模式 / CSP 禁 inline script）。检查浏览器 Console 看是否有 CSP 报错；后端 / 反代 `Content-Security-Policy: script-src 'unsafe-inline'` 是必须的（或者改 nonce 模式但 layout.tsx 也要改）。
- **切语言后部分文案没变？** 排查 ① 该文案是否硬编码字面量没走 `useT()`；② 该 key 是否在 `zh` 字典里漏了（`useT()(missingKey)` 回退到 key 字面量）；③ 该文案是否来自后端 API（如 `daily_reports.title` / `paper.summary` 是 LLM 输出，由 `KB_LANGUAGE` 在生成时定型，前端 locale 切不动它——是设计而非 bug）。
- **切主题后某些组件颜色没变？** 多半是组件用了硬编码 `bg-zinc-...` / `text-zinc-...` 而非语义 token。改用 `bg-background` / `bg-card` / `text-foreground` 等。
- **Reports 页 "Run pipeline now" 按钮永远 disabled？** 要么 `_DailyRunState._running=true` 但 worker thread 已死（重启 backend 进程清状态）；要么 `getDailyStatus()` 401（`KB_CHAT_TOKEN` 已设但前端没带 Bearer 头——目前 SDK 未实现 token 注入）。
- **Run-Now 进度条卡在 ingestion 不动？** 阶段切换依赖 `kb/daily.py` 的 `[N/4] <stage>` 启动 banner 通过 `print()` 触发 `_QueueStdoutWriter` 推 SSE log → 前端切换。如果 `kb/daily.py` 改了 banner 格式但 `_STAGE_PATTERN` 没同步改，前端永远看不到 stage 帧——但 log 帧仍会持续出现（说明 pipeline 在跑），可临时通过 log 面板看进度。

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
| `frontend/src/app/reports/page.tsx` | Run-Now 按钮 + 4-stage 进度条 + 日志面板 + 跨 tab 探测 |
| `frontend/src/app/globals.css` | `@theme inline` + oklch tokens（Cream Linen / Walnut Hearth）|
| `frontend/src/components/layout/{app-shell,header,sidebar}.tsx` | dashboard 布局 |
| `frontend/src/components/{language,theme}-switcher.tsx` | segmented control |
| `frontend/src/components/paper-card.tsx` | 列表行（含 SCORE_LABELS） |
| `frontend/src/components/source-filter.tsx` | Browse 页 source_name 多选过滤组件 |
| `frontend/src/components/chat/{chat-right-sidebar,source-picker}.tsx` | 聊天侧栏与 picker |
| `frontend/src/hooks/use-conversation-history.ts` | localStorage CRUD |
| `frontend/src/lib/api.ts` | API 客户端（含 `chat()` + `chatStream()` + `getDailyStatus` + `runDailyStream` + `DailyConflictError`） |
| `frontend/src/lib/types.ts` | TS 类型（含 ChatStreamEvent + `DailyStatus` + `DailyStageName` + `DailyStreamEvent`） |
| `frontend/src/lib/i18n/{provider.tsx,translations.ts,format.ts}` | LocaleProvider / 双语字典 / locale-aware 日期 |
| `frontend/src/lib/theme/provider.tsx` | ThemeProvider / `THEME_STORAGE_KEY` / `DEFAULT_THEME` |

---

## 十七、变更记录 (Changelog)

| 时间 | 操作 | 说明 |
| --- | --- | --- |
| 2026-04-25 09:59:45 | 初始化 | 自动生成 frontend 模块 `CLAUDE.md` |
| 2026-04-25 15:26:48 | 增量刷新 | 新增 Playwright e2e / CI / Bearer Token 警示 |
| 2026-05-02 08:57:04 | 增量刷新 | Next 16 standalone build / `/api/*` 反代 / Universal Score Axes / Docker |
| 2026-05-02 20:12:04 | 增量刷新 | 多轮 Chat + Source pin + `/chat?paperId=` 深链 + 移动端响应式 |
| 2026-05-02 21:18:53 | 增量刷新 | SSE 流式聊天 `chatStream` async generator + Stop 按钮 + `streaming` placeholder + 切换会话/卸载/deep-link 自动 abort |
| **2026-05-03 23:00:00** | **增量刷新** | **Browse 页 Source 名称多选过滤**（详见上一版本：source-filter 组件 / `?type` + `?source` URL state / `window.history.replaceState` 绕 Next 16.2.x router cache 回归） |
| **2026-05-03 22:34:43** | **增量刷新** | **Themed i18n shell + reports 页 Run-Now SSE 进度面板**（详见上一版本：i18n/theme 模块 / Cream Linen + Walnut Hearth oklch / FOUC-prevention / RunState 状态机 / `getDailyStatus` 跨 tab 探测 / `runDailyStream` async generator + `DailyConflictError` / `_parseDailyFrame` 跳 keepalive 注释 / `MAX_LOG_LINES=2000`） |
| **2026-05-06 00:04:43** | **自适应增量刷新（docs-only re-sync）** | **前端无代码变更**。本轮所有改动在 backend（`kb/processing/fulltext.py` / `kb/scripts/backfill_full_text.py` / `Dockerfile INSTALL_EXTRAS=all` 默认 / `[fulltext]` + `[all]` extras / 评分用全文 / chat prompt cap 200K），均不涉及前端：① `_SOURCE_TEXT_PROMPT_CAP=200K` 是 backend prompt 端的裁剪上限，对前端 chat / chatStream payload 完全透明；② `Paper.full_text` 不出现在任何前端 type 中（前端始终读 `paper.summary` / `paper.abstract` / `score_rationale`），200K cap 的提升对 `paper-card.tsx` / `paper/[id]/page.tsx` 无感；③ `prefetch_pending_full_text` 是采集尾步骤的服务端逻辑，前端 `/reports` 页 SSE 进度面板按既有契约消费 stage 帧即可，无新事件类型；④ 没有新 SSE 事件类型，`ChatStreamEvent` / `DailyStreamEvent` discriminated union 不动；⑤ 不需要新增 i18n key，不需要改 theme oklch 值。**仅刷新本文件顶部时间戳与本条 changelog**，所有结构 / API 客户端 / 类型 / Reports SSE 进度面板 / Browse SourceFilter / 双主题 / 双语 shell 维持原状。 |
