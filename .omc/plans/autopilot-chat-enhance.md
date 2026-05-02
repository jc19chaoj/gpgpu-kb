# Autopilot Plan: Chat 功能增强

**Generated**: 2026-05-02
**Scope**: 在 `/chat` 页右侧栏管理对话历史 + 选定单个 source 进行聊天 + arxiv PDF 全文加载

---

## 一、范围

### 后端
1. `Paper` 加列 `full_text`（TEXT，缓存抽取出的完整正文，避免重复下载）。
   - `database.py::_BACKCOMPAT_COLUMNS` 注册幂等迁移。
2. 新模块 `backend/kb/processing/pdf.py`：`fetch_full_text(paper)` —— arxiv/PDF URL → 下载 + `pypdf` 解析；blog/project → 用 abstract+summary。
3. `pyproject.toml` 默认依赖加 `pypdf>=5.0`（纯 Python，体积小）。
4. `schemas.py` 扩展 `ChatRequest`：
   - 新可选字段 `paper_id: int | None = None`（source 模式锚点）
   - 新可选字段 `history: list[ChatMessage] = []`（多轮对话历史）
   - 新模型 `ChatMessage{ role: "user"|"assistant", content: str }`
5. `main.py::chat`：
   - 如果 `paper_id` 给定：跳过向量检索，加载该 paper 的 `full_text`（arxiv 类按需下载），prompt 锚定到这一 source，`sources` 只返回该 paper。
   - 如果 `history` 给定：将历史 user/assistant 消息按顺序注入 prompt（包在 untrusted 块内）。
   - 维持原 RAG 行为作为 `paper_id` 缺省时的默认。
6. `tests/test_api_smoke.py` 新增：
   - `paper_id` 模式：mock `call_llm` 验证 prompt 含完整 source 内容、`sources` 仅含目标 paper。
   - `paper_id` 不存在：404。
   - `history` 注入：mock `call_llm` 验证 prompt 含历史消息。
7. `tests/test_processing_pdf.py` 新增：mock `httpx` 验证 PDF 下载 + 抽取走通；abstract fallback 路径。

### 前端
1. `src/lib/types.ts`：`ChatRequest` 加 `paper_id?` 与 `history?`；新增 `ChatMessage`。
2. `src/lib/api.ts`：`chat()` 转发新字段。
3. `src/hooks/use-conversation-history.ts`（新）：localStorage 读写、CRUD 一组对话；按 ID + 标题 + lastUpdated 列出。
4. `src/components/chat/chat-right-sidebar.tsx`（新）：两段折叠/分栏：
   - **Conversations**：列表 + "New chat" + "Delete" + 选中高亮；空状态提示。
   - **Source mode**：当前选中 source（含清除按钮）+ "Pick source" 触发 SourcePicker。
5. `src/components/chat/source-picker.tsx`（新）：弹窗 / 抽屉，输入即调 `searchPapers(q, { semantic: false, page_size: 10 })`，点击行 → 选定。
6. `src/app/chat/page.tsx` 重构：
   - 引入 `useConversationHistory`，持久化当前 session。
   - 多轮：每次发送时把 `messages` 头部映射为 `history`。
   - source 模式：状态 `selectedPaper`，发送时附 `paper_id`；header 显示锚定 source 名称。
   - 布局：`<flex>` 主区 + 右侧 `ChatRightSidebar`（移动端折叠）。

### 依赖添加
- backend: `pypdf>=5.0`（默认依赖；体积仅 ~600KB）

---

## 二、Files to create

| 路径 | 类型 |
| --- | --- |
| `backend/kb/processing/pdf.py` | new |
| `backend/tests/test_processing_pdf.py` | new |
| `frontend/src/hooks/use-conversation-history.ts` | new |
| `frontend/src/components/chat/chat-right-sidebar.tsx` | new |
| `frontend/src/components/chat/source-picker.tsx` | new |

## 三、Files to modify

| 路径 | 改动 |
| --- | --- |
| `backend/pyproject.toml` | 加 `pypdf` |
| `backend/kb/models.py` | `full_text` 列 |
| `backend/kb/database.py` | 迁移注册 |
| `backend/kb/schemas.py` | `ChatRequest` 扩展 + `ChatMessage` |
| `backend/kb/main.py` | `chat` 支持 paper_id + history |
| `backend/tests/test_api_smoke.py` | 加 chat-source 测试 |
| `frontend/src/lib/types.ts` | `ChatRequest` 字段 |
| `frontend/src/lib/api.ts` | 转发新字段 |
| `frontend/src/app/chat/page.tsx` | 重构集成 |

## 四、QA gates
1. `cd backend && python -m pytest tests/ -x -q`（要求新增测试通过）
2. `cd frontend && npx tsc --noEmit`
3. `cd frontend && npm run lint`

## 五、Risks & mitigations
- **pypdf 下载大体积 PDF**：限制 `max_bytes=20MB`、超时 30s；超量返回 abstract+summary fallback。
- **多轮上下文超长**：仅取最后 N=10 条历史；若 paper 全文 + 历史 + query > 32k chars，先截断 paper 全文到 32000。
- **arxiv PDF URL 变更**：使用 `paper.pdf_url` 字段（来自 ingest 时存的 `pdf_url`）；缺失则回退 abstract+summary。
- **localStorage SSR 报错**：用 `typeof window !== "undefined"` 守卫 + lazy init。
