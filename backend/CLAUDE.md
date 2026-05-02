# backend/ — Python / FastAPI 服务

[← 返回根](../CLAUDE.md) > **backend**

> 由 `init-architect` 于 `2026-04-25 09:59:45` 自动生成，
> 于 `2026-04-25 15:26:48` 增量刷新（DeepSeek provider / Bearer Token / pytest 套件落地），
> 于 `2026-04-25 16:50` 增量刷新（质量门 `is_processed=2` / `KB_QUALITY_SCORE_THRESHOLD`），
> 于 **`2026-05-02 08:57:04`** 增量刷新（**Universal Score Axes / 中文 LLM 输出 / Docker 镜像 / 自适应 ingest 回看窗 / 冷启动批处理 / 非论文 rescore 脚本 / RSS 源精简**）。

---

## 一、模块职责

后端承担四件事：

1. **采集（ingestion）**：从 ArXiv / RSS / GitHub Search 拉取近期内容，按 `Paper.url` 唯一索引去重写入 SQLite；回看窗自动适配上次成功时间。
2. **处理（processing）**：调用 LLM 对每条记录生成 ~3-5 段技术摘要，并按 `source_type` 切换 rubric 打两维 0-10 分（universal axes：`quality_score` / `relevance_score`）；之后用 sentence-transformers 生成嵌入并写入 ChromaDB。
3. **服务（API）**：FastAPI 暴露浏览 / 详情 / 搜索 / RAG 聊天 / 日报 / 统计 / 健康检查端点；可选 Bearer Token 守卫 `/api/chat`。
4. **报告（reports）**：每天聚合当日已处理论文与博客/项目，产出一份 Markdown 简报存入 `daily_reports`（按 `max(quality, relevance)` 排序，使非论文也能上榜）。

---

## 二、入口与启动

| 入口 | 作用 |
| --- | --- |
| `kb/main.py` (`app = FastAPI(...)`) | API 应用对象；`lifespan` 中初始化日志、`init_db()`、后台预热 EmbeddingStore（`asyncio.create_task`，不阻塞 startup） |
| `kb/daily.py` (`run_daily_pipeline`) | 完整每日流水线（ingest → process → embed → report）；冷启动检测 + `--lang zh` 切换 |
| `kb/ingestion/run.py` (`run_ingestion`) | 仅运行采集阶段；`_compute_days_back()` 自适应回看窗 |
| `kb/processing/llm.py` (`run_processing`) | 仅运行 LLM 处理阶段，`batch_size=None` 表示无上限 |
| `kb/processing/embeddings.py` (`index_unindexed_papers`) | 仅运行向量化阶段，`batch_size=None` 表示无上限 |
| `kb/reports.py` (`generate_daily_report`) | 仅生成日报（默认昨天，upsert） |
| `kb/scripts/rescore_non_papers.py` | **运维脚本**：回填非论文行 universal scores（支持 `--dry-run` / `--limit` / `--source-type`） |
| `run_api.sh` | `uvicorn kb.main:app --host 0.0.0.0 --port 8000 --reload` |
| `Dockerfile` | `python:3.12-slim` 多阶段镜像；`ARG INSTALL_EXTRAS=ml,llm-cloud` 控制大小；`HEALTHCHECK` 走 `/api/health` |

启动命令：

```bash
cd backend
source .venv/bin/activate
./run_api.sh                                       # 开发：带 --reload
python -m kb.daily                                 # 跑一遍完整流水线（语言由 KB_LANGUAGE 决定）
python -m kb.daily --lang zh                       # 命令行覆盖为中文
python -m kb.ingestion.run                         # 仅采集
python -m kb.reports                               # 仅生成昨天的报告
python -m kb.scripts.rescore_non_papers --dry-run  # 列出需要回填的非论文行
python -m pytest tests/ -x -q                      # 跑测试 (~95 例)
```

---

## 三、对外接口（FastAPI 路由）

定义文件：`kb/main.py`

| 方法 + 路径 | 函数 | 说明 |
| --- | --- | --- |
| `GET  /api/papers` | `list_papers` | 分页列出，按 `source_type` 过滤；`sort_by` 支持 `published_date` / `impact_score` / `originality_score` / **`quality_score`** / **`relevance_score`** / **`total_score`**（默认） / `ingested_date`；`total_score` 对应 `originality + impact + quality + relevance` 之和（paper / 非 paper 两组互斥，求和等价于行总分）。**默认仅返回 `is_processed=1`**，加 `?include_low_quality=true` 同时返回 `0`/`2` |
| `GET  /api/papers/search` | `search_papers` | `q` 必填；`semantic=true` 走 ChromaDB（仅含 `is_processed=1`），无结果回退 ILIKE（用 `_escape_like` 转义 `%` `_` `\`）。**注意路由顺序：search 必须在 `{paper_id}` 之前** |
| `GET  /api/papers/{paper_id}` | `get_paper` | 单条详情；**不过滤** `is_processed` |
| `POST /api/chat` | `chat` | RAG：先向量召回 `top_k`，再喂给 LLM；返回 `answer + sources[]`。**受 `verify_chat_token` 守卫**：若 `KB_CHAT_TOKEN` 已设置，必须带 `Authorization: Bearer <token>` |
| `GET  /api/reports` | `list_reports` | 倒序列出最近 N 份日报 |
| `GET  /api/reports/{report_id}` | `get_report` | 单份日报（Markdown）|
| `GET  /api/stats` | `get_stats` | `total_papers` / `processed` / `skipped_low_quality` / `pending` / `by_type` / `top_impact`（5 条，legacy paper-only）/ **`top_overall`**（5 条，按 `max(quality, relevance)` 跨类型 ranking） |
| `GET  /api/health` | `health` | 存活探针，返回 `{"status":"ok"}`（HEALTHCHECK 指标） |

Swagger UI：`http://localhost:8000/docs`

### Bearer Token 守卫细节（`verify_chat_token`）

- 配置项：`settings.chat_token`（来源 `KB_CHAT_TOKEN`）。
- 未设置 → 端点开放（无摩擦本地开发）。
- 已设置 → 需 `Authorization: Bearer <token>`；缺头或前缀不对返回 401 `Missing bearer token`；值不匹配返回 401 `Invalid bearer token`。
- **比较使用 `hmac.compare_digest`**（防侧信道）；新增类似认证端点请复用同款写法，禁止 `==`。

---

## 四、关键依赖与配置

`pyproject.toml` 三组可选依赖：

| Extra | 提供 | 触发 |
| --- | --- | --- |
| 默认 | FastAPI / Uvicorn / SQLAlchemy 2 / Pydantic 2 / arxiv / feedparser / httpx / python-dotenv | 必装 |
| `[ml]` | chromadb · sentence-transformers（~2GB） | 想要语义检索 / RAG |
| `[llm-cloud]` | anthropic · openai（DeepSeek 复用 openai SDK，无需新依赖） | 走云端 LLM |
| `[dev]` | pytest · pytest-asyncio · httpx · ruff | 测试 / lint |

> CI 中使用 `pip install -e '.[dev]'` + `pytest-cov`；**故意不装 `[ml]`** 以加快流水线，相关测试以 `pytest.mark.skipif` 自动跳过。
> Docker 镜像通过 `ARG INSTALL_EXTRAS=ml,llm-cloud` 控制；改成 `llm-cloud` 或空串可瘦身镜像（搜索自动降级到关键字）。

设置类：`kb/config.py` 的 `Settings(BaseSettings)`，前缀 `KB_`，亦读取 `backend/.env`（`load_dotenv` 在构造前先注入 `os.environ`，让无前缀的便利变量生效）。
该 settings 还接受不带前缀的 `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` / `GITHUB_TOKEN` 作为便利兜底。

新增 / 当前完整字段（见 `kb/config.py`）：

| 字段 | 默认 | 来源环境变量 | 用途 |
| --- | --- | --- | --- |
| `language` | `en` | `KB_LANGUAGE` | LLM 输出语言 (`en` / `zh`) |
| `llm_provider` | `hermes` | `KB_LLM_PROVIDER` | 路由到 `_PROVIDERS` |
| `llm_timeout_seconds` | `180` | `KB_LLM_TIMEOUT_SECONDS` | hermes / deepseek 超时 |
| `anthropic_api_key` / `model` | – / `claude-sonnet-4-6` | `KB_ANTHROPIC_*` / `ANTHROPIC_API_KEY` | – |
| `openai_api_key` / `model` | – / `gpt-4o-mini` | `KB_OPENAI_*` / `OPENAI_API_KEY` | – |
| `deepseek_api_key` / `model` / `base_url` | – / `deepseek-chat` / `https://api.deepseek.com` | `KB_DEEPSEEK_*` / `DEEPSEEK_API_KEY` | OpenAI 兼容协议 |
| `github_token` | – | `KB_GITHUB_TOKEN` / `GITHUB_TOKEN` | GitHub Search 限流 |
| `arxiv_per_category` | `50` | `KB_ARXIV_PER_CATEGORY` | – |
| `ingest_empty_db_days` | `30` | `KB_INGEST_EMPTY_DB_DAYS` | 冷启动回看天数 |
| `ingest_gap_min_days` | `1` | `KB_INGEST_GAP_MIN_DAYS` | 自适应回看窗下限 |
| `ingest_gap_max_days` | `30` | `KB_INGEST_GAP_MAX_DAYS` | 自适应回看窗上限（防多月重摄入） |
| `quality_score_threshold` | `7.0` | `KB_QUALITY_SCORE_THRESHOLD` | 质量门（仅 paper 生效） |
| `chat_query_max_len` | `2000` | `KB_CHAT_QUERY_MAX_LEN` | `/api/chat` & 搜索输入上限 |
| `chat_top_k_max` | `20` | `KB_CHAT_TOP_K_MAX` | RAG `top_k` 上限 |
| `chat_token` | – | `KB_CHAT_TOKEN` | `/api/chat` Bearer Token |
| `cors_origins` | `["http://localhost:3000"]` | `KB_CORS_ORIGINS` | CORS（推荐让前端走 Next `/api/*` 反代代替放宽 CORS） |
| `data_dir` | `./data` | `KB_DATA_DIR` | 数据根；Docker 内是 `/app/data` |
| `database_url` | `sqlite:///./data/kb.sqlite` | `KB_DATABASE_URL` | – |
| `chroma_dir` | `./data/chroma` | `KB_CHROMA_DIR` | ChromaDB 持久化目录 |
| `embedding_model` | `all-MiniLM-L6-v2` | `KB_EMBEDDING_MODEL` | – |

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
| `pdf_url` | str(1000) | – |
| `source_type` | Enum(`paper`/`blog`/`talk`/`project`) | 默认 `paper`，索引 |
| `source_name` | str(200) | 例如 `arxiv`、`OpenAI`、`github` |
| `published_date` / `ingested_date` | DateTime(tz) | `ingested_date` 索引，UTC |
| `venue` | str(200) | 默认空 |
| `citation_count` | int | 预留字段 |
| `summary` | Text | LLM 输出 |
| `originality_score` / `impact_score` | float | **legacy 兼容字段**：仅对 `paper` 行从 universal axes 镜像；`impact_score` 索引 |
| `impact_rationale` | Text | legacy；paper 行从 `score_rationale` 镜像 |
| **`quality_score`** | float | **universal axis #1**（0-10），按 `source_type` 语义切换；索引 |
| **`relevance_score`** | float | **universal axis #2**（0-10），按 `source_type` 语义切换 |
| **`score_rationale`** | Text | universal 评分理由（中文模式下为中文） |
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

1. `_BACKCOMPAT_COLUMNS`：`PRAGMA table_info(papers)` 探测后幂等 `ALTER TABLE` 加列：`quality_score` / `relevance_score` / `score_rationale`。
2. `_BACKCOMPAT_INDEXES`：`CREATE INDEX IF NOT EXISTS` 补加 `ix_papers_url` / `source_type` / `is_processed` / `impact_score` / `quality_score` / `ingested_date`。

这样既兼容 2026-04-25 之前生成的旧 `kb.sqlite`，又允许迁移到 Postgres 走 alembic（`_ensure_papers_columns` 仅在 `database_url.startswith("sqlite")` 时执行）。

---

## 六、采集与处理细节

### `kb/ingestion/`

| 文件 | 职责 | 关键点 |
| --- | --- | --- |
| `arxiv.py` | 9 个 cs.* 类目逐一查，按 `submitted_date` 倒排，截至 `cutoff` | 单查询而非 OR，避免高量类目（cs.AI）饿死其它 |
| `rss.py` | **11 个精选 RSS 源**（截至 2026-04 验证可用） | `feedparser`；`bozo` 仅警告不拒收；`_tag_to_str` 把 feedparser 的 `term/scheme/label` 字典规范化为 `list[str]` 入库 |
| `github_trending.py` | GitHub Search API 按 17 个关键词查 `pushed:>yesterday` | 无 token 时 10 req/min 易 429，建议设 `GITHUB_TOKEN`；带 token 后切到带 polite sleep 的 30 req/min 路径 |
| `run.py` | 编排上述三步，每步独立 try/except；**`_compute_days_back` 自适应回看窗** | 单源失败不影响其它；空库 → `KB_INGEST_EMPTY_DB_DAYS`，否则 `now - max(ingested_date)` clamped 到 `[min, max]` |

去重统一采用 `Paper.url` 是否已存在。

#### 已下线的 RSS 源（已从 `FEEDS` 移除）

- AnandTech（站点 2024 年关停，`/rss` 重定向到论坛 HTML）
- Meta AI Blog（`ai.meta.com/blog/feed/` 返回 404，无公开 RSS）

### `kb/processing/`

| 文件 | 职责 | 关键点 |
| --- | --- | --- |
| `llm.py` | provider 抽象 + 摘要/打分流水线 | `_PROVIDERS = {hermes, anthropic, openai, deepseek}`；任何 provider 异常一律返回 `""` 不抛 |
| `embeddings.py` | ChromaDB + sentence-transformers，懒加载单例 | 没装 ML 依赖时 `available=False`，`search()` 返回空列表，调用方自然降级；`get_embedding_store()` 用 `threading.Lock` 串行化首次构造 |

### Provider 矩阵（`call_llm`）

| `KB_LLM_PROVIDER` | 实现 | 依赖 |
| --- | --- | --- |
| `hermes`（默认） | `subprocess.run(["hermes", "ask", ...])` | 系统装有 `hermes` CLI；**容器中不可用** |
| `anthropic` | `anthropic.Anthropic(...).messages.create(...)` | `pip install -e '.[llm-cloud]'` + `ANTHROPIC_API_KEY` |
| `openai` | `openai.OpenAI(...).chat.completions.create(...)` | `pip install -e '.[llm-cloud]'` + `OPENAI_API_KEY` |
| `deepseek` | `openai.OpenAI(api_key=DEEPSEEK_API_KEY, base_url=KB_DEEPSEEK_BASE_URL).chat.completions.create(...)` | `pip install -e '.[llm-cloud]'` + `DEEPSEEK_API_KEY`（**复用 openai SDK，无需额外依赖**） |

### Prompt 安全 / 多语言

- `_sanitize()` 限长 8000 chars + ``` → `ʼʼʼ`。
- prompt 包裹 `=== UNTRUSTED START === / END ===`，并提示模型"只视为数据"。
- `_lang_instruction()`（zh）：在 summary prompt 末尾追加 `Write your entire response in Chinese (简体中文)`。
- `_impact_lang_instruction()`（zh）：仅在 score prompt 末尾追加 `Write the "impact_rationale" value in Chinese... Keep all JSON keys and numeric scores in English/ASCII.`——**JSON 键必须英文**，否则 `summarize_and_score` 会返回 `False`，留 `is_processed=0` 等待重试。

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
- 阈值通过 `settings.quality_score_threshold` 读取，**不要**直接硬编码 7.0；调高/调低只通过环境变量。
- 修改阈值**不会**回溯既存 `is_processed=1` 数据——只对新打分的论文生效。如需回填，写一次性 SQL `UPDATE papers SET is_processed=2 WHERE is_processed=1 AND ...`。
- ChromaDB 通过 `index_unindexed_papers` 仅索引 `is_processed=1`，所以语义搜索无需额外过滤；关键字 fallback 路径在 `main.py` 显式过滤。

### 冷启动批处理（`kb.daily`）

`run_daily_pipeline` 启动时探测：

- **处理冷启动**：`Paper.is_processed != 0` 全为空 → `run_processing(batch_size=None)`，否则默认 100 条/run。
- **嵌入冷启动**：`Paper.is_processed == 1 && chroma_id != ""` 全为空 → `index_unindexed_papers(batch_size=None)`，否则 100 条/run。

目的：避免后到的 RSS / GitHub 项目被 ArXiv 队列前缀（一次 ingestion 可能新增几百行）饿死。

### 运维脚本（`kb/scripts/`）

| 脚本 | 作用 |
| --- | --- |
| `rescore_non_papers.py` | 在 universal axes 上线前，blog/project/talk 行可能已经 `is_processed=1` 但 `quality_score=0.0`；这个脚本枚举此类行并重新评分。支持 `--dry-run` / `--limit N` / `--source-type {blog,project,talk}` |

---

## 七、测试与质量

测试套件已落地，详见 `backend/tests/README.md`。**~95 用例，<2 秒，无网络**。

| 测试文件 | 覆盖 |
| --- | --- |
| `conftest.py` | 隔离临时 SQLite、autouse `_init_db`、session 级 `client` |
| `test_api_smoke.py` | 路由注册、404、参数校验、**Bearer Token 守卫**（开放 / 缺 token / 错 token 三态）、**质量门**（默认隐藏 `is_processed!=1`、`?include_low_quality=true` 旁路、单篇详情不过滤、stats 三档计数）、**universal sort fields**（`quality_score` / `relevance_score`）、`top_overall`、LIKE 通配符转义、旧 RSS dict-categories 兼容（`{'term', 'scheme', 'label'}` → `list[str]`） |
| `test_ingestion_arxiv.py` | 类目去重、cutoff、`save_papers` 幂等 |
| `test_ingestion_rss.py` | bozo / cutoff / dedup / 多 feed 聚合 / **tags 规范化** |
| `test_ingestion_github.py` | auth 头、403 短路、polite sleep |
| `test_processing_llm.py` | provider 路由、`_clamp_score`、`_sanitize`、4 个 source_type rubric 各自验证关键词（`FAANG`/`TECHNICAL DEPTH`/`INNOVATION`/`MATURITY`/`ACTIONABILITY`）、**质量门分桶**（高分→1 / 低分→2 / 高 originality 救场→1 / JSON 失败→保留 0 等待重试 / 翻译键名→保留 0）、**non-paper 永远 `is_processed=1`**（含 1.0/1.0 极低分）、**paper 镜像到 legacy 字段**、**中文模式 prompt 注入**（summary 全中文 / score prompt 不全中文） |
| `test_processing_embeddings.py` | 单例锁、ML 缺失时优雅降级 |
| `test_reports.py` | happy / upsert / 空数据 / **中文模式标题与章节** / **非论文行参与排序**（验证 blog 因 `max(quality, relevance)` 高于 paper 时排在 prompt 前面 + Depth/Actionability 标签出现） |
| `fixtures/` | arxiv / rss / github 静态 JSON 样本 |

覆盖率（与 README 一致）：ingestion 90–92% · reports 94% · llm 65% · embeddings 59%（多数代码靠 `[ml]` extra 才能跑） · 整体 **74%**。

> Mocking 约定：`_PROVIDERS` 字典在导入时即捕获函数引用，**测试必须 `monkeypatch.setitem(llm_mod._PROVIDERS, "...", mock)` 或 `patch.dict(llm_mod._PROVIDERS, {...})`**，不能 `patch("kb.processing.llm._call_anthropic")`。

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
- `CMD ["uvicorn", "kb.main:app", "--host", "0.0.0.0", "--port", "8000"]`（无 `--reload`）。

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

- **首次 `/api/chat` 慢？** 正常，第一次会加载 SentenceTransformer 模型（5–10 秒）；`lifespan` 已在 `asyncio.create_task` 中后台预热，所以 startup 与 `/api/health` 立即可用。
- **`hermes` CLI 不存在？** `KB_LLM_PROVIDER=hermes` 时若 PATH 找不到 `hermes`，`call_llm` 返回空串并打 ERROR；改为 `anthropic` / `openai` / `deepseek` 即可。**Docker 镜像不带 hermes**——必须改 provider。
- **DeepSeek 模型超时？** `_call_deepseek` 已传 `timeout=settings.llm_timeout_seconds`；DeepSeek 长上下文响应可能 >60 秒，必要时调高 `KB_LLM_TIMEOUT_SECONDS`。
- **GitHub 429？** 必须设置 `GITHUB_TOKEN` 或 `KB_GITHUB_TOKEN`，无 token 限流极严。
- **新加路由位置敏感**：`/api/papers/search` 必须在 `/api/papers/{paper_id}` 之前；新增以 `/api/papers/<word>` 起头的路由也需排在动态路由之前。
- **`/api/chat` 突然 401？** 检查 `KB_CHAT_TOKEN` 是否在 `.env` 或宿主环境被设置；前端目前未携带该头，开启 token 后需要在 `frontend/src/lib/api.ts` 中追加。
- **既存非论文行 `quality_score=0.0`？** 这是 universal scoring 之前 ingest 的行，跑一次 `python -m kb.scripts.rescore_non_papers --dry-run` 看清单，确认后去掉 `--dry-run` 即可回填。
- **修改 `KB_LANGUAGE` 后已有数据没变？** 语言只影响"未来打分 / 未来日报"，已存进 SQLite 的 `summary` / `score_rationale` / `daily_reports.content` 不会自动重译；如需切换可手动 `UPDATE papers SET is_processed=0 WHERE ...` 触发重处理。
- **`run_daily_pipeline` 看到第一次跑了所有论文之后突然变慢？** 这就是冷启动机制——第二次起每次只处理 100 条；这是预期。

---

## 十一、相关文件清单（精选）

```
backend/
├─ pyproject.toml          # 依赖与 extras
├─ Dockerfile              # python:3.12-slim 多阶段
├─ .dockerignore           # 排除 data/ / tests/ / __pycache__ / .env
├─ run_api.sh              # uvicorn 启动脚本
├─ tests/
│  ├─ README.md            # 测试套件说明（~95 用例 / 74% 覆盖率）
│  ├─ conftest.py
│  ├─ test_api_smoke.py    # 含 Bearer Token / 质量门 / universal sort
│  ├─ test_ingestion_*.py
│  ├─ test_processing_*.py # 含 4-rubric / 中文模式 / JSON 失败重试
│  ├─ test_reports.py      # 含中文模式 / 非论文参与排序
│  └─ fixtures/
└─ kb/
   ├─ main.py              # FastAPI 应用 / 路由 / verify_chat_token / total_score 排序
   ├─ config.py            # Pydantic Settings（含 deepseek / language / ingest_gap_* / chat_token / quality_score_threshold）
   ├─ database.py          # engine / SessionLocal / init_db / 兼容列+索引
   ├─ models.py            # Paper（含 universal axes）/ DailyReport
   ├─ schemas.py           # PaperOut（含 universal + categories field_validator）/ ChatRequest / ChatResponse
   ├─ daily.py             # 全流水线编排（冷启动检测 + --lang）
   ├─ reports.py           # 日报生成（_score_line / max(quality, relevance) 排序 / 中文模式）
   ├─ ingestion/
   │  ├─ arxiv.py
   │  ├─ rss.py            # 11 源 + tag 规范化
   │  ├─ github_trending.py
   │  └─ run.py            # _compute_days_back 自适应回看窗
   ├─ processing/
   │  ├─ llm.py            # provider 抽象（4 种）+ 4 rubric + 中英双语 + summarize_and_score
   │  └─ embeddings.py     # ChromaDB + sentence-transformers
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
| **2026-05-02 08:57:04** | **增量刷新** | ① **Universal Score Axes**：`Paper` 加 `quality_score` / `relevance_score` / `score_rationale` 三列（含幂等迁移），`summarize_and_score` 按 `source_type` 走 4 个 rubric，paper 行镜像到 legacy `originality/impact/impact_rationale`，非论文不走质量门（成功一律 `is_processed=1`），JSON 失败 / 翻译键名 / 必需键缺失一律保留 `0` 等待重试；`/api/papers` 新增 `sort_by=quality_score|relevance_score|total_score`（默认 `total_score`，paper 与非 paper 字段求和）；`/api/stats` 新增 `top_overall`。② **中文 LLM 输出**：`KB_LANGUAGE=zh` 通过 `_lang_instruction` / `_impact_lang_instruction` 注入 prompt；JSON 键锁英文；日报标题 `每日研究简报 — YYYY-MM-DD`，章节中文化；`kb.daily --lang zh` 命令行覆盖。③ **Docker 镜像**：新增 `Dockerfile` + `.dockerignore`；`ARG INSTALL_EXTRAS=ml,llm-cloud` 可瘦身；`HEALTHCHECK` 走 `/api/health`；`VOLUME ["/app/data"]`；compose 自动覆盖 `KB_DATABASE_URL` / `KB_CHROMA_DIR` / `KB_DATA_DIR`。④ **自适应 ingest 回看窗**：`run.py` 新增 `_compute_days_back`（空库 → `KB_INGEST_EMPTY_DB_DAYS`；否则 `now - max(ingested_date)` clamped 到 `[KB_INGEST_GAP_MIN_DAYS, KB_INGEST_GAP_MAX_DAYS]`）。⑤ **冷启动批处理**：`kb.daily` 检测 `is_processed != 0` 全空 / `chroma_id != ""` 全空 → 处理与嵌入不限上限。⑥ **运维脚本**：`kb/scripts/rescore_non_papers.py`（`--dry-run` / `--limit` / `--source-type`）。⑦ **RSS 源**：移除 AnandTech / Meta AI Blog（已下线）；剩 11 个源；`_tag_to_str` 把 feedparser dict 规范化为 `list[str]`；`PaperOut.categories` 加 `field_validator` 兼容旧库 dict 数据，避免 500。⑧ **schemas**：`PaperOut` 加 `quality_score` / `relevance_score` / `score_rationale` 默认值；`citation_count` 仍为预留字段。 |
