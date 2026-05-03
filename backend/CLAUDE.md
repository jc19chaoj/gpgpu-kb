# backend/ — Python / FastAPI 服务

[← 返回根](../CLAUDE.md) > **backend**

> 由 `init-architect` 于 `2026-04-25 09:59:45` 自动生成，
> 于 `2026-04-25 15:26:48` 增量刷新（DeepSeek provider / Bearer Token / pytest 套件落地），
> 于 `2026-04-25 16:50` 增量刷新（质量门 `is_processed=2` / `KB_QUALITY_SCORE_THRESHOLD`），
> 于 `2026-05-02 08:57:04` 增量刷新（Universal Score Axes / 中文 LLM 输出 / Docker 镜像 / 自适应 ingest 回看窗 / 冷启动批处理 / 非论文 rescore 脚本 / RSS 源精简),
> 于 `2026-05-02 20:12:04` 增量刷新（多轮 Chat 历史 + 单 source 锚定模式 + `kb.processing.pdf` PDF 全文加载（pypdf 默认依赖、`Paper.full_text` 列）+ uvicorn `--timeout-keep-alive 75` keep-alive 修复），
> 于 `2026-05-02 21:18:53` 增量刷新（SSE 流式聊天 `/api/chat/stream` + 共享 `_build_chat_context` + `stream_llm` 抽象（`_STREAM_PROVIDERS` 字典）+ `_stream_openai_compatible` 公共体 + `_stream_anthropic` text_stream + chat 系统 prompt 改为中文硬编码），
> 于 `2026-05-02 23:32:00` 增量刷新（新增 vLLM Blog 进 RSS FEEDS（12 个源）+ 新模块 `kb/ingestion/sitemap_blog.py` 覆盖无原生 RSS 的 SPA 站点（首条来源 LMSYS / SGLang Blog）+ `kb/ingestion/run.py` 编排独立 stage `results["sitemap_blogs"]` + 12+ 例单元测试 + orchestrator 测试升级到 4 fetcher，pytest 174/174）。
> 于 **`2026-05-03 09:44:00`** 增量刷新（**ingestion 冷启动改为 per-`Paper.source_name` 判定：`kb/ingestion/run.py` 新增 `_lookback_for_source(source_name)`，4 个 fetcher 签名统一 `days_back: int | None`（None 时各自走 per-source 窗口；ArXiv / GitHub 用 aggregate `source_name="arxiv"` / `"github"`，RSS / sitemap_blog 在循环内 per-feed / per-source 调用）；新增 RSS feed 进 `FEEDS` 或 sitemap 源进 `SITEMAP_SOURCES` 后下次 daily 自动 30 天 backfill 该源；测试 174 → 180 pass**）。

---

## 一、模块职责

后端承担四件事：

1. **采集（ingestion）**：从 ArXiv / RSS / GitHub Search 拉取近期内容，按 `Paper.url` 唯一索引去重写入 SQLite；回看窗自动适配上次成功时间。
2. **处理（processing）**：调用 LLM 对每条记录生成 ~3-5 段技术摘要，并按 `source_type` 切换 rubric 打两维 0-10 分（universal axes：`quality_score` / `relevance_score`）；之后用 sentence-transformers 生成嵌入并写入 ChromaDB；**source-anchored chat 触发时按需下载 PDF 抽全文，缓存在 `Paper.full_text`**。
3. **服务（API）**：FastAPI 暴露浏览 / 详情 / 搜索 / **多轮 + source-anchored RAG 聊天（一次性 + SSE 流式两种端点）** / 日报 / 统计 / 健康检查端点；可选 Bearer Token 守卫 `/api/chat` 与 `/api/chat/stream`。
4. **报告（reports）**：每天聚合当日已处理论文与博客/项目，产出一份 Markdown 简报存入 `daily_reports`（按 `max(quality, relevance)` 排序，使非论文也能上榜）。

---

## 二、入口与启动

| 入口 | 作用 |
| --- | --- |
| `kb/main.py` (`app = FastAPI(...)`) | API 应用对象；`lifespan` 中初始化日志、`init_db()`、后台预热 EmbeddingStore（`asyncio.create_task`，不阻塞 startup）；`/api/chat` 与 **`/api/chat/stream`（SSE）** 共享 `_build_chat_context` + `_format_history` |
| `kb/daily.py` (`run_daily_pipeline`) | 完整每日流水线（ingest → process → embed → report）；冷启动检测 + `--lang zh` 切换 |
| `kb/ingestion/run.py` (`run_ingestion`) | 仅运行采集阶段；`days_back: int \| None`，None 时**每个 fetcher 自己走 per-`source_name` 冷启动**（见 `_lookback_for_source`）；`_compute_days_back()` 退化为 `_lookback_for_source(None)` 薄包装 |
| `kb/processing/llm.py` (`run_processing`) | 仅运行 LLM 处理阶段，`batch_size=None` 表示无上限 |
| `kb/processing/llm.py` (`call_llm` / **`stream_llm`**) | LLM 调用门面：`call_llm` 返回完整字符串（用于 summary/scoring 与 `/api/chat`）；**`stream_llm` 增量 yield 文本片段（用于 `/api/chat/stream`）；任何 provider 失败均返回空 / 静默结束 generator** |
| `kb/processing/embeddings.py` (`index_unindexed_papers`) | 仅运行向量化阶段，`batch_size=None` 表示无上限 |
| `kb/processing/pdf.py` (`fetch_full_text`) | 下载 + 抽取 PDF 全文，缓存到 `Paper.full_text`；缺失 / 失败 fallback 到 `summary + abstract`（不污染缓存） |
| `kb/reports.py` (`generate_daily_report`) | 仅生成日报（默认昨天，upsert） |
| `kb/scripts/rescore_non_papers.py` | 运维脚本：回填非论文行 universal scores（支持 `--dry-run` / `--limit` / `--source-type`） |
| `run_api.sh` | `uvicorn kb.main:app --host 0.0.0.0 --port 8000 --reload --timeout-keep-alive 75` |
| `Dockerfile` | `python:3.12-slim` 多阶段镜像；`ARG INSTALL_EXTRAS=ml,llm-cloud` 控制大小；`HEALTHCHECK` 走 `/api/health`；`CMD ["uvicorn", ..., "--timeout-keep-alive", "75"]` |

启动命令：

```bash
cd backend
source .venv/bin/activate
./run_api.sh                                       # 开发：带 --reload + keep-alive 75
python -m kb.daily                                 # 跑一遍完整流水线（语言由 KB_LANGUAGE 决定）
python -m kb.daily --lang zh                       # 命令行覆盖为中文
python -m kb.ingestion.run                         # 仅采集
python -m kb.reports                               # 仅生成昨天的报告
python -m kb.scripts.rescore_non_papers --dry-run  # 列出需要回填的非论文行
python -m pytest tests/ -x -q                      # 跑测试 (~115 例)
```

---

## 三、对外接口（FastAPI 路由）

定义文件：`kb/main.py`

| 方法 + 路径 | 函数 | 说明 |
| --- | --- | --- |
| `GET  /api/papers` | `list_papers` | 分页列出，按 `source_type` 过滤；`sort_by` 支持 `published_date` / `impact_score` / `originality_score` / `quality_score` / `relevance_score` / `total_score`（默认） / `ingested_date`；`total_score` 对应 `originality + impact + quality + relevance` 之和（paper / 非 paper 两组互斥，求和等价于行总分）。**默认仅返回 `is_processed=1`**，加 `?include_low_quality=true` 同时返回 `0`/`2` |
| `GET  /api/papers/search` | `search_papers` | `q` 必填；`semantic=true` 走 ChromaDB（仅含 `is_processed=1`），无结果回退 ILIKE（用 `_escape_like` 转义 `%` `_` `\`）。**注意路由顺序：search 必须在 `{paper_id}` 之前** |
| `GET  /api/papers/{paper_id}` | `get_paper` | 单条详情；**不过滤** `is_processed` |
| `POST /api/chat` | `chat` | **非流式 RAG / source-anchored 双模式**：默认走向量召回 `top_k`；当 `req.paper_id` 给定时**跳过检索**，调 `fetch_full_text(paper_id)` 把全文（≤60 000 字符）放入 prompt，`sources` 仅含目标 paper（不存在 → 404）。无论哪种模式，`req.history[]` 都通过 `_format_history` 注入 UNTRUSTED 块（最近 12 条 turn，单条 4 000 字符 cap）。**受 `verify_chat_token` 守卫**：若 `KB_CHAT_TOKEN` 已设置，必须带 `Authorization: Bearer <token>`。Prompt + sources 由 `_build_chat_context(req, db)` 生成，**与 `/api/chat/stream` 共用**。|
| **`POST /api/chat/stream`** | **`chat_stream`** | **SSE 流式版本**：返回 `text/event-stream`，Header `Cache-Control: no-cache` + `X-Accel-Buffering: no`；事件序列固定 `sources`（恰 1 条）→ `token`（≥1 条；若无输出则发占位 `(LLM produced no output)`）→ `done`（终止符）。**先同步跑 `_build_chat_context`** 让 HTTPException（如 paper_id 404）正常走 HTTP 错误而非空流；之后构造 `event_stream()` 生成器调 `stream_llm(prompt)` 增量 yield。**同样受 `verify_chat_token` 守卫**。 |
| `GET  /api/reports` | `list_reports` | 倒序列出最近 N 份日报 |
| `GET  /api/reports/{report_id}` | `get_report` | 单份日报（Markdown）|
| `GET  /api/stats` | `get_stats` | `total_papers` / `processed` / `skipped_low_quality` / `pending` / `by_type` / `top_impact`（5 条，legacy paper-only）/ `top_overall`（5 条，按 `max(quality, relevance)` 跨类型 ranking） |
| `GET  /api/health` | `health` | 存活探针，返回 `{"status":"ok"}`（HEALTHCHECK 指标） |

Swagger UI：`http://localhost:8000/docs`

### Bearer Token 守卫细节（`verify_chat_token`）

- 配置项：`settings.chat_token`（来源 `KB_CHAT_TOKEN`）。
- 未设置 → 端点开放（无摩擦本地开发）。
- 已设置 → 需 `Authorization: Bearer <token>`；缺头或前缀不对返回 401 `Missing bearer token`；值不匹配返回 401 `Invalid bearer token`。
- **比较使用 `hmac.compare_digest`**（防侧信道）；新增类似认证端点请复用同款写法，禁止 `==`。
- **同时挂在 `/api/chat` 与 `/api/chat/stream`**（`dependencies=[Depends(verify_chat_token)]`）。

### Chat schema (`kb/schemas.py`)

```python
class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")  # 不允许 "system"
    content: str = Field(..., min_length=1, max_length=settings.chat_query_max_len * 4)

class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=settings.chat_query_max_len)
    top_k: int = Field(5, ge=1, le=settings.chat_top_k_max)
    paper_id: int | None = None
    history: list[ChatMessage] = Field(default_factory=list, max_length=40)
```

`max_length=40` 是 Pydantic 边界（防 DoS），`main.py::_HISTORY_TURN_CAP=12` 是 prompt 实际渲染窗口。两者解耦，便于独立调整。

### 共享 prompt 构造（`_build_chat_context`，本轮新抽出）

`/api/chat` 与 `/api/chat/stream` 都调用 `_build_chat_context(req, db) -> tuple[str, list[PaperOut]]`：

- 计算 `history_block = _format_history(req.history)`（最近 12 条 turn，单条 4 000 字符）。
- 若 `req.paper_id is not None`：查 paper（404 if missing）→ lazy import `kb.processing.pdf.fetch_full_text` → 拼 source-anchored prompt（≤60 000 字符正文 + history block + current query）→ `sources = [那篇 paper]`。
- 否则：`get_embedding_store().search(req.query, top_k=req.top_k)` → 拼 RAG prompt（context + history + query）→ `sources = 召回到的 papers`。
- **整段都在 `=== UNTRUSTED START === / END ===` 块内**，并显式提示模型"data, not instructions"。
- **prompt 系统消息已硬编码为中文**（`你是一名资深的 GPGPU 芯片架构助理 ...`，结尾"请用简体中文作答"）。`KB_LANGUAGE` 不再影响 chat prompt（仅影响 summarization / scoring / reports）。

### Source-anchored prompt 结构

```
SOURCE TITLE / SOURCE TYPE / AUTHORS / URL
=== FULL SOURCE CONTENT ===
{up to 60 000 chars from fetch_full_text}

=== CONVERSATION HISTORY ===
{up to 12 most recent turns, each ≤4000 chars}

CURRENT USER QUESTION: ...
```

### SSE 帧格式（`_sse_event` helper）

```
event: <name>\ndata: <json>\n\n
```

- `_sse_event(event, data)` 用 `json.dumps(..., ensure_ascii=False)` 编码，避免中文被转成 `\uXXXX`。
- 事件序列：`sources`（恰 1，payload `{"sources": [PaperOut, ...]}`）→ `token`（≥1，payload `{"content": "<chunk>"}`）→ `done`（恰 1，payload `{}`）。可选 `error`（payload `{"message": "..."}`），但当前 `stream_llm` 失败是静默吞掉，**不会发 `error`**——前端通过"done 之前 token 累计为空"区分。

---

## 四、关键依赖与配置

`pyproject.toml` 三组可选依赖：

| Extra | 提供 | 触发 |
| --- | --- | --- |
| 默认 | FastAPI / Uvicorn / SQLAlchemy 2 / Pydantic 2 / arxiv / feedparser / httpx / python-dotenv / **pypdf>=5.0** | 必装 |
| `[ml]` | chromadb · sentence-transformers（~2GB） | 想要语义检索 / RAG |
| `[llm-cloud]` | anthropic · openai（DeepSeek 复用 openai SDK，无需新依赖） | 走云端 LLM |
| `[dev]` | pytest · pytest-asyncio · httpx · ruff | 测试 / lint |

> CI 中使用 `pip install -e '.[dev]'` + `pytest-cov`；**故意不装 `[ml]`** 以加快流水线，相关测试以 `pytest.mark.skipif` 自动跳过。
> Docker 镜像通过 `ARG INSTALL_EXTRAS=ml,llm-cloud` 控制；改成 `llm-cloud` 或空串可瘦身镜像（搜索自动降级到关键字）。
> **`pypdf` 是默认依赖**（仅 ~600 KB 纯 Python），用于 source-anchored chat 的 PDF 抽取。

设置类：`kb/config.py` 的 `Settings(BaseSettings)`，前缀 `KB_`，亦读取 `backend/.env`。新增 / 当前完整字段见 `kb/config.py`，包括 `language`、`llm_provider`、`anthropic/openai/deepseek_*`、`ingest_empty_db_days`、`ingest_gap_min_days`、`ingest_gap_max_days`、`quality_score_threshold`、`chat_query_max_len`、`chat_top_k_max`、`chat_token`、`cors_origins`、`data_dir`、`database_url`、`chroma_dir`、`embedding_model`、`llm_timeout_seconds` 等（详见根 CLAUDE.md "环境变量"表格）。

---

## 五、数据模型

文件：`kb/models.py`（SQLAlchemy DeclarativeBase）

### `papers`

| 字段 | 类型 | 备注 |
| --- | --- | --- |
| `id` | int PK | autoincrement |
| `title` | str(500) | 必填 |
| `authors` / `organizations` / `categories` | JSON list | 默认空 list；categories 经 `PaperOut._coerce_categories` 兼容旧 RSS 行的 feedparser dict |
| `abstract` | Text | 默认空 |
| `url` | str(1000) | **唯一索引**，去重依据 |
| `pdf_url` | str(1000) | source-anchored chat 通过 `_looks_like_pdf_url` 判断是否拉 PDF |
| `source_type` | Enum(`paper`/`blog`/`talk`/`project`) | 默认 `paper`，索引 |
| `source_name` | str(200) | 例如 `arxiv`、`OpenAI`、`github` |
| `published_date` / `ingested_date` | DateTime(tz) | `ingested_date` 索引，UTC |
| `venue` | str(200) | 默认空 |
| `citation_count` | int | 预留字段 |
| `summary` | Text | LLM 输出 |
| `originality_score` / `impact_score` | float | **legacy 兼容字段**：仅对 `paper` 行从 universal axes 镜像；`impact_score` 索引 |
| `impact_rationale` | Text | legacy；paper 行从 `score_rationale` 镜像 |
| `quality_score` | float | universal axis #1（0-10），按 `source_type` 语义切换；索引 |
| `relevance_score` | float | universal axis #2（0-10），按 `source_type` 语义切换 |
| `score_rationale` | Text | universal 评分理由（中文模式下为中文） |
| `full_text` | Text | **PDF 抽取后缓存的完整正文**（≤120 000 字符）；source-anchored chat 第一次成功提取后写入；网络/解析失败保持空串 |
| `is_processed` | int | **状态机**：`0`=待处理（含 LLM 失败重试）/ `1`=精品收录 / `2`=低分跳过（仅 paper 因质量门触发）；索引 |
| `chroma_id` | str(100) | 与 ChromaDB 行的关联键 |

### `daily_reports`

| 字段 | 类型 | 备注 |
| --- | --- | --- |
| `id` | int PK | – |
| `date` | DateTime(tz) | **唯一**（每天一条；`reports.py` 走 upsert）|
| `title` / `content` | str / Text | Markdown；中文模式下标题为 `每日研究简报 — YYYY-MM-DD` |
| `paper_ids` | JSON list[int] | 引用的 ID（论文 + 博客 + 项目混合） |
| `generated_date` | DateTime(tz) | – |

### 索引与列兼容性（SQLite-friendly）

`kb/database.py` 在 `init_db()` 中：

1. `_BACKCOMPAT_COLUMNS`：`PRAGMA table_info(papers)` 探测后幂等 `ALTER TABLE` 加列：`quality_score` / `relevance_score` / `score_rationale` / `full_text`。
2. `_BACKCOMPAT_INDEXES`：`CREATE INDEX IF NOT EXISTS` 补加 `ix_papers_url` / `source_type` / `is_processed` / `impact_score` / `quality_score` / `ingested_date`。

这样既兼容旧 `kb.sqlite`，又允许迁移到 Postgres 走 alembic（`_ensure_papers_columns` 仅在 `database_url.startswith("sqlite")` 时执行）。

---

## 六、采集与处理细节

### `kb/ingestion/`

| 文件 | 职责 | 关键点 |
| --- | --- | --- |
| `arxiv.py` | 9 个 cs.* 类目逐一查，按 `submitted_date` 倒排，截至 `cutoff` | 单查询而非 OR，避免高量类目（cs.AI）饿死其它 |
| `rss.py` | **12 个精选 RSS 源**（截至 2026-05 验证可用，本轮新增 vLLM Blog `https://vllm.ai/blog/rss.xml`） | `feedparser`；`bozo` 仅警告不拒收；`_tag_to_str` 把 feedparser 的 `term/scheme/label` 字典规范化为 `list[str]` 入库 |
| `sitemap_blog.py` | **本轮新增**：sitemap-driven blog scraper，覆盖没有原生 RSS 的 SPA 站点（当前内置 1 个源：LMSYS / SGLang Blog `https://lmsys.org/sitemap.xml` + `path_prefix="https://lmsys.org/blog/"`） | stdlib `xml.etree.ElementTree` 解析 sitemap → `<lastmod>` 预过滤 → 单 `httpx.Client` 顺序 GET 每篇 → 正则抽 `<meta og:* / twitter:* / article:*>` → 兼容 `April 29, 2026` 等人写日期；网络/解析失败一律 logger.warning + skip 不抛；`_MAX_ARTICLES_PER_SOURCE=60` 防 DoS；`default_categories` 给每条预贴静态标签（如 `("sglang","lmsys")`） |
| `github_trending.py` | GitHub Search API 按 17 个关键词查 `pushed:>yesterday` | 无 token 时 10 req/min 易 429，建议设 `GITHUB_TOKEN`；带 token 后切到带 polite sleep 的 30 req/min 路径 |
| `run.py` | 编排 arxiv → rss → sitemap_blog（独立 stage，复用 `save_posts`，写到 `results["sitemap_blogs"]`）→ github_trending；每步独立 try/except；**`_lookback_for_source(source_name)` per-source 冷启动**（`days_back is None` 时每个 fetcher 各自调；`_compute_days_back` 是 `_lookback_for_source(None)` 的薄包装） | 单源失败不影响其它；该 `source_name` 下 `MAX(ingested_date)` 为 NULL → `KB_INGEST_EMPTY_DB_DAYS` 冷启动 backfill；否则 `now - max(...)` clamped 到 `[min, max]`。**新增任意 RSS feed / sitemap 源后，下次 daily 自动 30 天 backfill 那一条 source_name** |

去重统一采用 `Paper.url` 是否已存在。`sitemap_blog` 写入的 `Paper.url` 取页面 `og:url`（不存在时回退 sitemap `<loc>`），所以重定向（如 lmsys.org → www.lmsys.org）不会破坏 dedup 稳定性——同一页跨 run 始终落在同一 canonical URL。

### `kb/processing/`

| 文件 | 职责 | 关键点 |
| --- | --- | --- |
| `llm.py` | provider 抽象 + 摘要/打分流水线 + **streaming 平行栈** | `_PROVIDERS = {hermes, anthropic, openai, deepseek}` + **`_STREAM_PROVIDERS = {hermes, anthropic, openai, deepseek}`** 平行；`call_llm` / **`stream_llm`** 公开门面，任何 provider 异常一律返回 `""` / 静默结束 generator 不抛 |
| `embeddings.py` | ChromaDB + sentence-transformers，懒加载单例 | 没装 ML 依赖时 `available=False`，`search()` 返回空列表，调用方自然降级；`get_embedding_store()` 用 `threading.Lock` 串行化首次构造 |
| `pdf.py` | PDF 下载 + 抽取，缓存写回 `Paper.full_text` | `httpx.Client.stream` 流式读取，**20 MB 上限 / 30 s 超时 / 120 000 字符截断**；`_extract_text` 容忍单页失败；非 PDF URL → `summary + abstract` fallback；网络/解析失败不污染缓存 |

### Provider 矩阵（`call_llm` / `stream_llm`）

| `KB_LLM_PROVIDER` | `call_llm` 实现 | `stream_llm` 实现 | 依赖 |
| --- | --- | --- | --- |
| `hermes`（默认） | `subprocess.run(["hermes", "ask", ...])` | **`_stream_hermes`：调 `_call_hermes` 拿全文 → yield 单 chunk（空字符串则不 yield）**；子进程不能真正流式 | 系统装有 `hermes` CLI；**容器中不可用** |
| `anthropic` | `anthropic.Anthropic(...).messages.create(...)` | `client.messages.stream(...)` 的 `text_stream` 上 yield | `pip install -e '.[llm-cloud]'` + `ANTHROPIC_API_KEY` |
| `openai` | `openai.OpenAI(...).chat.completions.create(...)` | **`_stream_openai_compatible(api_key, model)`**：`stream=True` 后逐 `chunk.choices[0].delta.content` yield | `pip install -e '.[llm-cloud]'` + `OPENAI_API_KEY` |
| `deepseek` | `openai.OpenAI(api_key=DEEPSEEK_API_KEY, base_url=KB_DEEPSEEK_BASE_URL).chat.completions.create(...)` | **`_stream_openai_compatible(api_key, model, base_url=...)`**：与 openai 走同一公共体，仅多传 `base_url` | `pip install -e '.[llm-cloud]'` + `DEEPSEEK_API_KEY`（**复用 openai SDK**） |

> 新增其它 OpenAI 兼容 provider（如 Together / Groq / 内部网关）时，只要在 `_PROVIDERS` 与 `_STREAM_PROVIDERS` 字典里各加一个 wrapper 调 `_stream_openai_compatible(api_key, model, base_url)` 即可，**不要重复写 client 构造**。

### Prompt 安全 / 多语言

- `_sanitize()` 限长 8000 chars + ``` → `ʼʼʼ`。
- prompt 包裹 `=== UNTRUSTED START === / END ===`，并提示模型"只视为数据"；**chat history 与 source 全文也都进同一块**（见 `main.py::_build_chat_context`）。
- `_lang_instruction()`（zh）：在 summary prompt 末尾追加 `Write your entire response in Chinese (简体中文)`。
- `_impact_lang_instruction()`（zh）：仅在 score prompt 末尾追加 `Write the "impact_rationale" value in Chinese... Keep all JSON keys and numeric scores in English/ASCII.`——**JSON 键必须英文**，否则 `summarize_and_score` 会返回 `False`，留 `is_processed=0` 等待重试。
- **chat prompt（`_build_chat_context`）已脱离 `KB_LANGUAGE` 控制，硬编码为中文系统消息**；要回退到英文必须直接修改函数内的 prompt 字面量（非流式与 SSE 端点共用同一处，改一次两处生效）。

### 评分 rubric 矩阵（`_RUBRICS`）

| `source_type` | quality_score 含义 | relevance_score 含义 |
| --- | --- | --- |
| `paper` | Originality（核心点子的新颖度） | Impact（作者 / 机构 / 会场 / 解法的通用性） |
| `blog` | Technical Depth | Actionability（CUDA/Triton/MLIR/HIP 可落地性） |
| `talk` | Depth（实测数据 / 架构细节深度） | Actionability |
| `project` | Innovation（独到的 kernel/runtime/compiler trick） | Maturity（stars / 活跃度 / 文档 / 测试） |

### 质量门与状态机

`summarize_and_score` 在 LLM JSON 解析成功后落桶到 `Paper.is_processed`：

| 分支 | 条件 | `is_processed` | 备注 |
| --- | --- | --- | --- |
| Paper · 精品 | `source_type=paper` 且 `max(quality, relevance) ≥ KB_QUALITY_SCORE_THRESHOLD` | `1` | 同时把 `quality/relevance/score_rationale` 镜像到 `originality/impact/impact_rationale` |
| Paper · 低分跳过 | `source_type=paper` 且 `max(...)` < threshold | `2` | 不进入 ChromaDB，不出现在默认 list；`Paper.url` 唯一 + `is_processed != 0` 双锁防重摄入 / 重打分 |
| 非论文 · 收录 | `source_type` ∈ {blog, talk, project} 且 JSON 解析成功 | `1` | **不走质量门**——curated RSS / GitHub 关键词已是入口闸；不镜像到 legacy paper 字段 |
| 待重试（任意类型） | LLM 返回非 JSON / 抛异常 / 必需键缺失 / 键被翻译成中文 | `0`（保留） | 下次 `run_processing` 自动重试；**禁止写 5.0/5.0 兜底** |

要点：

- 维度选 `max(quality, relevance)`：让"无名实验室但创意新"的 Hidden Gems 也能进精品（呼应 `reports.py` 的 Hidden Gems 章节）。
- 阈值通过 `settings.quality_score_threshold` 读取，**不要**直接硬编码 7.0。
- 修改阈值**不会**回溯既存 `is_processed=1` 数据——只对新打分的论文生效。
- ChromaDB 通过 `index_unindexed_papers` 仅索引 `is_processed=1`，所以语义搜索无需额外过滤；关键字 fallback 路径在 `main.py` 显式过滤。

### 冷启动批处理（`kb.daily`）

`run_daily_pipeline` 启动时探测：

- **处理冷启动**：`Paper.is_processed != 0` 全为空 → `run_processing(batch_size=None)`，否则默认 100 条/run。
- **嵌入冷启动**：`Paper.is_processed == 1 && chroma_id != ""` 全为空 → `index_unindexed_papers(batch_size=None)`，否则 100 条/run。

目的：避免后到的 RSS / GitHub 项目被 ArXiv 队列前缀（一次 ingestion 可能新增几百行）饿死。

### Per-Source ingest 冷启动（`kb.ingestion.run`）

与上一节"批处理冷启动"是**两套独立机制，判定维度不同**——这一节说的是"采集回看窗"。

`_lookback_for_source(source_name: str | None) -> int`（`kb/ingestion/run.py`）查 `MAX(Paper.ingested_date)` filtered by `source_name`：

- 该 `source_name` 下没有任何已入库行 → 返回 `settings.ingest_empty_db_days`（默认 30）→ **冷启动 backfill**。
- 否则按 `now - MAX(...)` 计算 gap，clamp 到 `[ingest_gap_min_days, ingest_gap_max_days]`。
- `source_name=None` 跳过过滤，返回旧"全局 gap"——`_compute_days_back()` 就是这个。

4 个 fetcher 签名都是 `days_back: int | None`：

| fetcher | None 时调用 | 粒度 |
| --- | --- | --- |
| `fetch_recent_papers` | `_lookback_for_source("arxiv")` | aggregate（一次调用作用所有 9 个 cs.* 类目） |
| `fetch_recent_posts` | `_lookback_for_source(source_name)` per feed in `FEEDS` | 每条 RSS feed 独立 |
| `fetch_recent_sitemap_posts` | `_lookback_for_source(source.source_name)` per `SitemapSource` | 每条 sitemap 源独立 |
| `fetch_trending_repos` | `_lookback_for_source("github")` | aggregate（一次调用作用所有 17 个关键词） |

`run_ingestion(days_back=None)` 直接把 None 透传给所有 fetcher，每个 fetcher 自己计算窗口（log 里打 `days_back=per-source (cold-start aware)`）。`run_ingestion(days_back=N)` 显式 int 仍透传作 override（log 打 `days_back=N (explicit override)`），CI / 一次性 backfill 使用。

**用户可见效果**：在 `kb/ingestion/rss.py::FEEDS` 里加一行新 RSS feed `("https://x.com/feed", "X Blog")`，或在 `kb/ingestion/sitemap_blog.py::SITEMAP_SOURCES` 里加一条新 `SitemapSource(source_name="...", ...)`，**下次 daily 跑下去会只对这一条 source_name 做 30 天 backfill**（DB 里没有该 source_name 的行 → 命中冷启动分支），其它成熟源继续走窄窗——不再被某条最近被刷的 feed / arxiv 把窗口拉成 1 天。

**循环 import 规避**：`run.py` 在顶层 `from kb.ingestion.rss import ...` 等，4 个 fetcher 模块如果在顶层反向 `from kb.ingestion.run import _lookback_for_source` 会触发"partial module"错误。所有 4 个 fetcher 都用**函数体内的 lazy import**（仅在真的需要 per-source 计算时才执行），避开了模块加载时序问题。新增 fetcher 时务必沿用同款写法。

### 运维脚本（`kb/scripts/`）

| 脚本 | 作用 |
| --- | --- |
| `rescore_non_papers.py` | blog/project/talk 行可能已经 `is_processed=1` 但 `quality_score=0.0`；这个脚本枚举此类行并重新评分。支持 `--dry-run` / `--limit N` / `--source-type {blog,project,talk}` |

### Source-anchored chat 数据流（`/api/chat[/stream]` `paper_id` 模式）

```
POST /api/chat[/stream] {paper_id, query, history}
        │
        ▼
  _build_chat_context(req, db) (synchronous, in request handler):
    1. Paper.id 查询 (404 if missing — propagates to HTTP error before SSE)
    2. fetch_full_text(paper_id):
         a. paper.full_text 非空 → 直接返回
         b. _looks_like_pdf_url(pdf_url || url) → _download_pdf (20MB/30s)
            → _extract_text (pypdf) → 写回 Paper.full_text[:120 000] → 返回
         c. 否则 → summary + abstract fallback (不写库)
    3. prompt = template + full_text[:60 000] + _format_history(history)
        │
        ▼
  call_llm(prompt)              → ChatResponse(answer, sources=[that paper])
  /api/chat/stream:
  StreamingResponse(event_stream()):
    yield _sse_event("sources", {sources:[paper]})
    for chunk in stream_llm(prompt): yield _sse_event("token", {content:chunk})
    yield _sse_event("done", {})
```

---

## 七、测试与质量

测试套件已落地，详见 `backend/tests/README.md`。**~180 用例，<10 秒，无网络**。

| 测试文件 | 覆盖 |
| --- | --- |
| `conftest.py` | 隔离临时 SQLite、autouse `_init_db`、session 级 `client` |
| `test_api_smoke.py` | 路由注册、404、参数校验、Bearer Token 守卫、质量门、universal sort fields、`top_overall`、LIKE 通配符转义、旧 RSS dict-categories 兼容、chat `paper_id` 模式 prompt 含全文 token + sources 仅含目标 paper / `paper_id` 不存在 → 404 / `history[]` 注入 prompt / role pattern 校验（system 拒绝 422）/ `history` `max_length=40` 上限、**`/api/chat/stream` 5 例（`_drain_sse` 辅助；happy path 事件序列 sources→token→done + sources 仅含目标 paper + token 累计 = 完整输出 + 全文 token 进 prompt；history 注入；paper_id 不存在 → 流开始前 HTTP 404；空输出 → 占位 `(LLM produced no output)`；system role → 流开始前 422）** |
| `test_ingestion_arxiv.py` | 类目去重、cutoff、`save_papers` 幂等 |
| `test_ingestion_rss.py` | bozo / cutoff / dedup / 多 feed 聚合 / tags 规范化 / **per-feed 冷启动**（mature feed 1d 窗口丢弃 10d 老 entry，新 feed 30d 窗口保留） |
| `test_ingestion_sitemap_blog.py` | `_parse_iso_datetime` 多格式 / `_parse_loose_datetime` 含 `April 29, 2026` LMSYS 风格 / `_parse_sitemap` 命名空间 + 损坏 XML / `_extract_meta` 双向属性顺序 + entity 解码 / `_build_post` 形状契约 / 端到端 happy path（命中 1 条 + 跳过索引页 + 跳过 off-prefix）/ sitemap 网络失败 → [] / 损坏 sitemap → [] / `<lastmod>` 早于 cutoff 的 URL **跳过 fetch**（流量预算）/ 单页失败不影响其它 / 缺 og:title 跳过 / sitemap 无 lastmod 但 `article:published_time` 早 → 二次 cutoff 跳过 / fallback published_date 至 sitemap lastmod / **per-source 冷启动**（mature `SitemapSource` 1d 窗口跳过 10d 老 URL 不发 GET，fresh `SitemapSource` 30d 窗口保留）。**全程 `_FakeClient` 替换 `httpx.Client`，零真实网络** |
| `test_ingestion_run.py` | `_compute_days_back` 边界 + tz-naive 兼容、**`_lookback_for_source` 4 例（unknown source 走冷启动 / existing source 走 gap / 多 source 隔离 / `None` 等价 `_compute_days_back`）**、4 个 fetcher 同步 days_back 传播（默认 `None`，显式 int override 仍透传）|
| `test_ingestion_github.py` | auth 头、403 短路、polite sleep |
| `test_processing_llm.py` | provider 路由、`_clamp_score`、`_sanitize`、4 个 source_type rubric、质量门分桶、non-paper 永远 `is_processed=1`、paper 镜像到 legacy 字段、中文模式 prompt 注入、JSON 键必须英文、**`stream_llm` 5 例（路由到 `_STREAM_PROVIDERS[provider]`；mid-stream 异常被静默吞掉但保留已 yield 的 chunk；anthropic 路由；`_stream_hermes` 单 chunk fallback；`_call_hermes` 返空时 `_stream_hermes` 不 yield 空串）** |
| `test_processing_embeddings.py` | 单例锁、ML 缺失时优雅降级 |
| `test_processing_pdf.py` | 缓存命中 → 不下载；首次下载 + extract → 写回；非 PDF URL → abstract+summary fallback **不写库**；缺失 paper id → `""`；下载失败 → fallback **不污染缓存** |
| `test_reports.py` | happy / upsert / 空数据 / 中文模式标题与章节 / 非论文行参与排序 |
| `fixtures/` | arxiv / rss / github 静态 JSON 样本 |

> Mocking 约定：`_PROVIDERS` / `_STREAM_PROVIDERS` 字典在导入时即捕获函数引用，**测试必须 `monkeypatch.setitem(llm_mod._PROVIDERS, "...", mock)` / `monkeypatch.setitem(llm_mod._STREAM_PROVIDERS, "...", mock)`**，不能 `patch("kb.processing.llm._call_anthropic")`。
> 对 chat 测试 mock LLM：`monkeypatch.setattr(main_mod, "call_llm", _fake_call_llm)` / `monkeypatch.setattr(main_mod, "stream_llm", _fake_stream_llm)`（main 在导入时把它们拉进自己的命名空间）。
> 对 SSE 测试解码：用 `client.stream("POST", "/api/chat/stream", json=...)` + `iter_text()` 拼回完整 body，再按 `\n\n` 切帧，按行匹配 `event:` / `data:`（参考 `test_api_smoke.py::_drain_sse` 实现）。
> 对 PDF 测试 mock 网络：`monkeypatch.setattr(pdf_mod, "_download_pdf", lambda url: b"...")` + `monkeypatch.setattr(pdf_mod, "_extract_text", lambda blob: "...")`。

Lint：`ruff` 已在 `[dev]` extra 中。

---

## 八、CI（`.github/workflows/ci.yml`）

| Job | 内容 |
| --- | --- |
| `backend-tests` | Python 3.12 → `pip install -e '.[dev]' && pip install pytest-cov` → `pytest tests/ -x -q --cov=kb --cov-report=term-missing`；`KB_LLM_PROVIDER=hermes`（mock 层屏蔽真实 CLI） |
| `frontend-typecheck` | Node 20 → `npm ci` → `tsc --noEmit` + `eslint src/` |
| `frontend-e2e` | Node 20 → `npm ci` → `playwright install --with-deps chromium` → `npm run build && npm run test:e2e` |

新增/修改后端代码时务必本地 `pytest tests/ -x -q` 通过再推。

---

## 九、Docker / 部署

`backend/Dockerfile`：

- 基础镜像 `python:3.12-slim`；装 `build-essential` / `curl` / `ca-certificates`。
- `ARG INSTALL_EXTRAS=ml,llm-cloud` → `pip install ".[${INSTALL_EXTRAS}]"`；空串走 `pip install .`（最小镜像）。
- `VOLUME ["/app/data"]`，所有 SQLite + ChromaDB 文件持久化到 host bind-mount。
- `HEALTHCHECK` curl `/api/health`；compose 中 frontend 用 `service_healthy` 等待 backend。
- **`CMD ["uvicorn", "kb.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "75"]`**——`75 s` 必须 ≥ Next 反代连接池任何 idle 窗口，否则前端会随机 ECONNRESET → "Sorry, I couldn't process that query"。**SSE 流式响应天然依赖长 keep-alive**，对 `/api/chat/stream` 这条修复尤其关键。
- Dockerfile 注释里详述了 keep-alive 修复的来龙去脉（uvicorn 默认 5 s vs Next fetch agent 连接池）。

`docker-compose.yml` 内 backend 自动覆盖三个变量：

```yaml
KB_DATABASE_URL: sqlite:////app/data/kb.sqlite
KB_CHROMA_DIR: /app/data/chroma
KB_DATA_DIR: /app/data
KB_CORS_ORIGINS: '["http://localhost:3000","http://127.0.0.1:3000"]'
```

`daily` 服务复用 backend 镜像，靠 `profiles: ["cron"]` 隔离，需要 `docker compose --profile cron run --rm daily` 才会启动。

---

## 十、常见问题 (FAQ)

- **首次 `/api/chat[/stream]` 慢？** 正常，第一次会加载 SentenceTransformer 模型（5–10 秒）；`lifespan` 已在 `asyncio.create_task` 中后台预热，所以 startup 与 `/api/health` 立即可用。Source-anchored 模式首次 PDF 下载 + 抽取也会增加 5-15 秒，下次走 `Paper.full_text` 缓存。
- **`hermes` CLI 不存在？** `KB_LLM_PROVIDER=hermes` 时若 PATH 找不到 `hermes`，`call_llm` 返回空串并打 ERROR；`stream_llm` 走 `_stream_hermes` 也只会 yield 0 个 chunk（空字符串短路），SSE 端点会自动发占位 `(LLM produced no output)` token。改为 `anthropic` / `openai` / `deepseek` 即可。**Docker 镜像不带 hermes**——必须改 provider。
- **DeepSeek / OpenAI streaming 超时？** `_stream_openai_compatible` 已传 `timeout=settings.llm_timeout_seconds`；DeepSeek 长上下文响应可能 >60 秒，必要时调高 `KB_LLM_TIMEOUT_SECONDS`。
- **GitHub 429？** 必须设置 `GITHUB_TOKEN` 或 `KB_GITHUB_TOKEN`，无 token 限流极严。
- **新加路由位置敏感**：`/api/papers/search` 必须在 `/api/papers/{paper_id}` 之前；新增以 `/api/papers/<word>` 起头的路由也需排在动态路由之前。
- **`/api/chat[/stream]` 突然 401？** 检查 `KB_CHAT_TOKEN` 是否在 `.env` 或宿主环境被设置；前端目前未携带该头，开启 token 后需要在 `frontend/src/lib/api.ts` 中追加。
- **既存非论文行 `quality_score=0.0`？** 这是 universal scoring 之前 ingest 的行，跑一次 `python -m kb.scripts.rescore_non_papers --dry-run` 看清单，确认后去掉 `--dry-run` 即可回填。
- **修改 `KB_LANGUAGE` 后已有数据没变？** 语言只影响"未来打分 / 未来日报"，已存进 SQLite 的 `summary` / `score_rationale` / `daily_reports.content` 不会自动重译；如需切换可手动 `UPDATE papers SET is_processed=0 WHERE ...` 触发重处理。**注意**：本轮起 `/api/chat[/stream]` 的 prompt 已硬编码为中文，**不再受 `KB_LANGUAGE` 控制**——切换 chat 输出语言需要直接改 `_build_chat_context` 模板。
- **`run_daily_pipeline` 看到第一次跑了所有论文之后突然变慢？** 这就是处理 / 嵌入冷启动机制——第二次起每次只处理 / 嵌入 100 条；这是预期（与 ingest 回看无关）。
- **新加 RSS feed 后 daily 只抓到 0 篇？** 不会再发生。Per-source ingest 冷启动会探测到这个 `source_name` 在库里没有任何已入库行，下次 daily 自动给它 30 天 backfill（见 `_lookback_for_source`）。如果你之前手动跑过 `kb.ingestion.run --days-back 1` 已经种了一行就破坏了冷启动条件——清掉那行（`DELETE FROM papers WHERE source_name='...' AND ...`）让 source 重新进入冷启动状态，或显式 `python -m kb.ingestion.run --days-back 30` 兜底（注意：这是个 Python 模块，没有 `--days-back` CLI 参数，需手动改 `if __name__ == "__main__":` 调用或写一行临时脚本 `python -c "from kb.ingestion.run import run_ingestion; run_ingestion(days_back=30)"`）。
- **聊天页随机 "Sorry, I couldn't process that query"？** 通常是 uvicorn keep-alive 与 Next 反代连接池的 ECONNRESET 竞态；已在 `Dockerfile` 与 `run_api.sh` 加 `--timeout-keep-alive 75` 修复。如果仍发生，检查中间是否还有别的反代（cpolar / nginx）也需同步调高 idle timeout，并确保未对 `text/event-stream` 做缓冲（响应头 `X-Accel-Buffering: no` 已加，但部分代理需要全局开关）。
- **`/api/chat/stream` 返回 200 但前端没 token？** 排查链：① 查 `Network` 面板的 EventStream 视图看是否真有 `event: token` 帧到达；② 中间反代是否对 `text/event-stream` 做了 buffering（nginx 默认对 chunked response 缓冲）；③ provider 是否真的在 stream（hermes 一次性返回是预期的）；④ keep-alive 是否被 30 s 之类的极短 idle timeout 砍掉。
- **source-anchored chat 抽出的全文是乱码？** 多半是 URL 指向 HTML 页面而非 PDF 但被 `_looks_like_pdf_url` 误判；扩白名单时务必 `.endswith(".pdf")` 或显式 substring，否则 pypdf 解析 HTML 会输出乱码并被缓存。需要时手动 `UPDATE papers SET full_text='' WHERE id=...` 清缓存。
- **PDF 太大 / 网络太慢？** `_MAX_PDF_BYTES=20 MB`、`_DOWNLOAD_TIMEOUT_S=30 s`；任何超量都返回 `None` 并 fallback 到 abstract+summary，**不会 OOM 或挂住请求**。

---

## 十一、相关文件清单（精选）

```
backend/
├─ pyproject.toml          # 依赖与 extras（含默认 pypdf>=5）
├─ Dockerfile              # python:3.12-slim 多阶段；CMD 含 --timeout-keep-alive 75
├─ .dockerignore           # 排除 data/ / tests/ / __pycache__ / .env
├─ run_api.sh              # uvicorn ... --reload --timeout-keep-alive 75
├─ tests/
│  ├─ README.md            # 测试套件说明（~115 用例）
│  ├─ conftest.py
│  ├─ test_api_smoke.py    # 含 Bearer Token / 质量门 / universal sort / chat paper_id+history / SSE 5 例
│  ├─ test_ingestion_*.py
│  ├─ test_processing_llm.py # 含 4-rubric / 中文模式 / JSON 失败重试 / stream_llm 5 例
│  ├─ test_processing_embeddings.py
│  ├─ test_processing_pdf.py  # PDF 缓存 / 下载 / fallback
│  ├─ test_reports.py
│  └─ fixtures/
└─ kb/
   ├─ main.py              # FastAPI 应用 / 路由 / verify_chat_token / _build_chat_context / chat & chat_stream / _sse_event / _format_history
   ├─ config.py            # Pydantic Settings
   ├─ database.py          # engine / SessionLocal / init_db / 兼容列(含 full_text)+索引
   ├─ models.py            # Paper（含 universal axes + full_text）/ DailyReport
   ├─ schemas.py           # PaperOut / ChatMessage / ChatRequest（paper_id + history）/ ChatResponse
   ├─ daily.py             # 全流水线编排（冷启动检测 + --lang）
   ├─ reports.py           # 日报生成（按 max(quality, relevance) 排序 / 中文模式）
   ├─ ingestion/
   │  ├─ arxiv.py
   │  ├─ rss.py            # 11 源 + tag 规范化
   │  ├─ github_trending.py
   │  └─ run.py            # _lookback_for_source per-source 冷启动 + run_ingestion 透传 None / int
   ├─ processing/
   │  ├─ llm.py            # provider 抽象（4 种）+ 4 rubric + 中英双语 + stream_llm + _stream_openai_compatible 公共体
   │  ├─ embeddings.py     # ChromaDB + sentence-transformers
   │  └─ pdf.py            # fetch_full_text / _download_pdf / _extract_text / abstract fallback
   └─ scripts/
      └─ rescore_non_papers.py  # 一次性回填非论文 universal scores
```

---

## 十二、变更记录 (Changelog)

| 时间 | 操作 | 说明 |
| --- | --- | --- |
| 2026-04-25 09:59:45 | 初始化 | 自动生成 backend 模块 `CLAUDE.md` |
| 2026-04-25 15:26:48 | 增量刷新 | 新增 `deepseek` provider 文档；补充 `/api/chat` 的 `verify_chat_token` Bearer 守卫细节与 `hmac.compare_digest` 约定；新增 `KB_CHAT_TOKEN` / `KB_DEEPSEEK_*` / `KB_CHAT_QUERY_MAX_LEN` / `KB_CHAT_TOP_K_MAX` 配置；同步 `backend/tests/README.md`；新增"CI"章节 |
| 2026-04-25 16:50 | 质量门 | 新增 `KB_QUALITY_SCORE_THRESHOLD`（默认 7.0），`summarize_and_score` 落桶 `is_processed=1`/`2`/`0`；阈值用 `max(originality, impact)` 比较；`/api/papers` 与 `/api/papers/search` 默认仅返 `is_processed=1`；`/api/stats` 拆三档；新增 8 个测试覆盖分桶逻辑 |
| 2026-05-02 08:57:04 | 增量刷新 | ① Universal Score Axes（4 rubrics + paper legacy 镜像 + universal sort + top_overall）② 中文 LLM 输出 `KB_LANGUAGE` ③ Docker 镜像 + compose ④ 自适应 ingest 回看窗 ⑤ 冷启动批处理 ⑥ 运维脚本 `rescore_non_papers.py` ⑦ RSS 源精简到 11 个 ⑧ schemas `categories` field_validator |
| 2026-05-02 20:12:04 | 增量刷新 | ① `/api/chat` 多轮 + source-anchored 双模式：`schemas.ChatMessage` (`role` ∈ {user, assistant})；`ChatRequest.paper_id: int \| None` + `history: list[ChatMessage]`（`max_length=40`）；`main.py::_format_history`（`_HISTORY_TURN_CAP=12`，单条 4 000 字符 cap）；`paper_id` 模式跳过 RAG，调 `fetch_full_text` 拼 prompt（≤60 000 字符），`sources` 仅返该 paper，缺失 → 404。② `kb/processing/pdf.py`（新）：`fetch_full_text(paper_id)` — `httpx.Client.stream` 流式下载（20 MB / 30 s 上限）→ `pypdf.PdfReader` 抽取 → `[:120 000]` 截断写回 `Paper.full_text`；非 PDF URL → `summary + abstract` fallback **且不写库**；`Paper.full_text` 列加入 `_BACKCOMPAT_COLUMNS`；`pypdf>=5.0` 提为默认依赖。③ uvicorn keep-alive：`Dockerfile.CMD` 与 `run_api.sh` 都加 `--timeout-keep-alive 75`，修复 Next 反代 ECONNRESET 竞态。④ 测试：新增 `tests/test_processing_pdf.py`（5 例），`test_api_smoke.py` 加 5 例 chat-mode；套件 ~95 → ~105。 |
| 2026-05-02 21:18:53 | 增量刷新 | ① **`/api/chat/stream` SSE 端点（新）**（`kb/main.py`）：返回 `text/event-stream`，事件序列固定 `sources → token... → done`，可选 `error`；token 流空时发占位 `(LLM produced no output)`；header `Cache-Control: no-cache` + `X-Accel-Buffering: no`；**与 `/api/chat` 共享 `verify_chat_token` 守卫与新抽出的 `_build_chat_context(req, db) -> (prompt, sources)`**——HTTPException（如 paper_id 404）必须在 `event_stream()` 之外抛出，让客户端见到正常 HTTP 错误而非空 SSE。新增 `_sse_event(event, data)` helper（`json.dumps(..., ensure_ascii=False)` 保中文紧凑）。② **`stream_llm` 抽象（新）**（`kb/processing/llm.py`）：与 `call_llm` 平行的公开 API；`_STREAM_PROVIDERS = {hermes, anthropic, openai, deepseek}`；任何 provider 失败静默 `return`（generator 结束，从不 raise，对齐 `call_llm` 的空字符串契约）。`_stream_anthropic` 走 `client.messages.stream(...).text_stream`；新抽出 `_stream_openai_compatible(api_key, model, base_url=None)` 公共体被 `_stream_openai` 与 `_stream_deepseek` 复用（`stream=True` + `chunk.choices[0].delta.content`）；`_stream_hermes` 因子进程不能真正流式，实现为"调 `_call_hermes` 拿全文 → yield 单 chunk（空字符串则不 yield）"。③ **Chat 系统 prompt 改为中文硬编码**（`_build_chat_context`）：从英文 "You are an expert GPGPU chip architect ..." 改成 "你是一名资深的 GPGPU 芯片架构助理 ..."，结尾"请用简体中文作答"。**`KB_LANGUAGE` 不再影响 chat prompt（仅影响 summarization / scoring / reports）**；要回退英文需直接改模板。④ **`backend/Dockerfile` / `backend/run_api.sh`** 内容相对上轮无新 delta（`--timeout-keep-alive 75` 已在位），但本轮 SSE 长连接对其依赖性更强，Dockerfile 注释新增 ECONNRESET 竞态背景说明（uvicorn 5 s 默认 vs Next fetch agent 连接池）。⑤ **测试**：`test_api_smoke.py` 加 5 例 SSE（`_drain_sse` 辅助 + happy path 事件序列校验 + history 注入 + 404 在流开始前抛 + 空输出占位 + system role 422）；`test_processing_llm.py` 加 5 例 streaming（路由 / 异常静默吞掉但保留已 yield chunk / anthropic 路由 / hermes fallback / hermes 空时不 yield）。套件 ~105 → ~115。所有 delta 已通过直接读取 `kb/main.py` / `kb/processing/llm.py` / `tests/test_api_smoke.py` / `tests/test_processing_llm.py` / `Dockerfile` / `run_api.sh` 源码核对。 |
| 2026-05-02 23:32:00 | 增量刷新 | 新增博客来源（vLLM Blog 进 RSS FEEDS / LMSYS · SGLang Blog 走 sitemap-driven scraper）+ 新模块 `kb/ingestion/sitemap_blog.py`（`SitemapSource` dataclass + sitemap.xml 解析 + per-page og:* meta 抽取 + 60 篇/源 上限）+ `kb/ingestion/run.py` 编排独立 stage `results["sitemap_blogs"]` + 30 例左右 sitemap_blog 单元测试 + orchestrator 测试升级到 4 fetcher。套件 ~115 → 174 pass。 |
| **2026-05-03 09:44:00** | **增量刷新** | **Per-`source_name` ingest 冷启动**。① **`kb/ingestion/run.py`**：新增 `_lookback_for_source(source_name: str \| None)`（带可选 `WHERE Paper.source_name = :name` 过滤），与 `_compute_days_back` 共用 clamp 逻辑；该 source_name 下 MAX(ingested_date) 为 NULL → `settings.ingest_empty_db_days`（30）走冷启动。`_compute_days_back()` 退化为 `_lookback_for_source(None)` 薄包装。`run_ingestion(days_back: int \| None)` 不再在顶部统一算一次——直接透传 None / int 给 4 个 fetcher，每个自己决定窗口；日志区分 `per-source (cold-start aware)` 与 `explicit override`。② **fetcher 签名统一为 `days_back: int \| None`**：`fetch_recent_papers` 调 `_lookback_for_source("arxiv")`、`fetch_trending_repos` 调 `_lookback_for_source("github")`（aggregate `source_name`，行为与今天一致）；`fetch_recent_posts` 在 `for feed_url, source_name in FEEDS` 循环里 per-feed 调用（每条 feed 独立打 `[rss] X: lookback=Yd`）；`fetch_recent_sitemap_posts` 在 `for source in SITEMAP_SOURCES` 循环里 per-`SitemapSource` 调用。**4 个 fetcher 都用函数体内的 lazy import 取 `_lookback_for_source`** 避开 run.py ↔ 4 个 fetcher 模块的双向 top-level import 顺序问题。③ **效果**：在 `FEEDS` 加新 feed 或 `SITEMAP_SOURCES` 加新源后，下次 daily 自动只对那条新 source_name 做 30 天 backfill。④ **测试**：`test_ingestion_run.py` `_seed_paper` 加 `source_name` 形参；新增 4 例 `_lookback_for_source` 单元（unknown source 走冷启动 / existing source 走 gap / 多 source 隔离 / `None` 等价 `_compute_days_back`）；`_spy_run_ingestion` 改捕 `int \| None`；`test_run_ingestion_propagates_cold_start_window_to_all_sources` → `test_run_ingestion_default_propagates_none_to_all_sources`（断言 4 fetcher 都收 None）；override 测试不变。`test_ingestion_rss.py` 加 `test_per_feed_cold_start_when_days_back_is_none`（mature feed 1d 窗口丢弃 10d 老 entry / fresh feed 30d 窗口保留）。`test_ingestion_sitemap_blog.py` 加 `test_per_source_cold_start_when_days_back_is_none`（mature `SitemapSource` per-source pre-filter 阻止 GET / fresh `SitemapSource` 保留）。⑤ **测试套件 174 → 180 pass**（`pytest tests/ -q` 离线 6.6s）。⑥ **`daily.py::_is_cold_start` / `_is_embedding_cold_start`** 不动（处理 / 嵌入批冷启动是不同维度）；`KB_INGEST_*` config 沿用；API / 前端 / DB / migration 不动。⑦ **CLAUDE.md** 同步：第三章 fetcher 表更新；第六章新增"Per-Source ingest 冷启动"段落详述 4 fetcher 粒度矩阵 + lazy import 规避循环；测试表加新覆盖；变更记录新增本条目。所有 delta 已通过直接读取 `kb/ingestion/run.py` / `kb/ingestion/rss.py` / `kb/ingestion/sitemap_blog.py` / `kb/ingestion/arxiv.py` / `kb/ingestion/github_trending.py` / `tests/test_ingestion_run.py` / `tests/test_ingestion_rss.py` / `tests/test_ingestion_sitemap_blog.py` 源码核对。 |
