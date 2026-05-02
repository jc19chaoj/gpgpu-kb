# frontend/ — Next.js 16 / React 19 UI

[← 返回根](../CLAUDE.md) > **frontend**

> 由 `init-architect` 于 `2026-04-25 09:59:45` 自动生成，
> 于 `2026-04-25 15:26:48` 增量刷新（Playwright e2e / CI / Bearer Token 警示），
> 于 `2026-05-02 08:57:04` 增量刷新（Next 16 standalone build / `/api/*` 反向代理 / Universal Score Axes / Docker 镜像 / `/search` 永久重定向到首页），
> 于 `2026-05-02 20:12:04` 增量刷新（多轮 Chat 对话历史（localStorage 持久化）/ Source pin 锚定模式（弹窗式 SourcePicker）/ `/chat?paperId=` 深链 / 移动端响应式聊天输入条 + 安全区适配 / 错误状态 transient 标记），
> 于 **`2026-05-02 21:18:53`** 增量刷新（**SSE 流式聊天 `chatStream` async generator + Stop 按钮（`AbortController`）+ `streaming` placeholder 增量 token 渲染 + 切换会话/卸载/deep-link 自动 abort + `enterKeyHint="send"` 移动键盘提示 + `_chatPayload` 复用 + `ChatStreamEvent` discriminated union**）。
>
> ⚠️ 必读：`frontend/AGENTS.md` 提示 **这是最新版 Next.js（16.x），API 与约定可能与旧版本不同**。在写代码前先阅读 `frontend/node_modules/next/dist/docs/` 中的相应文档，留意 deprecation 提示。

---

## 一、模块职责

提供 GPGPU Knowledge Base 的浏览器 UI：

- **Browse**：分页、按类型过滤、按多维度排序的论文/博客/项目列表（默认按 `total_score`）
- **Search**：URL `?q=...` 触发，调后端语义检索，自动回退关键字搜索
- **Chat（流式）**：**多轮 RAG 对话** + **Source pin 锚定模式**（弹窗 SourcePicker 选 paper → 后端拉 PDF 全文）；**SSE 增量 token 流式渲染** + Stop 按钮（`AbortController`）；右侧 sidebar 两段 Tabs（History 列出 localStorage 中保存的会话 / Source 显示当前锚定）；**`/chat?paperId=` 深链**自动从详情页拉一篇 paper 并起新会话；移动端隐藏 sidebar 并适配 `env(safe-area-inset-bottom)`
- **Paper detail**：单条详情，含双维 0-10 分（按 `source_type` 切换标签：Originality/Impact、Depth/Actionability、Innovation/Maturity）与 rationale；可触发 "Open in Chat" 跳到 `/chat?paperId=...`
- **Reports**：每日 Markdown 报告列表与详情
- **Stats**：知识库整体统计

整套界面采用暗色主题（`bg-zinc-950 text-zinc-100`），左侧 Sidebar + 顶部 Header 的 dashboard 布局；聊天页在大屏幕上会再加一条右侧 ChatRightSidebar。

---

## 二、入口与启动

| 入口 | 作用 |
| --- | --- |
| `src/app/layout.tsx` | RootLayout：`<html className="dark">`、暗色 body、Sidebar + Header dashboard 框架 |
| `src/app/page.tsx` | `/` Browse 页（含 `?q` → search）；外层套 `<Suspense>` 容纳 `useSearchParams` |
| `src/app/chat/page.tsx` | `/chat` 多轮 **流式** RAG / source-anchored 聊天页；外层 `<Suspense>` 包 `useSearchParams("paperId")` |
| `src/app/paper/[id]/page.tsx` | `/paper/:id` 论文详情；`SCORE_LABELS` 按 `source_type` 切换显示 |
| `src/app/reports/page.tsx` / `reports/[id]/page.tsx` | 报告列表 / 详情（Markdown via `react-markdown` + `remark-gfm`）|
| `src/app/stats/page.tsx` | `/stats` 统计 |
| `src/hooks/use-conversation-history.ts` | localStorage 持久化对话（`gpgpu-kb.chat.conversations.v1`）；CRUD / hydration flag |
| `src/components/chat/chat-right-sidebar.tsx` | 右侧 sidebar（History / Source 两个 Tab） |
| `src/components/chat/source-picker.tsx` | Pick source 弹窗（防抖 300 ms 调 `searchPapers(q, semantic:false)`） |
| `next.config.ts` | **Next 16 关键配置**：`output: "standalone"` + `/api/*` 反向代理 + `/search → /` 重定向 |
| `playwright.config.ts` | e2e（chromium / `npx next start -p 3000`） |
| `Dockerfile` | 三阶段（deps / builder / runner）；非 root；`server.js` 启动 |

启动命令：

```bash
cd frontend
npm install
npm run dev          # next dev (port 3000)；同源 /api/* → backend 反代
npm run build && npm run start   # 生产构建 + standalone 启动
npm run lint         # eslint (flat config, eslint-config-next)
npx tsc --noEmit     # 类型检查
npm run test:e2e     # Playwright e2e（需先 `npx playwright install chromium`）
```

---

## 三、对外接口（前端 → 后端 API 客户端）

文件：`src/lib/api.ts`，`API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""`（默认空串走同源 `/api/*` 经 Next 反代到 backend，避免 CORS）。

| 函数 | 后端端点 | 用途 |
| --- | --- | --- |
| `listPapers(params)` | `GET /api/papers` | 列表 + 过滤/排序（`sort_by` 支持 `total_score` / `published_date` / `quality_score` / `relevance_score` 等） |
| `getPaper(id)` | `GET /api/papers/{id}` | 详情；deep-link 进 chat 时也调它解析 `?paperId=` |
| `searchPapers(q, params)` | `GET /api/papers/search` | 语义/关键字检索；SourcePicker 强制 `semantic:false` 走关键字快路径 |
| `chat(request)` | `POST /api/chat` | **非流式** RAG / source-anchored；`request` 支持 `paper_id?: number` 与 `history?: ChatMessage[]`，**通过新抽出的 `_chatPayload(request)` 清理 undefined / null 字段**后再 POST。当前聊天页**不再使用此函数**（已切到 `chatStream`），但 SDK 仍保留供脚本与未来集成 |
| **`chatStream(request, { signal? })`** | **`POST /api/chat/stream`** | **新：SSE 流式 async generator**。`response.body.getReader()` + `TextDecoder` 累积 → 按 `\n\n` 分帧 → `_parseSSEFrame` 解码为 `ChatStreamEvent` discriminated union。`Accept: text/event-stream` 头显式发送；`signal` 串到 fetch 上，外层 `AbortController` 一调 `abort()` 整条流就被取消。`finally` 内 `reader.releaseLock()` 包 try/catch（abort 后释放会 throw，安全 swallow） |
| `listReports(limit?)` | `GET /api/reports` | 报告列表 |
| `getReport(id)` | `GET /api/reports/{id}` | 报告详情 |
| `getStats()` | `GET /api/stats` | 统计（`top_overall` 是新增的跨类型 ranking） |

类型定义集中在 `src/lib/types.ts`，与后端 `kb/schemas.py` / `kb/main.py::_sse_event` 对齐：

| 字段 / 接口 | 类型 | 备注 |
| --- | --- | --- |
| `originality_score` / `impact_score` / `impact_rationale` | number / string | legacy 字段：仅 `paper` 行从 universal axes 镜像 |
| `quality_score` / `relevance_score` / `score_rationale` | number / string | universal axes（所有 source_type） |
| `Stats.top_impact` | `{id, title, impact_score}[]` | legacy paper-only Top-5 |
| `Stats.top_overall?` | `{id, title, source_type, quality_score, relevance_score}[]` | 跨类型 Top-5（`max(quality, relevance)` 排序） |
| `ChatMessage` | `{ role: "user" \| "assistant"; content: string }` | **没有 system role**——后端拒收 |
| `ChatRequest` | `{ query, top_k?, paper_id?, history? }` | `paper_id` 给定 → 后端走 source-anchored 模式；`history` 给定 → 注入 prompt |
| `ChatResponse` | `{ answer, sources: Paper[] }` | 仅非流式 `chat()` 返回；流式版本通过 SSE 帧增量 |
| **`ChatStreamEvent`** | `{type:"sources",sources}` \| `{type:"token",content}` \| `{type:"error",message}` \| `{type:"done"}` | **discriminated union**；与后端 `_sse_event(event, data)` 镜像；新增事件类型时**两侧都要加** + `_parseSSEFrame` 加解码分支 + 聊天页 `for await` 循环加 case |

> 部署到生产 / 使用 cpolar 暴露时，若后端启用了 Bearer Token 守卫，需要扩展 `fetchJSON` / `chatStream` 接受 token（建议读 `process.env.NEXT_PUBLIC_CHAT_TOKEN` 或在 server-side route handler 转发）。

---

## 四、Next.js 16 特殊配置（`next.config.ts`）

```ts
output: "standalone"  // 生成 .next/standalone/server.js，Docker runtime 只需 node_modules-free
async redirects() {
  // 旧的 /search?q=... 已并入首页
  return [{ source: "/search", destination: "/", permanent: false }];
}
async rewrites() {
  // 浏览器只跟同源说话；CORS 在 prod / cpolar / Docker 全部失效问题一并解决
  return [{ source: "/api/:path*", destination: `${KB_BACKEND_URL}/api/:path*` }];
}
```

`KB_BACKEND_URL` 默认 `http://127.0.0.1:8000`（本地 `./start.sh` 路径），在 Docker 中通过 build arg 改成 `http://backend:8000`（compose 服务 DNS）。**这是 build-time baked**——`routes-manifest.json` 在 `next build` 时定型，运行时改 env 无效。

> **keep-alive + SSE 注意**：backend 已加 `--timeout-keep-alive 75`，与 Next 默认反代连接池配合避免 ECONNRESET；SSE 流式响应（`/api/chat/stream`）**天然依赖长 keep-alive**，且任何中间反代（cpolar / nginx）都必须**关闭 `text/event-stream` 的 buffering**，否则前端只会在 `done` 之后一次性收到所有 token，丧失流式效果。后端已发 `X-Accel-Buffering: no` + `Cache-Control: no-cache` 响应头，但部分代理需要全局开关。

`Dockerfile` 三阶段：

1. `deps`：`npm ci`，缓存 lockfile 层。
2. `builder`：拷源码 → `npm run build`，产出 `.next/standalone` + `.next/static`。
3. `runner`：alpine + 非 root nodejs 用户，启动 `node server.js`，`HEALTHCHECK` 走 `http://127.0.0.1:3000/`。

---

## 五、关键依赖与配置

`package.json` 摘录：

| 依赖 | 版本 | 说明 |
| --- | --- | --- |
| `next` | 16.2.x | App Router |
| `react` / `react-dom` | 19.x | React 19 正式版 |
| `@base-ui/react` | ^1.x | shadcn/ui 底层原语（含 Tabs / Dialog） |
| `shadcn` | ^4.x | shadcn 组件 CLI |
| `class-variance-authority` / `clsx` / `tailwind-merge` | – | 样式工具链 |
| `lucide-react` | ^1.x | 图标（含 `Square` / `PinIcon`） |
| `react-markdown` + `remark-gfm` | ^10 / ^4 | 报告 / 聊天 Markdown 渲染（流式时也安全增量渲染） |
| `tailwindcss` / `@tailwindcss/postcss` | ^4 | Tailwind v4 |
| `tw-animate-css` | ^1.x | 动画扩展 |
| `eslint` + `eslint-config-next` | ^9 / 16.x | flat config Lint |
| `typescript` | ^5 | strict 模式 |
| `@playwright/test` | ^1.x | e2e 测试框架（devDep） |

### scripts（`package.json`）

| 脚本 | 命令 |
| --- | --- |
| `dev` | `next dev` |
| `build` | `next build`（产出 `.next/standalone`） |
| `start` | `next start` |
| `lint` | `eslint` |
| `test:e2e` | `playwright test` |

环境变量：

| 变量 | 用途 |
| --- | --- |
| `NEXT_PUBLIC_API_URL` | **可选**：浏览器直连 API 时的绝对 URL（baked at build time）；空串则走 Next 反代（推荐） |
| `KB_BACKEND_URL` | **build-time only**：`next.config.ts` 反代目标；本地默认 `http://127.0.0.1:8000`，Docker 中 `http://backend:8000` |
| `NEXT_PUBLIC_CHAT_TOKEN`（建议，未实现） | 若后端启用了 `KB_CHAT_TOKEN`，可通过该变量在 `api.ts` 注入 Bearer 头 |
| `NPM_REGISTRY` | Dockerfile build arg：在墙内可换 `https://registry.npmmirror.com` |

---

## 六、目录结构

```
frontend/
├─ AGENTS.md                # ⚠️ Next.js 16 警示，必读
├─ CLAUDE.md                # 本文件
├─ package.json             # scripts / 依赖（含 @playwright/test）
├─ tsconfig.json            # TS strict
├─ next.config.ts           # output: standalone + /api 反代 + /search 重定向
├─ playwright.config.ts     # e2e 配置（chromium / webServer: next start -p 3000）
├─ eslint.config.* / postcss.config.*
├─ Dockerfile               # 三阶段：deps / builder / runner
├─ .dockerignore
├─ tests/
│  └─ e2e/                  # Playwright 用例（后端在 e2e 中完全 mock）
└─ src/
   ├─ app/                  # App Router
   │  ├─ layout.tsx         # 根布局：Sidebar + Header
   │  ├─ page.tsx           # Browse / Search 入口（外层 Suspense + Client）
   │  ├─ chat/page.tsx      # 多轮流式 RAG 聊天 + source-anchored + /chat?paperId= 深链
   │  ├─ paper/[id]/page.tsx     # 论文详情：ScoreCircle + Markdown summary
   │  ├─ reports/page.tsx
   │  ├─ reports/[id]/page.tsx
   │  ├─ stats/page.tsx
   │  └─ globals.css        # Tailwind v4 入口（@import + @theme + dark variant）
   ├─ components/
   │  ├─ layout/            # Sidebar、Header
   │  ├─ ui/                # shadcn/ui 原语（button / card / dialog / badge / skeleton / input / scroll-area / tabs …）
   │  ├─ chat/              # chat 子组件
   │  │  ├─ chat-right-sidebar.tsx  # History/Source Tabs
   │  │  └─ source-picker.tsx       # Dialog + 防抖搜索
   │  ├─ paper-card.tsx     # 列表行（按 source_type 切换 SCORE_LABELS）
   │  └─ search-bar.tsx     # 搜索框（路由跳到 / + ?q=...）
   ├─ hooks/
   │  └─ use-conversation-history.ts  # localStorage CRUD + hydration flag
   └─ lib/
      ├─ api.ts             # fetch 客户端（同源默认；chat() + chatStream() + _chatPayload 复用 + _parseSSEFrame）
      ├─ types.ts           # 与后端 schemas 对齐（含 ChatMessage / ChatRequest 扩展 / ChatStreamEvent union）
      └─ utils.ts           # cn / clsx 等
```

---

## 七、Universal Score Axes（前端镜像后端）

后端 `Paper` 提供两组评分字段：

- **legacy**：`originality_score` / `impact_score` / `impact_rationale`（仅 paper 行有真实值；非 paper 行 = 0.0）
- **universal**：`quality_score` / `relevance_score` / `score_rationale`（所有 source_type）

前端在两处镜像后端 `_SCORE_LABELS` 字典：

| `source_type` | quality 标签 | relevance 标签 |
| --- | --- | --- |
| `paper` | `Originality` | `Impact` |
| `blog` | `Depth` | `Actionability` |
| `talk` | `Depth` | `Actionability` |
| `project` | `Innovation` | `Maturity` |

两处实现：

- `src/components/paper-card.tsx::SCORE_LABELS`：列表行的两条进度条。
- `src/app/paper/[id]/page.tsx::SCORE_LABELS`：详情页的双 ScoreCircle。

`_resolveScores(paper)` 的兜底逻辑（universal 优先、paper legacy 兜底；非 paper 直接读 universal）。

> 与后端 `kb/reports.py::_score_line` 三处保持一致——任何一侧改了都要同步，否则首页和详情页/日报会显示不同的分数。

---

## 八、Chat 模块（流式版本细节）

### 8.1 状态机概览

`ChatContent` 顶层状态：

- `messages: DisplayMessage[]` — 当前 session 的消息流（含 `WELCOME` 卡片）；`DisplayMessage = ChatMessage & { sources?: Paper[]; error?: boolean; streaming?: boolean }`，**`sources` / `error` / `streaming` 仅渲染用，不持久化**（通过 `_stripDisplay` 过滤）。
- `input` / `loading` — 输入框与"正在思考"骨架的 transient 状态。
- `selectedPaper: Paper | null` — 当前锚定的 source；非空时 `chatStream()` 携带 `paper_id`，placeholder 与提示也会切换。
- `pinnedPaperIdRef: useRef<number | null>` — 防止 React 19 strict-mode 双触发与 back/forward 重新 pin 同一 deep-link。
- **`abortRef: useRef<AbortController | null>`** — 当前正在进行的 SSE 流的句柄。**任何"语义上让旧流应被抛弃"的事件**（Stop 按钮 / 切换会话 / 新建会话 / `?paperId=` 深链触发新会话 / 组件卸载）都必须先 `abortRef.current?.abort()`，否则旧流的 token 会继续灌进新会话的 placeholder。

`useConversationHistory()` 返回的对象暴露：`conversations` / `activeId` / `active` / `selectConversation` / `startNew({paperId?, paperTitle?})` / `saveActive(messages, opts?)` / `deleteConversation(id)` / `clearAll()` / `hydrated`。

### 8.2 SSE 消息流四种触发路径

1. **用户发送**（`handleSend`）— 立刻把 `userMsg` + 一条空的 `streaming` placeholder push 进 messages，`chatStream()` 携带 `priorTurns = _stripDisplay(messages)`（**不含本次新加的 user/placeholder turn**——快照在 setMessages 之前拍下）。`for await (const ev of chatStream(...))` 循环：
   - `sources` → 把 sources 字段写到 placeholder 上。
   - `token` → `accumulated += ev.content`；用局部 `snapshot` 变量（**不能用闭包里的 `accumulated`**）走 `setMessages` 把 placeholder 的 `content` 增量更新。
   - `error` → 标记 `errored=true`。
   - `done` → break。
   - 异常 + `AbortError` → `aborted=true`；其它异常 → `errored=true`。

   `finally` 三态 finalize：
   - `showError = errored && !accumulated` → 红色气泡 + **不持久化**。
   - `aborted` 带部分内容 → 保留 + 持久化（匹配 ChatGPT "Stop generating" 行为）。
   - 正常 done → 持久化。

   **持久化路径用 send-start 时拍下的 `priorTurns` 快照**而不是 `_stripDisplay(messages)`，因为闭包里的 `messages` 已过期；如果用户中途切换会话，闭包还指向新会话的 history，`priorTurns` 才指向旧会话——不会跨会话泄露 turn。
2. **历史会话切换**（`useEffect [history.activeId]`）— **先 `abortRef.current?.abort()` 切断当前流**，再重置 messages 为 `[WELCOME, ...active.messages]`，恢复 selectedPaper（用最小 `Paper`-shape stub 填空，仅展示 title 与 id——sidebar 不需要打分等字段）。
3. **新建会话**（`handleNewChat`）— `abortRef.current?.abort()` → 清空 messages 到 `[WELCOME]` → 清掉 selectedPaper → `history.startNew()`。
4. **深链 `/chat?paperId=123`**（`useEffect [searchParams]`）— 拉 `getPaper(id)` → `router.replace("/chat")` → `history.startNew({ paperId, paperTitle })` → `setSelectedPaper(paper)` → `setMessages([WELCOME])`。`pinnedPaperIdRef` 守卫确保只触发一次；fetch 失败时 URL 不清，让用户看到 broken link。
5. **组件卸载** — `useEffect(() => () => abortRef.current?.abort(), [])` 确保路由切换 / tab 关闭时停止流。

### 8.3 持久化协议（`use-conversation-history.ts`）

- localStorage key：`gpgpu-kb.chat.conversations.v1`（升级 schema 时把 `v1` 改 `v2`，避免污染老数据）。
- 上限：50 条会话；超出在 `_safeWrite` 时 `slice(0, MAX_CONVERSATIONS)`。
- 排序：`updatedAt` 倒排（每次 save 后 sort）。
- SSR：`_safeRead` 在 `typeof window === "undefined"` 时返回空数组；hook 在 mount 后才 `setHydrated(true)`，sidebar 通过 `hydrated && conversations.map(...)` 防 SSR/CSR markup mismatch。
- ID 生成：`crypto.randomUUID()` 优先，老 WebView fallback 到 `Date.now()-Math.random()`。
- 标题：从首条 user 消息派生（`_deriveTitle`）；用户已自定义过的不再被覆盖。
- 守卫：`_isConversation` 校验最小字段集（`id/title/messages[]/updatedAt`）；**新增字段时务必扩展守卫**，否则旧数据被静默丢弃。

### 8.4 SourcePicker 防抖与竞态

- `SEARCH_DEBOUNCE_MS = 300`。
- `requestSeq.current` 计数器在每次 query 变更时 `++`，回调返回时校验 `seq === requestSeq.current` 防止"慢请求落地后覆盖快请求"竞态。
- 强制 `semantic:false` 走关键字搜索，避免点开 picker 等向量召回（即便 ML 依赖装了，picker 用户体验也要走关键字快路径）。
- 选中后 `onSelect(paper) → onOpenChange(false)`，由父组件 `setSelectedPaper(paper)`。

### 8.5 移动端响应式

- `<aside className="hidden lg:flex w-72 ...">` 在 `<lg` 断点直接隐藏右侧 sidebar；移动端只能从历史栏外通过深链或 New chat 工作。
- 输入条 padding 用 `pb-[max(0.75rem,env(safe-area-inset-bottom))]` 避免 iOS Home Indicator 遮挡。
- `<Input>` 在移动端 `h-10 text-base`，桌面端 `sm:h-9 sm:text-sm`，**iOS 键盘自动 zoom 阈值是 16 px → `text-base`**，防止聚焦时页面缩放。
- **`enterKeyHint="send"`**：移动键盘的 Enter 键标签变成 "Send"（而不是默认的 "Enter / Return"），强化"按 Enter 发送"的视觉提示。
- IME 守卫：`onKeyDown` 检查 `e.nativeEvent.isComposing || e.keyCode === 229` 防中日韩输入法 Enter 选词时误发消息。
- Stop 按钮（红色 `Square` 图标）在 loading 状态下替换 Send 按钮位置，`h-10 w-10 sm:h-9 sm:w-9 shrink-0`，移动端可点。

### 8.6 错误处理约定

- `chatStream()` 自身只在 fetch 非 2xx 或 abort 时 throw；SSE `error` 事件（当前后端不发）也会被 for-await 循环捕获并标记 `errored`。
- `try / finally` 把 finalize 路径统一到一处：`showError`（持久化跳过 + 红色气泡，文案 "Sorry, I couldn't process that query. Is the backend running?"）/ `aborted`（保留 partial + 持久化）/ `done`（正常持久化）。
- 错误消息 icon 用 red 而非 emerald 区分。
- 401（`KB_CHAT_TOKEN` 未带）当前同样会被吞——开 Network 面板调试或在 catch 里 `console.error(err.message)`。

### 8.7 SSE 解码（`api.ts::_parseSSEFrame`）

- 每帧形如 `event: <name>\n data: <json>\n\n`；`\n\n` 分帧由 `chatStream` 处理，`_parseSSEFrame` 处理单帧。
- **多行 `data:` 拼接**：按 SSE spec，连续的 `data:` 行用 `"\n"` 拼接（防止 LLM token 含原始换行时把两条 JSON 粘起来导致 `JSON.parse` 静默 drop frame）。
- 解码后按 `event` 字段分发到 `ChatStreamEvent` union 的对应 variant。新增事件类型时**这里要加 case，且后端 `_sse_event` + 前端 `ChatStreamEvent` 三处同步**。

---

## 九、约定与坑位

1. **Next.js 16 是最新版本**：在写任何前端代码前，先阅读 `node_modules/next/dist/docs/` 的相关章节；不要套用 Next 13/14 时代的 App Router / Route Handler / Metadata API 经验。如发现弃用提示，按其指引迁移。
2. **React 19**：`page.tsx` 中保留了 `// eslint-disable-next-line react-hooks/set-state-in-effect`（多处），标准修法是引入 SWR / React Query；当前项目刻意 keep simple，新增页面也尽量先评估"是否需要状态管理库"再下手。`pinnedPaperIdRef` + `abortRef` 模式也是 strict-mode 双触发的标准对策。
3. **Suspense 边界**：使用 `useSearchParams` 的客户端组件（如 Browse、Chat）必须包在 `<Suspense>` 中，否则 16 会编译报错（参见 `app/page.tsx` 与 `app/chat/page.tsx` 的 `Suspense` 包装）。
4. **暗色主题**：根 `<html className="… dark">`；新组件请直接走 Tailwind dark palette（zinc / emerald 强调色，**Stop 按钮专用 red-600**）。`globals.css` 用 Tailwind v4 的 `@theme inline` + oklch 调色板，**不要再写 `tailwind.config.*`**，配置都在 CSS 里。
5. **shadcn/ui 复用**：UI 原语都在 `components/ui/`，新增基础原语优先用 `npx shadcn add ...`，不要手抄重写。Tabs / Dialog 已在 chat 重构中加入。
6. **Markdown 渲染**：聊天与报告页用 `react-markdown + remark-gfm`，对 LLM 输出做受控渲染；流式 token 增量更新 placeholder 时 markdown 会逐 token 重渲（性能可接受，~50 ms 内）。**不要在不可信文本上启用 raw HTML**。
7. **聊天 history persistence**：`Conversation` 接口与 `_isConversation` 守卫必须同步演进；改 schema 时 bump localStorage key 版本号。
8. **`/search` 已并入首页**：`next.config.ts` 用 302 重定向到 `/`，新代码用 `/?q=...`；`SearchBar` 已经这么做。
9. **API_BASE 空串是新默认**：浏览器同源 `/api/*` → Next 反代 → backend；不要在新代码里硬编码 `http://localhost:8000`。
10. **`_chatPayload` 复用**：`api.ts` 里 `chat()` 与 `chatStream()` 共用 `_chatPayload(request)` 构造 body，**`paper_id: null` 与 `paper_id: 0` 也都不会被发送**（`!== null`、`!== undefined` 双重守卫）；`history.length === 0` 时不发 `history` 字段。改 payload 形状时只改这一处。
11. **role 白名单**：`ChatMessage.role` 仅 `"user" | "assistant"`；前端有任何"系统提示"需求都改成在后端 prompt 模板里硬编码（`backend/kb/main.py::_build_chat_context`）。
12. **`abortRef` 生命周期**：`finally` 内只在 `abortRef.current === controller` 时清空，避免覆盖已被新 send 替换的 controller。任何路由 / 状态切换都要先 abort，否则新会话会被旧流的 token 污染。
13. **流式 Stop 按钮 vs Send**：用 `loading` 状态条件渲染，**不要叠两个 Button 用 `display:none` 切换**（`<button type="submit">` 会跟错动作）。

---

## 十、测试与质量

- **静态检查**：`npm run lint`（ESLint 9 flat config + `eslint-config-next`）。
- **类型检查**：`npx tsc --noEmit`（CI 中强制）。
- **e2e 测试**：`npm run test:e2e` → Playwright（chromium-only）。
  - 配置：`playwright.config.ts`
    - `testDir: ./tests/e2e`、`timeout: 30000`、`baseURL: http://127.0.0.1:3000`
    - `webServer: npx next start -p 3000`（CI 中 `reuseExistingServer=false`，本地 `=true`）
    - 单 `chromium` project（基于 `devices['Desktop Chrome']`）
  - **后端在 e2e 中是 mock 的**——浏览器层面拦截 `/api/*` 请求，避免依赖真实 SQLite/ChromaDB。
  - **流式 chat 路径建议补的用例**：① mock `text/event-stream` 响应 → 验证 placeholder 增量；② Stop 按钮触发 `AbortController.abort` → 验证停在 partial 内容并持久化；③ 切换会话期间正在流 → 旧会话不受新 token 影响；④ `?paperId=` deep-link 起新会话且 URL 被清空 + selectedPaper 已设置；⑤ history sidebar 渲染 + 切换会话恢复 messages。
- **当前未配置**：jest / vitest / @testing-library；如需补单元测试推荐 vitest + @testing-library/react，对 `useConversationHistory` 的 localStorage 边界与 `_parseSSEFrame` 的多行 data 拼接尤其值得单测。

---

## 十一、CI 集成

`.github/workflows/ci.yml` 中包含两个前端 job（与 backend 并行）：

| Job | 步骤 |
| --- | --- |
| `frontend-typecheck` | `actions/setup-node@v4`（Node 20，npm cache） → `npm ci` → `npx tsc --noEmit` → `npx eslint src/` |
| `frontend-e2e` | `actions/setup-node@v4` → `npm ci` → `npx playwright install --with-deps chromium` → `npm run build` → `npm run test:e2e` |

> Playwright 浏览器二进制每次 CI 都要 `--with-deps` 安装，耗时 ~30s；本地首次 `npx playwright install chromium` 即可。

---

## 十二、Docker 镜像

`Dockerfile` 三阶段（multi-stage）：

| Stage | 作用 |
| --- | --- |
| `deps` | `node:20-alpine` + `libc6-compat` + 可选 `--build-arg NPM_REGISTRY=...`；只 `npm ci` 缓存 |
| `builder` | 拷贝 `node_modules` + 源码；接收 `--build-arg NEXT_PUBLIC_API_URL` / `KB_BACKEND_URL`；运行 `npm run build` 产出 standalone |
| `runner` | 拷贝 `.next/standalone` + `.next/static` + `public`；非 root `nextjs:nodejs`；`HEALTHCHECK` curl `http://127.0.0.1:3000/`；`CMD ["node", "server.js"]` |

`.dockerignore` 排除 `node_modules/` / `.next/` / `tests/` / `playwright.config.ts` / `*.md` 等，使 build context 最小化。

> **重要**：`NEXT_PUBLIC_API_URL` 与 `KB_BACKEND_URL` 都是 build-time baked，不要指望用 `docker run -e` 修改；任意一个变动都要 `docker compose build frontend`。
> compose 默认 `KB_BACKEND_URL=http://backend:8000`（compose 服务 DNS）；裸机 host networking 需要传 `--build-arg KB_BACKEND_URL=http://127.0.0.1:8000`。

---

## 十三、常见问题 (FAQ)

- **空白页 / `API error: 0`？** 检查后端是否运行；本地默认走 Next 反代到 `http://127.0.0.1:8000`，可在浏览器 DevTools 的 Network 看 `/api/*` 是不是 502。
- **首次搜索 / 聊天明显延迟？** 正常，后端 `EmbeddingStore` 首次需要加载 SentenceTransformer 模型（已在 FastAPI lifespan 中后台预热，多数情况下感知不到）。Source-anchored 模式首次还会触发 PDF 下载 + 抽取（5–15 秒），下次走 backend 端 `Paper.full_text` 缓存。
- **CORS 报错？** 不应该再出现——前端默认走同源 `/api/*` 反代。如果你显式设了 `NEXT_PUBLIC_API_URL=https://....`，那就要在后端 `KB_CORS_ORIGINS` 加上前端域名。
- **聊天页 token 不增量出现，等 `done` 之后才一次性显示？** 中间有反代在 buffer SSE。后端已发 `X-Accel-Buffering: no`，但 nginx / cpolar 可能需要在 location 块单独 `proxy_buffering off; proxy_cache off; proxy_read_timeout 3600;`。
- **聊天页随机 "Sorry, I couldn't process that query"？** 多半是 backend keep-alive（已修为 75 s）/ Token 守卫 / ML 依赖三者之一；按以下顺序排查：① Network 面板看 `/api/chat/stream` 状态码；② 后端是否启用 `KB_CHAT_TOKEN`（前端目前未带头）；③ 是否安装 `[ml]` extra；④ 是否额外串了反代（cpolar / nginx）但 idle timeout < 75 s。
- **Stop 按钮按了之后 UI 没停？** 检查 `abortRef.current` 是否真指向当前 controller；`finally` 里只有 `abortRef.current === controller` 才清空，防止旧 finally 把新 send 的 controller 抹掉。如果 partial 内容没保留，多半是 `accumulated` 为空时被错走 `showError` 分支了——`aborted && accumulated` 路径才会持久化 partial。
- **历史记录消失？** localStorage 被清；如果是浏览器隐私模式或 storage 配额满，hook 在 `_safeWrite` 静默 catch。**多浏览器/多设备会话不会自动同步**——这是设计而非 bug。
- **`/chat?paperId=999` 是个坏链？** fetch 失败时 URL 不会被清掉，刻意保留让用户看到 broken state；想换"安静失败"行为就在 `catch` 里加一次 `router.replace("/chat")`。
- **e2e 在 CI 失败？** 检查是否漏跑 `npm run build`（`webServer.command` 用的是 `next start`，而非 `next dev`，需先有 `.next/`）。
- **Docker 构建后浏览器仍然请求 localhost:8000？** `NEXT_PUBLIC_API_URL` 被显式设过；删 `.env` 里的对应变量并 `docker compose build frontend` 重打镜像。
- **看到 `Error: Hydration failed` 与日期或 history 相关？** 详情页用 `new Date(paper.published_date).toLocaleDateString()`，server/client locale 可能不同；history sidebar 必须等 `hydrated=true` 才渲染列表。

---

## 十四、相关文件清单（精选）

| 路径 | 用途 |
| --- | --- |
| `frontend/AGENTS.md` | Next.js 16 必读告警 |
| `frontend/package.json` | scripts / 依赖（含 `test:e2e`） |
| `frontend/next.config.ts` | standalone + `/api/*` 反代 + `/search → /` 重定向 |
| `frontend/playwright.config.ts` | e2e 配置 |
| `frontend/Dockerfile` | 多阶段镜像 |
| `frontend/.dockerignore` | 镜像 build context 黑名单 |
| `frontend/tests/e2e/` | Playwright 用例 |
| `frontend/src/app/layout.tsx` | 根布局 |
| `frontend/src/app/page.tsx` | 浏览 / 搜索 |
| `frontend/src/app/chat/page.tsx` | **流式** 多轮 RAG / source-anchored / `?paperId=` 深链 / Stop 按钮 / abort-on-switch |
| `frontend/src/app/paper/[id]/page.tsx` | 详情页（含 SCORE_LABELS / ScoreCircle） |
| `frontend/src/components/paper-card.tsx` | 列表行（含 SCORE_LABELS / ScoreBar） |
| `frontend/src/components/chat/chat-right-sidebar.tsx` | History/Source Tabs |
| `frontend/src/components/chat/source-picker.tsx` | Pick source 弹窗 |
| `frontend/src/hooks/use-conversation-history.ts` | localStorage CRUD + hydration |
| `frontend/src/lib/api.ts` | API 客户端（含 `chat()` + `chatStream()` SSE generator + `_chatPayload` + `_parseSSEFrame`） |
| `frontend/src/lib/types.ts` | TS 类型（含 ChatMessage / ChatRequest 扩展 / Stats.top_overall / **`ChatStreamEvent` union**） |
| `frontend/src/app/globals.css` | Tailwind v4 入口（`@theme inline` + oklch + dark variant） |

---

## 十五、变更记录 (Changelog)

| 时间 | 操作 | 说明 |
| --- | --- | --- |
| 2026-04-25 09:59:45 | 初始化 | 自动生成 frontend 模块 `CLAUDE.md` |
| 2026-04-25 15:26:48 | 增量刷新 | 新增 Playwright e2e 文档；新增"CI 集成"章节；标注 `/api/chat` 在后端启用 `KB_CHAT_TOKEN` 时前端尚未携带 `Authorization` 头的潜在坑 |
| 2026-05-02 08:57:04 | 增量刷新 | ① `next.config.ts` `output:"standalone"` + `/api/*` 反代 + `/search → /` 重定向；② `api.ts` 默认同源；③ Universal Score Axes UI 镜像（paper-card / paper detail）；④ Browse 默认 `sort_by=total_score`；⑤ Dockerfile 三阶段；⑥ `globals.css` Tailwind v4 入口 |
| 2026-05-02 20:12:04 | 增量刷新 | ① **多轮 Chat 历史**：新增 `src/hooks/use-conversation-history.ts`（localStorage `gpgpu-kb.chat.conversations.v1`，最多 50 条；按 `updatedAt` 倒排；SSR 守卫 + `hydrated` flag；`Conversation { id, title, paperId?, paperTitle?, messages, updatedAt }` + `_isConversation` 守卫防旧数据污染）。② **Source pin 锚定模式**：新增 `src/components/chat/chat-right-sidebar.tsx`（History/Source 两个 Tab，新建/删除/选中、清除 source、Pick source 触发对话框）+ `src/components/chat/source-picker.tsx`（Dialog + 防抖 300 ms 调 `searchPapers(q, semantic:false)`，`requestSeq.current` 防竞态）。③ **`/chat?paperId=` 深链**：从详情页跳过来时自动 `getPaper(id)` → `history.startNew({ paperId, paperTitle })` → `setSelectedPaper(paper)` → `router.replace("/chat")` 清 URL；`pinnedPaperIdRef` 防 React 19 strict-mode 双触发。④ **`src/app/chat/page.tsx` 重构**（双栏 + 移动端响应式 + IME 守卫）。⑤ **`src/lib/types.ts`**：新增 `ChatMessage`；`ChatRequest` 加 `paper_id?` / `history?`。⑥ **`src/lib/api.ts::chat`**：清理 undefined / null 字段后再 POST。 |
| **2026-05-02 21:18:53** | **增量刷新** | ① **`chatStream()` async generator（新）**（`src/lib/api.ts`）：fetch `/api/chat/stream` → `response.body.getReader()` → `TextDecoder` 累积 → 按 `\n\n` 分帧 → `_parseSSEFrame` 解码为 `ChatStreamEvent` union。`Accept: text/event-stream` 头显式发送；外层 `signal?: AbortSignal` 串到 fetch 上；`finally` 内 `reader.releaseLock()` 包 try/catch（abort 后释放会 throw，安全 swallow）。`_chatPayload(request)` 抽出供 `chat()` 与 `chatStream()` 共用，依然清理 `undefined` / `null`。`_parseSSEFrame` 按 SSE spec 用 `"\n"` 拼接连续 `data:` 行，防 LLM token 含原始换行时 JSON.parse 静默 drop。② **`ChatStreamEvent` discriminated union**（`src/lib/types.ts`）：`{type:"sources",sources}` / `{type:"token",content}` / `{type:"error",message}` / `{type:"done"}`，与后端 `_sse_event` 镜像。③ **聊天页完全重写为流式**（`src/app/chat/page.tsx`）：`DisplayMessage` 新增 `streaming?: boolean` transient 字段；`handleSend` 先 push user + 一条空 streaming placeholder，`for await (const ev of chatStream(...))` 增量灌 `accumulated` 字符串到 placeholder（用 `snapshot` 局部变量避免闭包过期）；`AbortController` 由 `abortRef` 持有，**Stop 按钮 / 切换会话 / 新建会话 / `?paperId=` deep-link 切换 / 组件卸载**全都触发 `abortRef.current?.abort()`；持久化路径用 send-start 时拍下的 `priorTurns` 快照而非闭包里的 `messages`，防止用户中途切换会话时把当前流的 turn 漏写到新会话。新增 `Stop` 按钮（红色 `Square` 图标）替换 `Send` 在 loading 状态下显示；`Input` 加 `enterKeyHint="send"` 移动键盘提示；spinner 仅在 "streaming 但 placeholder 还空"时显示，token 一开始流就让 markdown 渲染接管。错误三态 finalize：`showError`（持久化跳过 + 红色气泡）/ `aborted`（保留部分内容 + 持久化）/ `done`（正常持久化）。`_stripDisplay` 现在过滤 `error` 与 `streaming` 两类 transient 消息。④ **WELCOME 文案微调**：提示用户可在右侧 pin 一个 source（"arXiv PDFs are loaded in full"）。⑤ **`finally` 内 `abortRef.current === controller` 才清空**——避免新 send 已经替换 controller 时被旧 finally 抹掉。 |
