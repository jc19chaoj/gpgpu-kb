# frontend/ — Next.js 16 / React 19 UI

[← 返回根](../CLAUDE.md) > **frontend**

> 由 `init-architect` 于 `2026-04-25 09:59:45` 自动生成，
> 于 `2026-04-25 15:26:48` 增量刷新（新增 Playwright e2e、`npm run test:e2e`、CI 集成；提示 `/api/chat` 可能需要携带 `Authorization` 头）。
>
> ⚠️ 必读：`frontend/AGENTS.md` 提示 **这是最新版 Next.js（16.x），API 与约定可能与旧版本不同**。在写代码前先阅读 `frontend/node_modules/next/dist/docs/` 中的相应文档，留意 deprecation 提示。

---

## 一、模块职责

提供 GPGPU Knowledge Base 的浏览器 UI：

- **Browse**：分页、按类型过滤、按多维度排序的论文/博客/项目列表
- **Search**：URL `?q=...` 触发，调后端语义检索，自动回退关键字搜索
- **Chat**：RAG 对话页，调用 `/api/chat`，展示来源徽章并跳转详情
- **Paper detail**：单条论文详情，含 Originality / Impact 与 rationale
- **Reports**：每日 Markdown 报告列表与详情
- **Stats**：知识库整体统计

整套界面采用暗色主题（`bg-zinc-950 text-zinc-100`），左侧 Sidebar + 顶部 Header 的 dashboard 布局。

---

## 二、入口与启动

| 入口 | 作用 |
| --- | --- |
| `src/app/layout.tsx` | RootLayout：暗色 `<html>`、Geist 字体、Sidebar + Header 框架 |
| `src/app/page.tsx` | `/` Browse 页（含 `?q` → search） |
| `src/app/chat/page.tsx` | `/chat` RAG 对话页 |
| `src/app/paper/[id]/page.tsx` | `/paper/:id` 论文详情 |
| `src/app/reports/page.tsx` / `reports/[id]/page.tsx` | 报告列表 / 详情（Markdown via `react-markdown` + `remark-gfm`）|
| `src/app/stats/page.tsx` | `/stats` 统计 |

启动命令：

```bash
cd frontend
npm install
npm run dev          # next dev (port 3000)
npm run build && npm run start   # 生产构建 + 启动
npm run lint         # eslint (flat config, eslint-config-next)
npx tsc --noEmit     # 类型检查
npm run test:e2e     # Playwright e2e（需先 `npx playwright install chromium`）
```

---

## 三、对外接口（前端 → 后端 API 客户端）

文件：`src/lib/api.ts`，`API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"`。

| 函数 | 后端端点 | 用途 |
| --- | --- | --- |
| `listPapers(params)` | `GET /api/papers` | 列表 + 过滤/排序 |
| `getPaper(id)` | `GET /api/papers/{id}` | 详情 |
| `searchPapers(q, params)` | `GET /api/papers/search` | 语义/关键字检索 |
| `chat(request)` | `POST /api/chat` | RAG 对话；**若后端开启了 `KB_CHAT_TOKEN`，需要在 `fetchJSON` 的 `headers` 中追加 `Authorization: Bearer <token>`，当前默认实现未带** |
| `listReports(limit?)` | `GET /api/reports` | 报告列表 |
| `getReport(id)` | `GET /api/reports/{id}` | 报告详情 |
| `getStats()` | `GET /api/stats` | 统计 |

类型定义集中在 `src/lib/types.ts`（`Paper` / `PaperListResponse` / `DailyReport` / `ChatRequest` / `ChatResponse` / `Stats`），与后端 `kb/schemas.py` 一一对应——**任一侧字段变更需同步另一侧**。

> 部署到生产 / 使用 cpolar 暴露时，若后端启用了 Bearer Token 守卫，需要扩展 `fetchJSON` 接受 token（建议读 `process.env.NEXT_PUBLIC_CHAT_TOKEN` 或在 server-side route handler 转发）。

---

## 四、关键依赖与配置

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
| **`@playwright/test`** | **^1.59.1** | **e2e 测试框架（devDep）** |

### scripts（`package.json`）

| 脚本 | 命令 |
| --- | --- |
| `dev` | `next dev` |
| `build` | `next build` |
| `start` | `next start` |
| `lint` | `eslint` |
| **`test:e2e`** | **`playwright test`** |

环境变量：

| 变量 | 用途 |
| --- | --- |
| `NEXT_PUBLIC_API_URL` | 覆盖后端 API 地址，默认 `http://localhost:8000` |
| `NEXT_PUBLIC_CHAT_TOKEN`（建议，未实现） | 若上线后开启了后端 `KB_CHAT_TOKEN`，可通过该变量在 `api.ts` 注入 Bearer 头 |

---

## 五、目录结构

```
frontend/
├─ AGENTS.md                # ⚠️ Next.js 16 警示，必读
├─ CLAUDE.md                # 本文件
├─ package.json             # scripts / 依赖（含 @playwright/test）
├─ tsconfig.json            # TS strict
├─ playwright.config.ts     # e2e 配置（chromium / webServer: next start -p 3000）
├─ next.config.* / eslint.config.* / postcss.config.*
├─ tests/
│  └─ e2e/                  # Playwright 用例（后端在 e2e 中完全 mock）
└─ src/
   ├─ app/                  # App Router
   │  ├─ layout.tsx         # 根布局：Sidebar + Header
   │  ├─ page.tsx           # Browse / Search 入口
   │  ├─ chat/page.tsx      # RAG 聊天
   │  ├─ paper/[id]/page.tsx
   │  ├─ reports/page.tsx
   │  ├─ reports/[id]/page.tsx
   │  ├─ stats/page.tsx
   │  └─ globals.css        # Tailwind v4 入口
   ├─ components/
   │  ├─ layout/            # Sidebar、Header
   │  ├─ ui/                # shadcn/ui 原语（button / card / dialog / badge / skeleton / input / scroll-area …）
   │  ├─ paper-card.tsx     # 列表行
   │  └─ search-bar.tsx     # 搜索框（路由跳到 / + ?q=...）
   └─ lib/
      ├─ api.ts             # fetch 客户端
      ├─ types.ts           # 与后端 schemas 对齐
      └─ utils.ts           # cn / clsx 等
```

---

## 六、约定与坑位

1. **Next.js 16 是最新版本**：在写任何前端代码前，先阅读 `node_modules/next/dist/docs/` 的相关章节；不要套用 Next 13/14 时代的 App Router / Route Handler / Metadata API 经验。如发现弃用提示，按其指引迁移。
2. **React 19**：`page.tsx` 中保留了 `// eslint-disable-next-line react-hooks/set-state-in-effect`，标准修法是引入 SWR / React Query；当前项目刻意 keep simple，新增页面也尽量先评估"是否需要状态管理库"再下手。
3. **Suspense 边界**：使用 `useSearchParams` 的客户端组件（如 Browse）必须包在 `<Suspense>` 中，否则 16 会编译报错（参见 `app/page.tsx` 的 `BrowsePage` 包装）。
4. **暗色主题**：根 `<html className="… dark">`；新组件请直接走 Tailwind dark palette（zinc / emerald 强调色）。
5. **shadcn/ui 复用**：UI 原语都在 `components/ui/`，新增基础原语优先用 `npx shadcn add ...`，不要手抄重写。
6. **Markdown 渲染**：聊天与报告页用 `react-markdown + remark-gfm`，对 LLM 输出做受控渲染；不要在不可信文本上启用 raw HTML。
7. **聊天页错误吞掉**：`chat/page.tsx` 用 `try/catch` 把后端 4xx/5xx 一律转成 "Sorry, I couldn't process that query"；若后端开启了 `KB_CHAT_TOKEN` 而前端未带头，会一直显示该提示而非 401，**调试时请打开 Network 面板**或在 catch 中记录 `err.message`。

---

## 七、测试与质量

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

## 八、CI 集成

`.github/workflows/ci.yml` 中包含两个前端 job（与 backend 并行）：

| Job | 步骤 |
| --- | --- |
| `frontend-typecheck` | `actions/setup-node@v4`（Node 20，npm cache） → `npm ci` → `npx tsc --noEmit` → `npx eslint src/` |
| `frontend-e2e` | `actions/setup-node@v4` → `npm ci` → `npx playwright install --with-deps chromium` → `npm run build` → `npm run test:e2e` |

> Playwright 浏览器二进制每次 CI 都要 `--with-deps` 安装，耗时 ~30s；本地首次 `npx playwright install chromium` 即可。

---

## 九、常见问题 (FAQ)

- **空白页 / `API error: 0`？** 检查后端是否运行在 `http://localhost:8000`，或显式设置 `NEXT_PUBLIC_API_URL` 后重启 `npm run dev`。
- **首次搜索 / 聊天明显延迟？** 正常，后端 `EmbeddingStore` 首次需要加载 SentenceTransformer 模型（已在 FastAPI lifespan 中预热，多数情况下感知不到）。
- **CORS 报错？** 后端默认仅放行 `http://localhost:3000`，如改前端端口或部署需要，更新 `KB_CORS_ORIGINS`。
- **聊天页一直 "Sorry, I couldn't process that query"？** 排查顺序：① 后端是否运行；② 后端是否启用 `KB_CHAT_TOKEN`（如启用，前端目前未带头）；③ 是否安装 `[ml]` extra（无 ML 依赖时会拿不到 sources，但答案应可生成）。
- **e2e 在 CI 失败？** 检查是否漏跑 `npm run build`（`webServer.command` 用的是 `next start`，而非 `next dev`，需先有 `.next/`）。

---

## 十、相关文件清单（精选）

| 路径 | 用途 |
| --- | --- |
| `frontend/AGENTS.md` | Next.js 16 必读告警 |
| `frontend/package.json` | scripts / 依赖（含 `test:e2e`） |
| `frontend/playwright.config.ts` | e2e 配置 |
| `frontend/tests/e2e/` | Playwright 用例 |
| `frontend/src/app/layout.tsx` | 根布局 |
| `frontend/src/app/page.tsx` | 浏览 / 搜索 |
| `frontend/src/app/chat/page.tsx` | RAG 聊天 |
| `frontend/src/lib/api.ts` | API 客户端 |
| `frontend/src/lib/types.ts` | TS 类型（与后端 schemas 对齐） |

---

## 十一、变更记录 (Changelog)

| 时间 | 操作 | 说明 |
| --- | --- | --- |
| 2026-04-25 09:59:45 | 初始化 | 自动生成 frontend 模块 `CLAUDE.md` |
| 2026-04-25 15:26:48 | 增量刷新 | ① 新增 Playwright e2e 文档（`playwright.config.ts` / `tests/e2e/` / `npm run test:e2e` / `@playwright/test` devDep）；② 新增"CI 集成"章节，反映 `frontend-typecheck` + `frontend-e2e` 两个 GitHub Actions job；③ 标注 `/api/chat` 在后端启用 `KB_CHAT_TOKEN` 时前端尚未携带 `Authorization` 头的潜在坑；④ 顶部面包屑改为 `[← 返回根]` 风格，与 backend 一致 |
