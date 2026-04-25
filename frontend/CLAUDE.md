# frontend/ — Next.js 16 / React 19 UI

[根目录](../CLAUDE.md) > **frontend**

> 由 `init-architect` 于 `2026-04-25 09:59:45` 自动生成。
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
npm run dev      # next dev (port 3000)
npm run build && npm start
npm run lint     # eslint (flat config, eslint-config-next)
```

---

## 三、对外接口（前端 → 后端 API 客户端）

文件：`src/lib/api.ts`，`API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"`。

| 函数 | 后端端点 | 用途 |
| --- | --- | --- |
| `listPapers(params)` | `GET /api/papers` | 列表 + 过滤/排序 |
| `getPaper(id)` | `GET /api/papers/{id}` | 详情 |
| `searchPapers(q, params)` | `GET /api/papers/search` | 语义/关键字检索 |
| `chat(request)` | `POST /api/chat` | RAG 对话 |
| `listReports(limit?)` | `GET /api/reports` | 报告列表 |
| `getReport(id)` | `GET /api/reports/{id}` | 报告详情 |
| `getStats()` | `GET /api/stats` | 统计 |

类型定义集中在 `src/lib/types.ts`（`Paper` / `PaperListResponse` / `DailyReport` / `ChatRequest` / `ChatResponse` / `Stats`），与后端 `kb/schemas.py` 一一对应——**任一侧字段变更需同步另一侧**。

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

环境变量：

| 变量 | 用途 |
| --- | --- |
| `NEXT_PUBLIC_API_URL` | 覆盖后端 API 地址，默认 `http://localhost:8000` |

---

## 五、目录结构

```
frontend/
├─ AGENTS.md                # ⚠️ Next.js 16 警示，必读
├─ CLAUDE.md                # 本文件
├─ package.json             # scripts / 依赖
├─ tsconfig.json            # TS strict
├─ next.config.* / eslint.config.* / postcss.config.*
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

---

## 七、测试与质量

- **静态检查**：`npm run lint`（ESLint 9 flat config + `eslint-config-next`）。
- **类型检查**：`tsc --noEmit`（建议接入到 CI / pre-commit）。
- **当前未配置**：jest / vitest / playwright；如需补，建议优先 vitest + @testing-library/react，路由相关用 playwright。

---

## 八、常见问题 (FAQ)

- **空白页 / `API error: 0`？** 检查后端是否运行在 `http://localhost:8000`，或显式设置 `NEXT_PUBLIC_API_URL` 后重启 `npm run dev`。
- **首次搜索 / 聊天明显延迟？** 正常，后端 `EmbeddingStore` 首次需要加载 SentenceTransformer 模型（已在 FastAPI lifespan 中预热，多数情况下感知不到）。
- **CORS 报错？** 后端默认仅放行 `http://localhost:3000`，如改前端端口或部署需要，更新 `KB_CORS_ORIGINS`。

---

## 九、相关文件清单（精选）

| 路径 | 用途 |
| --- | --- |
| `frontend/AGENTS.md` | Next.js 16 必读告警 |
| `frontend/package.json` | scripts / 依赖 |
| `frontend/src/app/layout.tsx` | 根布局 |
| `frontend/src/app/page.tsx` | 浏览 / 搜索 |
| `frontend/src/app/chat/page.tsx` | RAG 聊天 |
| `frontend/src/lib/api.ts` | API 客户端 |
| `frontend/src/lib/types.ts` | TS 类型（与后端 schemas 对齐） |

---

## 十、变更记录 (Changelog)

| 时间 | 操作 | 说明 |
| --- | --- | --- |
| 2026-04-25 09:59:45 | 初始化 | 自动生成 frontend 模块 `CLAUDE.md` |
