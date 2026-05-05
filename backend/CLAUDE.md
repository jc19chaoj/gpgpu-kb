# backend/ — Python / FastAPI 服务

[← 返回根](../CLAUDE.md) > **backend**

> 由 `init-architect` 于 `2026-04-25 09:59:45` 自动生成，
> 于 `2026-04-25 15:26:48` 增量刷新（DeepSeek provider / Bearer Token / pytest 套件落地），
> 于 `2026-04-25 16:50` 增量刷新（质量门 `is_processed=2` / `KB_QUALITY_SCORE_THRESHOLD`），
> 于 `2026-05-02 08:57:04` 增量刷新（Universal Score Axes / 中文 LLM 输出 / Docker 镜像 / 自适应 ingest 回看窗 / 冷启动批处理 / 非论文 rescore 脚本 / RSS 源精简),
> 于 `2026-05-02 20:12:04` 增量刷新（多轮 Chat 历史 + 单 source 锚定模式 + `kb.processing.pdf` PDF 全文加载 + uvicorn `--timeout-keep-alive 75` keep-alive 修复），
> 于 `2026-05-02 21:18:53` 增量刷新（SSE 流式聊天 `/api/chat/stream` + 共享 `_build_chat_context` + `stream_llm` 抽象 + chat 系统 prompt 改为中文硬编码），
> 于 `2026-05-02 23:32:00` 增量刷新（vLLM Blog + LMSYS / SGLang Blog (sitemap) + 12 例 sitemap_blog 单元测试 + orchestrator 测试升级到 4 fetcher，pytest 174/174）。
> 于 `2026-05-03 09:44:00` 增量刷新（per-`Paper.source_name` ingest 冷启动；测试 174 → 180 pass）。
> 于 `2026-05-03 21:41:00` 增量刷新（**Fast / Expert 双角色 LLM**：`call_llm` / `stream_llm` 新增 `role="fast"\|"expert"` 参数；`kb/main.py` 的 `/api/chat` + `/api/chat/stream` 显式 `role="expert"`；`summarize_and_score` / `generate_daily_report` 保持默认 fast；测试套件 180 → 203 pass）。
> 于 **`2026-05-03 22:34:43`** 增量刷新（**手动触发 daily pipeline 端点（SSE 进度）**：① 新增 `GET /api/daily/status` + `POST /api/daily/stream`，**都挂 `verify_chat_token`**；② `_DailyRunState` 单例 + `threading.Lock` 防并发，第二个 POST → HTTP 409；③ `_run_daily_in_worker` 在 daemon thread 内 `run_daily_pipeline()`，**无 subprocess**；④ `_QueueLogHandler` + `_QueueStdoutWriter` 把 logger / banner print 都泵进 `Queue(maxsize=2000)`；⑤ `_STAGE_PATTERN=r"\[([1-4])/4\]"` 兼容中英文 stage banner；⑥ 事件序列 `started → stage(≤4) → log(N) → done|error`，15s idle 发 `: keepalive\n\n` SSE 注释帧；⑦ 测试新增 `_drain_daily_sse` 辅助 + 6 例用例；⑧ 既有 chat / SSE 流式聊天 / fast-expert 双角色 / per-source 冷启动 / sitemap blog 等行为全部不动）。
> 于 **`2026-05-05 23:15:12`** 增量刷新（**`pdf.py` → `fulltext.py` + HTML / GitHub README loader + 评分用全文 + chat prompt cap 提到 200K + `[all]` 聚合 extras + ingestion 尾步骤 prefetch + 回填脚本**：① **`kb/processing/pdf.py` 重命名为 `fulltext.py`**：三 loader 派发（PDF 保留 / HTML via trafilatura / GitHub via REST API，自动剥 `.git`），均 httpx 流式 + 超限返回 `""`；`Paper.full_text` cap 120K → **200K**；新增 `_ensure_cached(paper_id)` 单 SessionLocal 工人。② **`run_ingestion()` 尾步骤** `prefetch_pending_full_text()` 4 worker 并发，仅非论文 `full_text==""`，幂等。③ **评分用全文**：`summarize_and_score` 用 `paper.full_text or paper.abstract`，`_SCORING_BODY_CAP=30_000`，prompt 字段 `Abstract:` → `Content:`。④ **chat prompt cap 提到 200K**（`kb/main.py::_SOURCE_TEXT_PROMPT_CAP`）。⑤ `pyproject.toml` 新增 `[fulltext]` extras + 聚合 `[all]`；Docker 默认 `INSTALL_EXTRAS=all`；ST 预下载条件 `grep -qE ',(ml\|all),'` 兼容。⑥ 新脚本 `kb/scripts/backfill_full_text.py` 回填旧非论文 `full_text`；`rescore_non_papers.py` 加 `--include-already-scored`。⑦ 测试 216 → 242（重命名 `test_processing_pdf.py` → `test_processing_fulltext.py` + 17 例）。`/api/chat[/stream]` / `/api/daily/*` / DB schema / 前端代码全部不动）。
> 于 **`2026-05-06 00:04:43`** 自适应增量刷新（**docs-only re-sync, no code drift**）：核对 `kb/processing/fulltext.py`（PDF / HTML / GitHub 三 loader、200K cap、stream + 早期 abort、`_ensure_cached`、`prefetch_pending_full_text`、`_PREFETCH_TYPES = (BLOG, PROJECT, TALK)`、`_PREFETCH_WORKERS=4`，全部存在）/ `kb/scripts/backfill_full_text.py`（`--dry-run` / `--limit` / `--source-type` + `_ensure_cached` 复用 + `_BACKFILL_WORKERS=4` + `is_processed.in_([1,2])` 过滤，存在）/ `Dockerfile`（`ARG INSTALL_EXTRAS=all` 默认 + `grep -qE ',(ml\|all),'` ST 预下载条件 + `--timeout-keep-alive 75`，存在）/ `pyproject.toml`（`[fulltext] = ["trafilatura>=1.12.0"]` + 聚合 `[all]` 自引用，存在）/ `kb/ingestion/run.py` 末尾 `prefetch_pending_full_text()` try/except 入口（存在）/ `kb/main.py` 头部 imports（`asyncio` / `contextlib` / `hmac` / `re` / `threading` / `deque`，存在）。**全部源码与 2026-05-05 23:15:12 changelog 描述一一吻合，无新功能 / 无代码漂移**。仅刷新本文件顶部时间戳与下方 changelog 末尾追加的 docs-only 条目，不动 API 路由、Schema、依赖、模块职责描述。

---

## 一、模块职责

后端承担五件事：

1. **采集（ingestion）**：从 ArXiv / RSS（12 个源）/ sitemap_blog（1 个源）/ GitHub Search 拉取近期内容，按 `Paper.url` 唯一索引去重写入 SQLite；回看窗自动适配 per-`source_name` 上次成功时间。
2. **处理（processing）**：调用 LLM 对每条记录生成 ~3-5 段技术摘要，并按 `source_type` 切换 rubric 打两维 0-10 分（universal axes：`quality_score` / `relevance_score`）；之后用 sentence-transformers 生成嵌入并写入 ChromaDB；**source-anchored chat 触发时按需下载 PDF 抽全文，缓存在 `Paper.full_text`**。
3. **服务（API）**：FastAPI 暴露浏览 / 详情 / 搜索 / **多轮 + source-anchored RAG 聊天（一次性 + SSE 流式两种端点，使用 expert 角色 LLM）** / 日报 / 统计 / 健康检查端点；**本轮新增**：手动触发 daily pipeline + SSE 实时进度的两个端点（`/api/daily/status` + `/api/daily/stream`）。
4. **报告（reports）**：每天聚合当日已处理论文与博客/项目，产出一份 Markdown 简报存入 `daily_reports`（按 `max(quality, relevance)` 排序）。
5. **流水线编排**（本轮新增网页入口）：`run_daily_pipeline()` 既可 `python -m kb.daily` 命令行启动、Docker `--profile cron` 启动，也可通过 `POST /api/daily/stream`（前端 `/reports` 页 Run-Now 按钮）触发——**全部走同一个 in-process 实现**，不开 subprocess。

---

## 二、入口与启动

| 入口 | 作用 |
| --- | --- |
| `kb/main.py` (`app = FastAPI(...)`) | API 应用对象；`lifespan` 中初始化日志、`init_db()`、后台预热 EmbeddingStore；`/api/chat` 与 **`/api/chat/stream`（SSE）** 共享 `_build_chat_context` + `_format_history`；**本轮新增 `/api/daily/status` + `/api/daily/stream`** 走 `_DailyRunState` 单例 + `_run_daily_in_worker` daemon thread + `_QueueLogHandler` / `_QueueStdoutWriter` 双管道 |
| `kb/daily.py` (`run_daily_pipeline`) | 完整每日流水线（ingest → process → embed → report）；冷启动检测 + `--lang zh` 切换；**本轮起也是 `/api/daily/stream` 在 daemon thread 内 lazy import 调用的目标** |
| `kb/ingestion/run.py` (`run_ingestion`) | 仅运行采集阶段；`days_back: int \| None`，None 时**每个 fetcher 自己走 per-`source_name` 冷启动**（见 `_lookback_for_source`）；**末尾自动调 `prefetch_pending_full_text()`**（4 worker，仅非论文 `full_text==""`，幂等；try/except 不阻塞 ingest 总数） |
| `kb/processing/llm.py` (`run_processing`) | 仅运行 LLM 处理阶段，`batch_size=None` 表示无上限 |
| `kb/processing/llm.py` (`call_llm` / **`stream_llm`**) | LLM 调用门面（`role="fast"\|"expert"`）：`call_llm` 返回完整字符串（用于 summary/scoring）；**`stream_llm` 增量 yield 文本片段（用于 `/api/chat/stream`）**；任何 provider 失败均返回空 / 静默结束 generator |
| `kb/processing/embeddings.py` (`index_unindexed_papers`) | 仅运行向量化阶段，`batch_size=None` 表示无上限 |
| `kb/processing/fulltext.py` (`fetch_full_text` / `prefetch_pending_full_text`) | 三路全文 loader：PDF（pypdf）/ HTML（trafilatura）/ GitHub README（REST API）；按 source 派发；缓存到 `Paper.full_text`（200K 字符上限）；缺失 / 失败 fallback 到 `summary + abstract`（不污染缓存）。`prefetch_pending_full_text()` 是采集尾步骤的 4 worker 并发 batcher |
| `kb/reports.py` (`generate_daily_report`) | 仅生成日报（默认昨天，upsert）；用 fast 角色 LLM |
| `kb/scripts/rescore_non_papers.py` | 运维脚本：回填非论文行 universal scores（支持 `--dry-run` / `--limit` / `--source-type` / `--include-already-scored`） |
| `kb/scripts/backfill_full_text.py` | 运维脚本：回填旧非论文行 `full_text`（`--dry-run` / `--limit` / `--source-type`，4 worker 并发；`is_processed ∈ {1,2} AND full_text == ""` 过滤；**不重新评分**——配合 `rescore_non_papers.py --include-already-scored` 二阶段使用） |
| `run_api.sh` | `uvicorn kb.main:app --host 0.0.0.0 --port 8000 --reload --timeout-keep-alive 75` |
| `Dockerfile` | `python:3.12-slim` 多阶段镜像；`ARG INSTALL_EXTRAS=all` 默认（聚合 `ml` + `llm-cloud` + `fulltext`）；ST 预下载条件 `grep -qE ',(ml\|all),'` 兼容新默认；`HEALTHCHECK` 走 `/api/health`；`CMD ["uvicorn", ..., "--timeout-keep-alive", "75"]` |

启动命令：

```bash
cd backend
source .venv/bin/activate
./run_api.sh                                       # 开发：带 --reload + keep-alive 75
python -m kb.daily                                 # 跑一遍完整流水线（命令行）
python -m kb.daily --lang zh                       # 命令行覆盖为中文
python -m kb.ingestion.run                         # 仅采集（含尾步骤 prefetch）
python -m kb.reports                               # 仅生成昨天的报告
python -m kb.scripts.rescore_non_papers --dry-run  # 列出需要回填的非论文行
python -m kb.scripts.backfill_full_text --dry-run  # 列出需要回填 full_text 的旧行
python -m pytest tests/ -x -q                      # 跑测试 (~242 例)
# 网页触发完整流水线：在 /reports 页面点击 "Run pipeline now" 按钮
# (后端调用：POST /api/daily/stream)
```

---

## 三、对外接口（FastAPI 路由）

定义文件：`kb/main.py`

| 方法 + 路径 | 函数 | 说明 |
| --- | --- | --- |
| `GET  /api/papers` | `list_papers` | 分页列出，按 `source_type` 过滤；`source_name`（逗号分隔多值，与 `source_type` AND 组合）多源过滤；`sort_by` 支持 `published_date` / `impact_score` / `originality_score` / `quality_score` / `relevance_score` / `total_score`（默认） / `ingested_date`。**默认仅返回 `is_processed=1`**，加 `?include_low_quality=true` 同时返回 `0`/`2` |
| `GET  /api/sources` | `list_sources` | 浏览页 source_name tag 过滤数据源。返回 `[{name, type, count}, ...]`（仅 `is_processed=1`，按 count desc），group by `(source_name, source_type)`。空 `source_name` 行被跳过 |
| `GET  /api/papers/search` | `search_papers` | `q` 必填；`semantic=true` 走 ChromaDB（仅含 `is_processed=1`），无结果回退 ILIKE（用 `_escape_like` 转义 `%` `_` `\`）。**注意路由顺序：search 必须在 `{paper_id}` 之前** |
| `GET  /api/papers/{paper_id}` | `get_paper` | 单条详情；**不过滤** `is_processed` |
| `POST /api/chat` | `chat` | **非流式 RAG / source-anchored 双模式**（**expert 角色 LLM**）。Prompt + sources 由 `_build_chat_context(req, db)` 生成，**与 `/api/chat/stream` 共用**。**受 `verify_chat_token` 守卫** |
| `POST /api/chat/stream` | `chat_stream` | **SSE 流式版本**（**expert 角色 LLM**）：返回 `text/event-stream`，Header `Cache-Control: no-cache` + `X-Accel-Buffering: no`；事件序列固定 `sources`（恰 1 条）→ `token`（≥1 条；若无输出则发占位 `(LLM produced no output)`）→ `done`（终止符）。**先同步跑 `_build_chat_context`** 让 HTTPException（如 paper_id 404）正常走 HTTP 错误而非空流。**同样受 `verify_chat_token` 守卫** |
| `GET /api/daily/status` | `daily_status` | 返回 `_DailyRunState` 当前快照 `{running, started_at, current_stage}`。前端 `/reports` 页 mount 时调它判断 Run-Now 按钮初始 enabled/disabled——典型场景：他 tab 已经 POST `/api/daily/stream` 在跑，本 tab 刷新后通过 status 探测到 `running=true` 把按钮锁住，避免发出第二个 POST 拿 409。**受 `verify_chat_token` 守卫** |
| `POST /api/daily/stream` | `daily_stream` | 在后端 daemon thread 内 lazy import 调 `kb.daily.run_daily_pipeline()`，并把 logger / stdout / stage banner 编织成 SSE 流推给客户端。事件序列 `started`（恰 1，含 `started_at`）→ `stage`（≤4，含 `index: 1..4` 与 `name: "ingestion"\|"processing"\|"embedding"\|"report"`）→ `log`（N 条，每条含 `line`）→ `done`（payload `{}`）/ `error`（含 `message`），`done` 与 `error` 互斥。15 秒 idle 时发 `: keepalive\n\n` SSE comment 帧防中间反代砍连接。**`_DailyRunState.try_start()` 拿不到锁 → HTTP 409 `DailyConflictError`**，前端 fallback 到 `getDailyStatus()` 探测 in-flight run。Header `Cache-Control: no-cache` + `X-Accel-Buffering: no`。**受 `verify_chat_token` 守卫** |
| `GET  /api/reports` | `list_reports` | 倒序列出最近 N 份日报 |
| `GET  /api/reports/{report_id}` | `get_report` | 单份日报（Markdown）|
| `GET  /api/stats` | `get_stats` | `total_papers` / `processed` / `skipped_low_quality` / `pending` / `by_type` / `top_impact`（5 条，legacy paper-only）/ `top_overall`（5 条，按 `max(quality, relevance)` 跨类型 ranking） |
| `GET  /api/health` | `health` | 存活探针，返回 `{"status":"ok"}`（HEALTHCHECK 指标） |

Swagger UI：`http://localhost:8000/docs`

### Bearer Token 守卫细节（`verify_chat_token`）

- 配置项：`settings.chat_token`（来源 `KB_CHAT_TOKEN`）。
- 未设置 → 端点开放（无摩擦本地开发）。
- 已设置 → 需 `Authorization: Bearer <token>`。
- **比较使用 `hmac.compare_digest`**（防侧信道）。
- **同时挂在 `/api/chat` / `/api/chat/stream` / `/api/daily/status` / `/api/daily/stream`**——任何"昂贵 / 写入 / 触发任务"端点都必须复用同款守卫。

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

`max_length=40` 是 Pydantic 边界（防 DoS），`main.py::_HISTORY_TURN_CAP=12` 是 prompt 实际渲染窗口。

### 共享 prompt 构造（`_build_chat_context`）

`/api/chat` 与 `/api/chat/stream` 都调用 `_build_chat_context(req, db) -> tuple[str, list[PaperOut]]`：

- 计算 `history_block = _format_history(req.history)`（最近 12 条 turn，单条 4 000 字符）。
- 若 `req.paper_id is not None`：查 paper（404 if missing）→ lazy import `kb.processing.fulltext.fetch_full_text` → 拼 source-anchored prompt。**chat 时若 `paper.full_text` 为空会触发现场抓取**（首次访问的旧数据会慢 1-3 秒，但一次性写入缓存）。
- 否则：`get_embedding_store().search(req.query, top_k=req.top_k)` → 拼 RAG prompt。
- **整段都在 `=== UNTRUSTED START === / END ===` 块内**。
- **prompt 系统消息已硬编码为中文**（"你是一名资深的 GPGPU 芯片架构助理 ..."）。

### SSE 帧格式（`_sse_event` helper）

```
event: <name>\ndata: <json>\n\n
```

- `_sse_event(event, data)` 用 `json.dumps(..., ensure_ascii=False)` 编码，避免中文被转成 `\uXXXX`。
- **chat 事件序列**：`sources`（恰 1）→ `token`（≥1，若无输出则 `(LLM produced no output)` 占位）→ `done`（恰 1）。可选 `error`，但当前 `stream_llm` 失败是静默吞掉。
- **daily 事件序列**：`started`（恰 1）→ `stage`（≤4）→ `log`（N 条）→ `done` / `error`（互斥；emit 后 `terminal_emitted=True` 抑制重复）。15 秒 idle 时发 `: keepalive\n\n` SSE comment 帧（前端 `_parseDailyFrame` 跳过 `:` 开头的行）。

---

## 四、Daily Pipeline 网页触发架构

整体设计：把 `python -m kb.daily` 的本地命令行执行能力迁到 HTTP，但**不开 subprocess**——直接在 daemon thread 内 lazy import 调 `run_daily_pipeline()`。这样省去进程间序列化 / IPC / 子进程僵尸回收等所有麻烦，同时通过 `Queue` 把"实时日志流"和"业务执行"完全解耦。

详细架构（状态单例 / Worker thread / Generator / 并发模型 / 测试配方）见上一版本不变。

---

## 五、关键依赖与配置

`pyproject.toml` 五组可选依赖：

| Extra | 提供 | 触发 |
| --- | --- | --- |
| 默认 | FastAPI / Uvicorn / SQLAlchemy 2 / Pydantic 2 / arxiv / feedparser / httpx / python-dotenv / **pypdf>=5.0** | 必装 |
| `[ml]` | chromadb · sentence-transformers（~2GB） | 想要语义检索 / RAG |
| `[llm-cloud]` | anthropic · openai（DeepSeek 复用 openai SDK，无需新依赖） | 走云端 LLM |
| `[fulltext]` | trafilatura（~10MB，连带 lxml / dateparser 等） | 想要 blog / project 全文抽取（不装时 HTML loader 静默 fallback 到 abstract） |
| `[all]` | **聚合**：等价于 `[ml] + [llm-cloud] + [fulltext]` | 端用户便利安装：`pip install -e '.[all]'`；**Docker 默认 `INSTALL_EXTRAS=all`** |
| `[dev]` | pytest · pytest-asyncio · httpx · ruff | 测试 / lint |

设置类：`kb/config.py` 的 `Settings(BaseSettings)`，前缀 `KB_`，亦读取 `backend/.env`。完整字段见 `kb/config.py`（详见根 CLAUDE.md "环境变量"表格）。

---

## 六、数据模型

文件：`kb/models.py`（SQLAlchemy DeclarativeBase）

### `papers`

| 字段 | 类型 | 备注 |
| --- | --- | --- |
| `id` | int PK | autoincrement |
| `title` | str(500) | 必填 |
| `authors` / `organizations` / `categories` | JSON list | 默认空 list |
| `abstract` | Text | 默认空 |
| `url` | str(1000) | **唯一索引**，去重依据 |
| `pdf_url` | str(1000) | source-anchored chat 通过 `_looks_like_pdf_url` 判断是否拉 PDF |
| `source_type` | Enum(`paper`/`blog`/`talk`/`project`) | 默认 `paper`，索引 |
| `source_name` | str(200) | 例如 `arxiv`、`OpenAI`、`github` |
| `published_date` / `ingested_date` | DateTime(tz) | `ingested_date` 索引，UTC |
| `venue` | str(200) | 默认空 |
| `citation_count` | int | 预留字段 |
| `summary` | Text | LLM 输出 |
| `originality_score` / `impact_score` | float | **legacy 兼容字段** |
| `impact_rationale` | Text | legacy |
| `quality_score` / `relevance_score` | float | universal axes（0-10） |
| `score_rationale` | Text | universal 评分理由 |
| `full_text` | Text | **抽取后缓存的完整正文**（PDF / HTML / GitHub README，≤200 000 字符；自 2026-05-05 cap 提升） |
| `is_processed` | int | **状态机**：`0`=待处理 / `1`=精品收录 / `2`=低分跳过；索引 |
| `chroma_id` | str(100) | 与 ChromaDB 行的关联键 |

### `daily_reports`

| 字段 | 类型 | 备注 |
| --- | --- | --- |
| `id` | int PK | – |
| `date` | DateTime(tz) | **唯一**（每天一条） |
| `title` / `content` | str / Text | Markdown |
| `paper_ids` | JSON list[int] | – |
| `generated_date` | DateTime(tz) | – |

### 索引与列兼容性（SQLite-friendly）

`kb/database.py` 在 `init_db()` 中：

1. `_BACKCOMPAT_COLUMNS`：幂等 `ALTER TABLE` 加列：`quality_score` / `relevance_score` / `score_rationale` / `full_text`。
2. `_BACKCOMPAT_INDEXES`：`CREATE INDEX IF NOT EXISTS`。

---

## 七、采集与处理细节

### `kb/ingestion/`

| 文件 | 职责 |
| --- | --- |
| `arxiv.py` | 9 个 cs.* 类目逐一查 |
| `rss.py` | **12 个精选 RSS 源** |
| `sitemap_blog.py` | sitemap-driven blog scraper（当前 1 个源：LMSYS / SGLang Blog） |
| `github_trending.py` | GitHub Search API 按 17 个关键词 |
| `run.py` | 编排 + per-source 冷启动（`_lookback_for_source(source_name)`）+ **末尾 `prefetch_pending_full_text()` 尾步骤** |

### `kb/processing/`

| 文件 | 职责 |
| --- | --- |
| `llm.py` | provider 抽象（4 种）+ 摘要/打分（用 `paper.full_text or paper.abstract`，cap 30K）+ streaming 平行栈 + Fast/Expert 双角色（`_resolve_role`） |
| `embeddings.py` | ChromaDB + sentence-transformers，懒加载单例 |
| `fulltext.py` | 三路全文 loader（PDF / HTML / GitHub README）+ `prefetch_pending_full_text()` ingestion 尾步骤；缓存写回 `Paper.full_text`（200K cap） |

### Provider 矩阵（`call_llm` / `stream_llm`）

| `KB_LLM_PROVIDER` | `call_llm` 实现 | `stream_llm` 实现 | 依赖 |
| --- | --- | --- | --- |
| `hermes`（默认） | `subprocess.run(["hermes", "ask", ...])` | `_stream_hermes`：调 `_call_hermes` → yield 单 chunk | 系统装有 `hermes` CLI |
| `anthropic` | `anthropic.Anthropic(...).messages.create(...)` | `client.messages.stream(...).text_stream` | `[llm-cloud]` + `ANTHROPIC_API_KEY` |
| `openai` | `openai.OpenAI(...).chat.completions.create(...)` | `_stream_openai_compatible(api_key, model)` | `[llm-cloud]` + `OPENAI_API_KEY` |
| `deepseek` | `openai.OpenAI(api_key=DEEPSEEK_API_KEY, base_url=...)...` | `_stream_openai_compatible(api_key, model, base_url=...)` | `[llm-cloud]` + `DEEPSEEK_API_KEY` |

### Fast / Expert 双角色（role overlay）

| 调用点 | role | 触达路径 |
| --- | --- | --- |
| `kb/processing/llm.py::summarize_and_score` | `fast`（默认） | `(settings.llm_provider, None)` |
| `kb/reports.py::generate_daily_report` | `fast`（默认） | 同上 |
| `kb/main.py::chat` | `expert` | `(settings.llm_expert_provider or settings.llm_provider, settings.llm_expert_model)` |
| `kb/main.py::chat_stream` | `expert` | 同上，走 `stream_llm` |

配置规则：`KB_LLM_EXPERT_PROVIDER` 与 `KB_LLM_EXPERT_MODEL` 都是可选；都不设时 expert 透明回退 fast。

### 评分 rubric 矩阵（`_RUBRICS`）

| `source_type` | quality_score 含义 | relevance_score 含义 |
| --- | --- | --- |
| `paper` | Originality | Impact |
| `blog` | Technical Depth | Actionability |
| `talk` | Depth | Actionability |
| `project` | Innovation | Maturity |

### 冷启动批处理（`kb.daily`）

`run_daily_pipeline` 启动时探测：

- **处理冷启动**：`Paper.is_processed != 0` 全为空 → `run_processing(batch_size=None)`。
- **嵌入冷启动**：`Paper.is_processed == 1 && chroma_id != ""` 全为空 → `index_unindexed_papers(batch_size=None)`。

### Per-Source ingest 冷启动（`kb.ingestion.run`）

详见根 CLAUDE.md 第九条与上一轮变更记录。

---

## 八、测试与质量

测试套件已落地，详见 `backend/tests/README.md`。**~242 用例，<35 秒，无网络**。

| 测试文件 | 覆盖 |
| --- | --- |
| `conftest.py` | 隔离临时 SQLite、autouse `_init_db`、session 级 `client` |
| `test_api_smoke.py` | 路由注册、404、参数校验、Bearer Token 守卫、质量门、universal sort、`top_overall`、LIKE 通配符转义、旧 RSS dict-categories 兼容、chat `paper_id` / history / role 校验、**`/api/chat/stream` 5 例 SSE**（happy path 事件序列 / history 注入 / 404 抛在流前 / 空输出占位 / system role 422）、**`/api/daily/{status,stream}` 6 例**（idle / happy 4-stage / 409 并发 / exception → error / Bearer 守卫 / 中文 banner 识别） |
| `test_ingestion_arxiv.py` | 类目去重、cutoff、`save_papers` 幂等 |
| `test_ingestion_rss.py` | bozo / cutoff / dedup / per-feed 冷启动 |
| `test_ingestion_sitemap_blog.py` | sitemap 解析 / og:* meta 抽取 / per-source 冷启动 |
| `test_ingestion_run.py` | `_compute_days_back` / `_lookback_for_source` 4 例 / 4 fetcher 透传 + `prefetch_pending_full_text` mock spy |
| `test_ingestion_github.py` | auth 头、403 短路、polite sleep |
| `test_processing_llm.py` | provider 路由 / 4 source_type rubric / 中文 prompt / `stream_llm` 5 例 / **Fast/Expert 角色 overlay 6 例** |
| `test_processing_embeddings.py` | 单例锁、ML 缺失时优雅降级 |
| `test_processing_fulltext.py` | PDF 路径（缓存 / 下载 / 抽取 / fallback）+ HTML 路径（trafilatura mock / stream / oversize abort）+ GitHub README（happy / 404 / non-github / `.git` 剥离）+ `prefetch_pending_full_text` 选行 + 幂等（17 例） |
| `test_reports.py` | happy / upsert / 空数据 / 中文模式 |
| `fixtures/` | arxiv / rss / github 静态 JSON 样本 |

> Mocking 约定：
> - `_PROVIDERS` / `_STREAM_PROVIDERS` 字典：`monkeypatch.setitem(llm_mod._PROVIDERS, "...", mock)`。
> - chat LLM mock：`monkeypatch.setattr(main_mod, "call_llm", _fake_call_llm)` / `monkeypatch.setattr(main_mod, "stream_llm", _fake_stream_llm)`，签名要接受 `role` kwarg：`def _fake_call_llm(prompt, role: str = "fast"): ...`。
> - daily pipeline mock：`monkeypatch.setattr(daily_mod, "run_daily_pipeline", _fake_pipeline)`；worker thread 内 lazy import 才能命中 patch。
> - daily SSE 解码：`_drain_daily_sse(client)` 跳过 `:` keepalive 注释帧；`_reset_daily_state()` 在每个 daily test 开头清单例。
> - Fulltext mock：`from kb.processing import fulltext as ft_mod` → `monkeypatch.setattr(ft_mod, "_download_pdf", lambda url: b"...")`（PDF 路径）/ `monkeypatch.setattr(ft_mod, "_fetch_html_article", lambda url: "...")`（HTML 路径）/ `monkeypatch.setattr(ft_mod, "_fetch_github_readme", lambda url: "...")`（GitHub 路径）。HTML 路径走 `client.stream("GET", url)`，FakeClient 的 mock 必须实现 `.stream(method, url)` 而不是 `.get(url)`。

---

## 九、CI（`.github/workflows/ci.yml`）

| Job | 内容 |
| --- | --- |
| `backend-tests` | Python 3.12 → `pip install -e '.[dev]' && pip install pytest-cov` → `pytest tests/ -x -q --cov=kb --cov-report=term-missing`；`KB_LLM_PROVIDER=hermes` |
| `frontend-typecheck` | Node 20 → `npm ci` → `tsc --noEmit` + `eslint src/` |
| `frontend-e2e` | Node 20 → `npm ci` → `playwright install --with-deps chromium` → `npm run build && npm run test:e2e` |

---

## 十、Docker / 部署

`backend/Dockerfile`：

- 基础镜像 `python:3.12-slim`；装 `build-essential` / `curl` / `ca-certificates`。
- **`ARG INSTALL_EXTRAS=all`**（聚合：`ml` + `llm-cloud` + `fulltext`） → `pip install ".[${INSTALL_EXTRAS}]"`。
- **ST 预下载条件 `grep -qE ',(ml\|all),'`** —— `INSTALL_EXTRAS=all` 时也会触发 sentence-transformers 模型预下载。
- `VOLUME ["/app/data"]`，所有 SQLite + ChromaDB 文件持久化到 host bind-mount。
- `HEALTHCHECK` curl `/api/health`。
- **`CMD ["uvicorn", "kb.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "75"]`**——`75 s` 必须 ≥ Next 反代连接池任何 idle 窗口。**SSE 流式响应（`/api/chat/stream` 与 `/api/daily/stream`）天然依赖长 keep-alive**。

`docker-compose.yml` 内 backend 自动覆盖三个变量：

```yaml
KB_DATABASE_URL: sqlite:////app/data/kb.sqlite
KB_CHROMA_DIR: /app/data/chroma
KB_DATA_DIR: /app/data
KB_CORS_ORIGINS: '["http://localhost:3000","http://127.0.0.1:3000"]'
```

`build.args.INSTALL_EXTRAS: ${BACKEND_INSTALL_EXTRAS:-all}` 兜底——`.env` 没设也走聚合 `all`。

`daily` 服务复用 backend 镜像，靠 `profiles: ["cron"]` 隔离。

> **网页 vs cron 触发的区别**：cron `docker compose --profile cron run --rm daily` 启一个**新的容器**跑 `python -m kb.daily` 然后退出，跟主 backend 容器完全隔离；网页 Run-Now 按钮（`POST /api/daily/stream`）在**主 backend 容器**的 daemon thread 内跑——相当于"占用主进程的工作时间和内存"。两种方式数据隔离都靠 SQLite 的写锁；并发跑两次 daily 会有写锁竞争，所以 `_DailyRunState` 内 lock + 409 是必要的。

---

## 十一、常见问题 (FAQ)

- **首次 `/api/chat[/stream]` 慢？** 正常，第一次会加载 SentenceTransformer 模型。
- **`hermes` CLI 不存在？** `KB_LLM_PROVIDER=hermes` 时若 PATH 找不到 `hermes`，`call_llm` 返回空串。改为 `anthropic` / `openai` / `deepseek` 即可。
- **DeepSeek / OpenAI streaming 超时？** 调高 `KB_LLM_TIMEOUT_SECONDS`。
- **新加路由位置敏感**：`/api/papers/search` 必须在 `/api/papers/{paper_id}` 之前。
- **`/api/chat[/stream]` / `/api/daily/*` 突然 401？** 检查 `KB_CHAT_TOKEN`。
- **`POST /api/daily/stream` 返回 409？** 有另一个 in-flight run；前端 `getDailyStatus()` 探测 `running=true` 时按钮 disabled。如果 `_DailyRunState._running=true` 但实际 worker thread 已死（罕见，进程异常崩了），重启 backend 进程清状态。
- **`POST /api/daily/stream` 流出来的 stage 没切？** 检查 `kb/daily.py` 的 banner 是不是还按 `[N/4]` 格式 print；`_STAGE_PATTERN = r"\[([1-4])/4\]"` 是和 banner 格式硬约定。
- **`/api/daily/stream` log 帧很多但缺业务关键日志？** `_QueueLogHandler` 监听 root logger，但 ingestion / processing 子模块的 logger 必须 propagate=True（默认是）才会冒泡到 root。如果在某个子模块改了 `logger.propagate = False` 会导致那段日志看不到。
- **网页 Run-Now 跑到一半浏览器关了，pipeline 怎么样？** daemon thread 不受 SSE 客户端断开影响，pipeline 继续在 backend 跑完 → 写库 → 释放 `_DailyRunState` 锁。下次 `/reports` 页面 mount 时 `getDailyStatus()` 会显示 idle，新数据已落库。**真正会中断 pipeline 的只有 backend 进程退出**。
- **聊天页随机 "Sorry, I couldn't process that query"？** 检查 `--timeout-keep-alive 75` 是否到位；中间反代是否对 `text/event-stream` 做了 buffering。
- **source-anchored chat 抽出的全文是乱码？** 多半是 URL 被 `_looks_like_pdf_url` 误判为 PDF；扩白名单时务必 `.endswith(".pdf")` 或显式 substring。
- **采集后非论文行的 `full_text` 仍然空？** ① 检查 `[fulltext]` extras 是否装了（不装则 HTML loader 静默 fallback）；② 检查 `prefetch_pending_full_text()` 日志：`[fulltext] prefetch: M/N rows populated` ——M < N 说明部分行抓取失败（网络 / 404 / oversize），下次 ingest 还会重试。手动回填用 `python -m kb.scripts.backfill_full_text --dry-run` 先列出，再去掉 `--dry-run` 实跑。

---

## 十二、相关文件清单（精选）

```
backend/
├─ pyproject.toml          # 依赖与 extras（含默认 pypdf>=5 + 可选 [fulltext] + 聚合 [all]）
├─ Dockerfile              # python:3.12-slim 多阶段；ARG INSTALL_EXTRAS=all 默认；CMD 含 --timeout-keep-alive 75
├─ .dockerignore           # 排除 data/ / tests/ / __pycache__ / .env
├─ run_api.sh              # uvicorn ... --reload --timeout-keep-alive 75
├─ tests/
│  ├─ README.md            # 测试套件说明 (~242 用例)
│  ├─ conftest.py
│  ├─ test_api_smoke.py    # 含 Bearer Token / 质量门 / universal sort / chat paper_id+history / SSE 5 例 / daily-stream 6 例
│  ├─ test_ingestion_*.py  # 含 test_ingestion_run.py 中的 prefetch_pending_full_text mock spy
│  ├─ test_processing_llm.py
│  ├─ test_processing_embeddings.py
│  ├─ test_processing_fulltext.py  # PDF / HTML / GitHub README 三路（17 例）
│  ├─ test_reports.py
│  └─ fixtures/
└─ kb/
   ├─ main.py              # FastAPI 应用 / 路由 / verify_chat_token / _build_chat_context / chat & chat_stream / daily_status & daily_stream / _DailyRunState / _QueueLogHandler / _QueueStdoutWriter / _STAGE_PATTERN / _SOURCE_TEXT_PROMPT_CAP=200K
   ├─ config.py            # Pydantic Settings（含 llm_expert_provider/model）
   ├─ database.py          # engine / SessionLocal / init_db / 兼容列+索引
   ├─ models.py            # Paper（含 universal axes + full_text）/ DailyReport
   ├─ schemas.py           # PaperOut / ChatMessage / ChatRequest / ChatResponse / SourceItem / SourcesOut
   ├─ daily.py             # 全流水线编排（冷启动检测 + --lang）；既是 CLI 入口，也是 /api/daily/stream 在 worker thread 内 lazy import 调用的目标
   ├─ reports.py           # 日报生成（fast 角色）
   ├─ ingestion/
   │  ├─ arxiv.py
   │  ├─ rss.py            # 12 源
   │  ├─ sitemap_blog.py
   │  ├─ github_trending.py
   │  └─ run.py            # _lookback_for_source per-source 冷启动 + 末尾 prefetch_pending_full_text() 尾步骤
   ├─ processing/
   │  ├─ llm.py            # provider 抽象（4 种）+ Fast/Expert 双角色 + stream_llm + summarize 用 full_text/30K cap
   │  ├─ embeddings.py
   │  └─ fulltext.py       # PDF / HTML / GitHub README 三路 loader + _ensure_cached + prefetch_pending_full_text + 200K cap
   └─ scripts/
      ├─ rescore_non_papers.py     # --include-already-scored
      └─ backfill_full_text.py     # 旧非论文行 full_text 回填（4 worker 并发；is_processed ∈ {1,2}）
```

---

## 十三、变更记录 (Changelog)

| 时间 | 操作 | 说明 |
| --- | --- | --- |
| 2026-04-25 09:59:45 | 初始化 | 自动生成 backend 模块 `CLAUDE.md` |
| 2026-04-25 15:26:48 | 增量刷新 | 新增 `deepseek` provider；补充 `verify_chat_token` Bearer 守卫细节；新增 `KB_CHAT_TOKEN` / `KB_DEEPSEEK_*`；新增"CI"章节 |
| 2026-04-25 16:50 | 质量门 | 新增 `KB_QUALITY_SCORE_THRESHOLD`；is_processed 落桶 0/1/2 |
| 2026-05-02 08:57:04 | 增量刷新 | Universal Score Axes / 中文 LLM 输出 / Docker 镜像 / 自适应 ingest 回看窗 / 冷启动批处理 / 运维脚本 / RSS 源精简 |
| 2026-05-02 20:12:04 | 增量刷新 | 多轮 + source-anchored chat / `kb/processing/pdf.py` / `Paper.full_text` / pypdf 默认依赖 / `--timeout-keep-alive 75` |
| 2026-05-02 21:18:53 | 增量刷新 | `/api/chat/stream` SSE 端点 / `_build_chat_context` 共享 / `stream_llm` 抽象 / `_STREAM_PROVIDERS` 字典 / `_stream_openai_compatible` 公共体 / chat 系统 prompt 改为中文硬编码 |
| 2026-05-02 23:32:00 | 增量刷新 | vLLM Blog + LMSYS / SGLang Blog (sitemap) / `kb/ingestion/sitemap_blog.py` / 测试 ~115 → 174 pass |
| 2026-05-03 09:44:00 | 增量刷新 | per-`source_name` ingest 冷启动 / `_lookback_for_source` / 测试 174 → 180 pass |
| 2026-05-03 21:41:00 | 增量刷新 | Fast / Expert 双角色 LLM；`call_llm` / `stream_llm` 新增 `role` 参数；`KB_LLM_EXPERT_PROVIDER` / `KB_LLM_EXPERT_MODEL`；`/api/chat[/stream]` 显式 expert；测试 180 → 203 pass |
| **2026-05-03 23:00:00** | **增量刷新** | **Browse 页 source_name 过滤后端支持**（`/api/sources` + `list_papers?source_name=`，详见上一版本）；测试 209 → 216 pass |
| **2026-05-03 22:34:43** | **增量刷新** | **手动触发 daily pipeline + SSE 进度**（`/api/daily/{status,stream}` 详见上一版本）；测试 +6 例 |
| **2026-05-05 23:15:12** | **增量刷新** | **Universal full-text loader（HTML / GitHub README / PDF）+ 评分用全文 + chat prompt cap 提到 200K + `[all]` 聚合 extras + ingestion 尾步骤 prefetch + 回填脚本**（详见上一版本）；测试 216 → 242 (+26) |
| **2026-05-06 00:04:43** | **自适应增量刷新（docs-only re-sync）** | **代码与文档已对齐**。本次扫描核对：`kb/processing/fulltext.py`（PDF / HTML / GitHub 三 loader、200K cap、stream + 早期 abort、`_ensure_cached`、`prefetch_pending_full_text`、`_PREFETCH_TYPES = (BLOG, PROJECT, TALK)`、`_PREFETCH_WORKERS=4`）/ `kb/scripts/backfill_full_text.py`（`--dry-run` / `--limit` / `--source-type` + `_ensure_cached` 复用 + `_BACKFILL_WORKERS=4` + `is_processed.in_([1,2])` 过滤）/ `Dockerfile`（`ARG INSTALL_EXTRAS=all` 默认 + `grep -qE ',(ml\|all),'` ST 预下载条件 + `--timeout-keep-alive 75`）/ `pyproject.toml`（`[fulltext] = ["trafilatura>=1.12.0"]` + 聚合 `[all]` 自引用）/ `kb/ingestion/run.py` 末尾 `prefetch_pending_full_text()` try/except 入口 / `kb/main.py` 头部 imports（`asyncio` / `contextlib` / `hmac` / `re` / `threading` / `deque`）。**全部源码与 2026-05-05 23:15:12 changelog 描述一一吻合，无新功能 / 无代码漂移**。仅刷新本文件顶部时间戳与本条 changelog 记录；表格 / API 路由 / Schema / 依赖 / 模块职责 / 测试章节均维持原状（除入口表格 `kb/scripts/backfill_full_text.py` 行从"未来工作"改为已存在描述、`Dockerfile` 行追加聚合 `INSTALL_EXTRAS=all` 描述、Docker 章节追加 `${BACKEND_INSTALL_EXTRAS:-all}` 兜底说明、入口表 `kb/ingestion/run.py` 行追加"末尾自动调 `prefetch_pending_full_text()`"描述这几处文字微调，使行文与已对齐的代码现状完全一致）。 |
