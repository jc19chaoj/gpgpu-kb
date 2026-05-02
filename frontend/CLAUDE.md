# frontend/ — Next.js 16 / React 19 UI

[← 返回根](../CLAUDE.md) > **frontend**

> 由 `init-architect` 于 `2026-04-25 09:59:45` 自动生成，
> 于 `2026-04-25 15:26:48` 增量刷新（Playwright e2e / CI / Bearer Token 警示），
> 于 **`2026-05-02 08:57:04`** 增量刷新（**Next 16 standalone build / `/api/*` 反向代理 / Universal Score Axes（Depth/Actionability/Innovation/Maturity 等）/ Docker 镜像 / `/search` 永久重定向到首页**）。
>
> ⚠️ 必读：`frontend/AGENTS.md` 提示 **这是最新版 Next.js（16.x），API 与约定可能与旧版本不同**。在写代码前先阅读 `frontend/node_modules/next/dist/docs/` 中的相应文档，留意 deprecation 提示。

---

## 一、模块职责

提供 GPGPU Knowledge Base 的浏览器 UI：

- **Browse**：分页、按类型过滤、按多维度排序的论文/博客/项目列表（默认按 `total_score`）
- **Search**：URL `?q=...` 触发，调后端语义检索，自动回退关键字搜索
- **Chat**：RAG 对话页，调用 `/api/chat`，展示来源徽章并跳转详情
- **Paper detail**：单条详情，含双维 0-10 分（按 `source_type` 切换标签：Originality/Impact、Depth/Actionability、Innovation/Maturity）与 rationale
- **Reports**：每日 Markdown 报告列表与详情
- **Stats**：知识库整体统计

整套界面采用暗色主题（`bg-zinc-950 text-zinc-100`），左侧 Sidebar + 顶部 Header 的 dashboard 布局。

---

## 二、入口与启动

| 入口 | 作用 |
| --- | --- |
| `src/app/layout.tsx` | RootLayout：`<html className="dark">`、暗色 body、Sidebar + Header dashboard 框架 |
| `src/app/page.tsx` | `/` Browse 页（含 `?q` → search）；外层套 `<Suspense>` 容纳 `useSearchParams` |
| `src/app/chat/page.tsx` | `/chat` RAG 对话页 |
| `src/app/paper/[id]/page.tsx` | `/paper/:id` 论文详情；`SCORE_LABELS` 按 `source_type` 切换显示 |
| `src/app/reports/page.tsx` / `reports/[id]/page.tsx` | 报告列表 / 详情（Markdown via `react-markdown` + `remark-gfm`）|
| `src/app/stats/page.tsx` | `/stats` 统计 |
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

文件：`src/lib/api.ts`，**`API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""`**（默认空串走同源 `/api/*` 经 Next 反代到 backend，避免 CORS）。

| 函数 | 后端端点 | 用途 |
| --- | --- | --- |
| `listPapers(params)` | `GET /api/papers` | 列表 + 过滤/排序（`sort_by` 支持 `total_score` / `published_date` / `quality_score` / `relevance_score` 等） |
| `getPaper(id)` | `GET /api/papers/{id}` | 详情 |
| `searchPapers(q, params)` | `GET /api/papers/search` | 语义/关键字检索 |
| `chat(request)` | `POST /api/chat` | RAG 对话；**若后端开启了 `KB_CHAT_TOKEN`，需要在 `fetchJSON` 的 `headers` 中追加 `Authorization: Bearer <token>`，当前默认实现未带** |
| `listReports(limit?)` | `GET /api/reports` | 报告列表 |
| `getReport(id)` | `GET /api/reports/{id}` | 报告详情 |
| `getStats()` | `GET /api/stats` | 统计（`top_overall` 是新增的跨类型 ranking） |

类型定义集中在 `src/lib/types.ts`，与后端 `kb/schemas.py` 对齐：

| 字段 | 类型 | 备注 |
| --- | --- | --- |
| `originality_score` / `impact_score` / `impact_rationale` | number / string | **legacy 字段**：仅 `paper` 行从 universal axes 镜像 |
| **`quality_score`** / **`relevance_score`** / **`score_rationale`** | number / string | **universal axes**（所有 source_type） |
| `Stats.top_impact` | `{id, title, impact_score}[]` | legacy paper-only Top-5 |
| `Stats.top_overall?` | `{id, title, source_type, quality_score, relevance_score}[]` | **新增**：跨类型 Top-5（`max(quality, relevance)` 排序） |

> 部署到生产 / 使用 cpolar 暴露时，若后端启用了 Bearer Token 守卫，需要扩展 `fetchJSON` 接受 token（建议读 `process.env.NEXT_PUBLIC_CHAT_TOKEN` 或在 server-side route handler 转发）。

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

`Dockerfile` 三阶段：

1. `deps`：`npm ci`，缓存 lockfile 层。
2. `builder`：拷源码 → `npm run build`，产出 `.next/standalone` + `.next/static`。
3. `runner`：alpine + 非 root nodejs 用户，启动 `node server.js`，`HEALTHCHECK` 走 `http://127.0.0.1:3000/`。

---

## 五、关键依赖与配置

`package.json` 摘录：

| 依赖 | 版本 | 说明 |
| --- | --- | --- |
| `next` | 16.2.4 | App Router |
| `react` / `react-dom` | 19.2.4 | React 19 正式版 |
| `@base-ui/react` | ^1.4.1 | shadcn/ui 底层原语 |
| `shadcn` | ^4.4.0 | shadcn 组件 CLI |
| `class-variance-authority` / `clsx` / `tailwind-merge` | – | 样式工具链 |
| `lucide-react` | ^1.11.0 | 图标 |
| `react-markdown` + `remark-gfm` | ^10 / ^4 | 报告 / 聊天 Markdown 渲染 |
| `tailwindcss` / `@tailwindcss/postcss` | ^4 | Tailwind v4 |
| `tw-animate-css` | ^1.4.0 | 动画扩展 |
| `eslint` + `eslint-config-next` | ^9 / 16.2.4 | flat config Lint |
| `typescript` | ^5 | strict 模式 |
| `@playwright/test` | ^1.59.1 | e2e 测试框架（devDep） |

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
├─ .dockerignore            # 排除 node_modules / .next / tests / playwright.config.ts
├─ tests/
│  └─ e2e/                  # Playwright 用例（后端在 e2e 中完全 mock）
└─ src/
   ├─ app/                  # App Router
   │  ├─ layout.tsx         # 根布局：Sidebar + Header
   │  ├─ page.tsx           # Browse / Search 入口（外层 Suspense + Client）
   │  ├─ chat/page.tsx      # RAG 聊天
   │  ├─ paper/[id]/page.tsx     # 论文详情：ScoreCircle + Markdown summary
   │  ├─ reports/page.tsx
   │  ├─ reports/[id]/page.tsx
   │  ├─ stats/page.tsx
   │  └─ globals.css        # Tailwind v4 入口（@import + @theme + dark variant）
   ├─ components/
   │  ├─ layout/            # Sidebar、Header
   │  ├─ ui/                # shadcn/ui 原语（button / card / dialog / badge / skeleton / input / scroll-area …）
   │  ├─ paper-card.tsx     # 列表行（按 source_type 切换 SCORE_LABELS）
   │  └─ search-bar.tsx     # 搜索框（路由跳到 / + ?q=...）
   └─ lib/
      ├─ api.ts             # fetch 客户端（API_BASE 默认空串走同源反代）
      ├─ types.ts           # 与后端 schemas 对齐（含 universal axes + top_overall）
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

`_resolveScores(paper)` 的兜底逻辑：

```ts
if (paper.source_type === "paper") {
  // 旧 paper 行可能 quality_score=0 而 originality_score 有值
  return {
    quality:   paper.quality_score   || paper.originality_score,
    relevance: paper.relevance_score || paper.impact_score,
  };
}
return { quality: paper.quality_score, relevance: paper.relevance_score };
```

> 与后端 `kb/reports.py::_score_line` 三处保持一致——任何一侧改了都要同步，否则首页和详情页/日报会显示不同的分数。
> 详情页同理：`paper.score_rationale || paper.impact_rationale` 兜底。

---

## 八、约定与坑位

1. **Next.js 16 是最新版本**：在写任何前端代码前，先阅读 `node_modules/next/dist/docs/` 的相关章节；不要套用 Next 13/14 时代的 App Router / Route Handler / Metadata API 经验。如发现弃用提示，按其指引迁移。
2. **React 19**：`page.tsx` 中保留了 `// eslint-disable-next-line react-hooks/set-state-in-effect`，标准修法是引入 SWR / React Query；当前项目刻意 keep simple，新增页面也尽量先评估"是否需要状态管理库"再下手。
3. **Suspense 边界**：使用 `useSearchParams` 的客户端组件（如 Browse）必须包在 `<Suspense>` 中，否则 16 会编译报错（参见 `app/page.tsx` 的 `BrowsePage` 包装）。
4. **暗色主题**：根 `<html className="… dark">`；新组件请直接走 Tailwind dark palette（zinc / emerald 强调色）。`globals.css` 用 Tailwind v4 的 `@theme inline` + oklch 调色板，**不要再写 `tailwind.config.*`**，配置都在 CSS 里。
5. **shadcn/ui 复用**：UI 原语都在 `components/ui/`，新增基础原语优先用 `npx shadcn add ...`，不要手抄重写。
6. **Markdown 渲染**：聊天与报告页用 `react-markdown + remark-gfm`，对 LLM 输出做受控渲染；不要在不可信文本上启用 raw HTML。
7. **聊天页错误吞掉**：`chat/page.tsx` 用 `try/catch` 把后端 4xx/5xx 一律转成 "Sorry, I couldn't process that query"；若后端开启了 `KB_CHAT_TOKEN` 而前端未带头，会一直显示该提示而非 401，**调试时请打开 Network 面板**或在 catch 中记录 `err.message`。
8. **`/search` 已并入首页**：`next.config.ts` 用 302 重定向到 `/`，新代码用 `/?q=...`；`SearchBar` 已经这么做。
9. **API_BASE 空串是新默认**：浏览器同源 `/api/*` → Next 反代 → backend；不要在新代码里硬编码 `http://localhost:8000`。

---

## 九、测试与质量

- **静态检查**：`npm run lint`（ESLint 9 flat config + `eslint-config-next`）。
- **类型检查**：`npx tsc --noEmit`（CI 中强制）。
- **e2e 测试**：`npm run test:e2e` → Playwright（chromium-only）。
  - 配置：`playwright.config.ts`
    - `testDir: ./tests/e2e`、`timeout: 30000`、`baseURL: http://127.0.0.1:3000`
    - `webServer: npx next start -p 3000`（CI 中 `reuseExistingServer=false`，本地 `=true`）
    - 单 `chromium` project（基于 `devices['Desktop Chrome']`）
  - **后端在 e2e 中是 mock 的**——浏览器层面拦截 `/api/*` 请求，避免依赖真实 SQLite/ChromaDB。
- **当前未配置**：jest / vitest / @testing-library；如需补单元测试推荐 vitest + @testing-library/react。

---

## 十、CI 集成

`.github/workflows/ci.yml` 中包含两个前端 job（与 backend 并行）：

| Job | 步骤 |
| --- | --- |
| `frontend-typecheck` | `actions/setup-node@v4`（Node 20，npm cache） → `npm ci` → `npx tsc --noEmit` → `npx eslint src/` |
| `frontend-e2e` | `actions/setup-node@v4` → `npm ci` → `npx playwright install --with-deps chromium` → `npm run build` → `npm run test:e2e` |

> Playwright 浏览器二进制每次 CI 都要 `--with-deps` 安装，耗时 ~30s；本地首次 `npx playwright install chromium` 即可。

---

## 十一、Docker 镜像

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

## 十二、常见问题 (FAQ)

- **空白页 / `API error: 0`？** 检查后端是否运行；本地默认走 Next 反代到 `http://127.0.0.1:8000`，可在浏览器 DevTools 的 Network 看 `/api/*` 是不是 502。
- **首次搜索 / 聊天明显延迟？** 正常，后端 `EmbeddingStore` 首次需要加载 SentenceTransformer 模型（已在 FastAPI lifespan 中后台预热，多数情况下感知不到）。
- **CORS 报错？** 不应该再出现——前端默认走同源 `/api/*` 反代。如果你显式设了 `NEXT_PUBLIC_API_URL=https://....`，那就要在后端 `KB_CORS_ORIGINS` 加上前端域名。
- **聊天页一直 "Sorry, I couldn't process that query"？** 排查顺序：① 后端是否运行；② 后端是否启用 `KB_CHAT_TOKEN`（如启用，前端目前未带头）；③ 是否安装 `[ml]` extra（无 ML 依赖时会拿不到 sources，但答案应可生成）。
- **e2e 在 CI 失败？** 检查是否漏跑 `npm run build`（`webServer.command` 用的是 `next start`，而非 `next dev`，需先有 `.next/`）。
- **Docker 构建后浏览器仍然请求 localhost:8000？** `NEXT_PUBLIC_API_URL` 被显式设过；删 `.env` 里的对应变量并 `docker compose build frontend` 重打镜像。
- **看到 `Error: Hydration failed` 与日期相关？** 详情页用 `new Date(paper.published_date).toLocaleDateString()`，服务器和客户端 locale 可能不同；如严格要求一致，改用 `paper.published_date.slice(0, 10)`。

---

## 十三、相关文件清单（精选）

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
| `frontend/src/app/chat/page.tsx` | RAG 聊天 |
| `frontend/src/app/paper/[id]/page.tsx` | 详情页（含 SCORE_LABELS / ScoreCircle） |
| `frontend/src/components/paper-card.tsx` | 列表行（含 SCORE_LABELS / ScoreBar） |
| `frontend/src/lib/api.ts` | API 客户端（同源默认） |
| `frontend/src/lib/types.ts` | TS 类型（含 universal axes + Stats.top_overall） |
| `frontend/src/app/globals.css` | Tailwind v4 入口（`@theme inline` + oklch + dark variant） |

---

## 十四、变更记录 (Changelog)

| 时间 | 操作 | 说明 |
| --- | --- | --- |
| 2026-04-25 09:59:45 | 初始化 | 自动生成 frontend 模块 `CLAUDE.md` |
| 2026-04-25 15:26:48 | 增量刷新 | 新增 Playwright e2e 文档（`playwright.config.ts` / `tests/e2e/` / `npm run test:e2e` / `@playwright/test` devDep）；新增"CI 集成"章节；标注 `/api/chat` 在后端启用 `KB_CHAT_TOKEN` 时前端尚未携带 `Authorization` 头的潜在坑 |
| **2026-05-02 08:57:04** | **增量刷新** | ① **`next.config.ts` 改造**：`output: "standalone"`（Docker runtime 镜像极简）；`/api/*` 反向代理到 `KB_BACKEND_URL`（默认 `http://127.0.0.1:8000`，Docker 中 `http://backend:8000`）；`/search → /` 302 重定向。② **`api.ts` 默认走同源**：`API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""`；浏览器只与同源说话，CORS 摩擦消失。③ **Universal Score Axes UI 镜像**：`paper-card.tsx` 与 `paper/[id]/page.tsx` 各自维护 `SCORE_LABELS`（paper=Originality/Impact、blog=Depth/Actionability、talk=Depth/Actionability、project=Innovation/Maturity），通过 `_resolveScores` 做"universal 优先 + paper legacy 兜底"；`types.ts` 加 `quality_score` / `relevance_score` / `score_rationale` 字段，`Stats.top_overall` 可选数组。④ **Browse 页**：默认 `sort_by=total_score`（与后端默认对齐）；继续保留 `<Suspense>` 包装客户端 `useSearchParams` 组件。⑤ **Docker 镜像**：新增 `Dockerfile`（deps/builder/runner 三阶段，alpine 非 root，HEALTHCHECK 走 `/`） + `.dockerignore`；接受 `NEXT_PUBLIC_API_URL` / `KB_BACKEND_URL` / `NPM_REGISTRY` build arg。⑥ **`globals.css`**：标记仍为 Tailwind v4 入口（`@import "tailwindcss" / "tw-animate-css" / "shadcn/tailwind.css"` + `@theme inline` + `@custom-variant dark`），不再使用 `tailwind.config.*`。 |
