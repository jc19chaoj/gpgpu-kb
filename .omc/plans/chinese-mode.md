# 计划：中文模式支持（kb.daily 流水线）

> 生成时间：2026-04-26
> 模式：RALPLAN-DR 短模式（非高风险任务）

---

## 一、需求复述

用户希望为 GPGPU Knowledge Base 添加"中文模式"，使得运行 `python -m kb.daily` 时，LLM 生成的摘要、打分理由、日报 Markdown 均以中文输出。该功能应为 opt-in，通过环境变量和/或 CLI 参数激活，默认行为（英文）保持不变。

---

## 二、范围与非范围

### 在范围内（本期）

- `kb/config.py`：新增 `KB_LANGUAGE` 环境变量
- `kb/daily.py`：新增 `--lang` CLI 参数，优先级高于环境变量；流水线 banner 文案双语化
- `kb/processing/llm.py`：摘要 prompt 和打分 prompt 根据语言追加"请用中文回答"指令
- `kb/reports.py`：日报生成 prompt 根据语言追加中文指令；报告标题模板双语化
- `backend/tests/`：新增覆盖语言切换逻辑的单元测试

### 不在范围内（follow-up）

- **前端 UI i18n**：前端页面文案的中英切换不在本期
- **`/api/chat` 回答语言**：聊天端点的回答语言控制不在本期（可复用同一 `KB_LANGUAGE` 设定，作为后续迭代）
- **多语言（除 en/zh 外）**：本期仅支持英文和中文两种
- **已处理论文的回填**：切换语言后，已有 `is_processed=1|2` 的论文不会被重新处理（见决策点 5）

---

## 三、RALPLAN-DR 摘要

### Principles（原则）

1. **Opt-in，向后兼容**：默认 `en`，不改变任何现有行为，所有改动均为加法
2. **不破坏 Prompt 安全**：`=== UNTRUSTED START/END ===` 包裹和 `_sanitize()` 必须保留，语言指令只追加在 system-level prompt 中，不触碰不可信数据区域
3. **最小改动覆盖核心流水线**：只改 config / daily / llm / reports 四个文件 + 测试
4. **可扩展**：`language` 字段设计为字符串枚举，未来可低成本扩展到 `ja`/`ko` 等
5. **不改 DB schema**：避免迁移成本，保持简单

### Decision Drivers（决策驱动）

1. **用户体感**：中文研究人员阅读中文日报效率更高，这是核心目标
2. **实现成本**：改动文件数控制在 4+测试，无数据库迁移，1 天内可完成
3. **可扩展性**：语言参数化而非硬编码中文，为未来多语言留口子

### Viable Options（可行方案）

#### 选项 A：仅环境变量 `KB_LANGUAGE=zh|en`

| 维度 | 评价 |
|------|------|
| 优点 | 实现最简，只改 `config.py` 加一个字段；与现有 `KB_*` 配置风格一致 |
| 缺点 | 临时切换不方便——需要 `KB_LANGUAGE=zh python -m kb.daily`，每次都要写；无法在同一环境下快速切换 |
| 适用场景 | 语言长期固定（如部署在中文环境中）|

#### 选项 B：仅 CLI 参数 `--lang {en,zh}`

| 维度 | 评价 |
|------|------|
| 优点 | 临时切换极方便 `python -m kb.daily --lang zh` |
| 缺点 | 不能通过 `.env` 持久化默认值；与项目现有"环境变量驱动配置"的风格不一致；cron 场景需要在命令行写死 |
| 适用场景 | 偶尔使用中文模式 |

#### 选项 C（推荐）：CLI + 环境变量组合，CLI 覆盖 env

| 维度 | 评价 |
|------|------|
| 优点 | 两全其美——`.env` 设默认值，CLI 临时覆盖；cron 可写 `--lang zh` 或依赖 env |
| 缺点 | 实现稍复杂（多一个 argparse），但复杂度极低（约 10 行） |
| 适用场景 | 所有场景 |

### 推荐方案

**选项 C（CLI + env 组合）**。理由：成本增量极小（仅多一个 argparse），但同时满足"持久化默认值"和"临时切换"两种使用模式。排除选项 A 因为临时切换不便；排除选项 B 因为不能持久化默认值且与项目配置风格不符。

---

## 四、关键决策说明

### 决策 1：Prompt 改造策略（分级处理）

**选择**：对 `summary_prompt` 和 `impact_prompt` 采用**不同的语言指令策略**，而非统一追加同一条指令。

#### summary_prompt（摘要生成）— 完整中文输出指令

```
# 追加行（当 lang=zh 时）
IMPORTANT: Write your entire response in Chinese (简体中文).
```

摘要输出是纯自然语言文本，无结构化解析依赖，可安全使用完整中文输出指令。

#### impact_prompt（JSON 打分）— 精确局部指令

```
# 追加行（当 lang=zh 时）
The "impact_rationale" value should be written in Chinese (简体中文). All JSON keys and the numeric values must remain exactly as specified above (English keys, numeric scores).
```

**绝对不能**对 `impact_prompt` 追加 `"Write your entire response in Chinese"` 这样的完整指令。原因：LLM（尤其 hermes 和部分开源模型）有非零概率将 JSON key 翻译成中文（如 `"原创性": 8.0`），`json.loads` 不会报错，但 `result_json.get("originality_score")` 返回 `None`，`_clamp_score(None)` 静默返回 `5.0`，论文被标记 `is_processed=2`（永久错误分类，不可重试）。

精确局部指令只要求 `impact_rationale` value 使用中文，这是用户直接阅读的文本，中文化有实际价值；同时严格约束 JSON key 和数值不变，将结构风险控制在最低。

**通用理由**：
- 英文 prompt 经过验证，结构稳定，改动风险最小
- 主流 LLM（Claude/GPT/DeepSeek）均能正确响应英文 prompt + 中文输出指令
- 保留英文 prompt 使得 prompt 注入防护的 `=== UNTRUSTED START/END ===` 语义不变
- 如果写全中文 prompt，需要维护两套完整 prompt 模板，维护成本翻倍

### 决策 2：数据库 schema 不变

**选择**：不新增 `summary_lang` 字段，不改 schema。

**理由**：验证了 `is_processed` 状态机——`run_processing` 只查询 `is_processed == 0` 的论文（`llm.py` 第 277 行），已处理（1 或 2）的论文不会被重新处理。因此：
- 切换到 `zh` 后，仅新采集的论文会得到中文摘要
- 已有英文摘要的论文保持不变
- 如果用户确实需要重新处理，可手动 `UPDATE papers SET is_processed=0 WHERE ...`
- 这是最小且正确的方案，避免了 schema 迁移

### 决策 3：日报模板双语化

**选择**：最小改动方案——日报标题 (`_upsert_report` 中的 `title`) 和日报 LLM prompt 中的章节名根据语言切换。

具体改动：
- `title`：`"Daily Research Report — {date}"` vs `"每日研究简报 — {date}"`
- prompt 中的章节名（Executive Summary / Top Papers / Key Themes / Hidden Gems / Recommended Reading）通过语言参数切换为中文等价物
- 空数据占位文案双语化

### 决策 4：`language` 参数传递方式

**选择**：通过 `settings.language` 全局读取，不在函数签名间层层传递。

**理由**：
- `summarize_and_score`、`generate_daily_report` 都已经通过 `settings` 读取配置（如 `settings.quality_score_threshold`）
- CLI `--lang` 覆盖通过在 `daily.py` 的 `__main__` 中直接修改 `settings.language` 实现
- 避免改动 `summarize_and_score(paper_id)` 和 `generate_daily_report(date)` 的函数签名（这会影响所有调用方）

---

## 五、详细实施步骤

### 步骤 1：`config.py` — 新增 `language` 配置字段

**文件**：`backend/kb/config.py`

**改动**：在 `Settings` 类中（约第 39 行 `llm_provider` 附近）新增：

```python
# Language for LLM outputs (summaries, scores, reports)
# Options: "en" (default), "zh" (Chinese)
language: str = "en"
```

**验收标准**：
- `settings.language` 默认值为 `"en"`
- 设置 `KB_LANGUAGE=zh` 环境变量后，`settings.language == "zh"`
- 现有测试套件全部通过（无行为变化）

---

### 步骤 2：`daily.py` — 添加 argparse + 双语 banner

**文件**：`backend/kb/daily.py`

**改动**：

1. 在 `__main__` 块（第 47-52 行）中引入 `argparse`：
   ```python
   if __name__ == "__main__":
       import argparse
       parser = argparse.ArgumentParser(description="GPGPU KB daily pipeline")
       parser.add_argument("--lang", choices=["en", "zh"], default=None,
                           help="Output language (overrides KB_LANGUAGE env)")
       args = parser.parse_args()
       if args.lang:
           from kb.config import settings
           settings.language = args.lang
       # ... existing logging + run_daily_pipeline()
   ```

2. `run_daily_pipeline()` 中的 print banner 根据 `settings.language` 切换：
   - `"GPGPU Knowledge Base - Daily Pipeline"` vs `"GPGPU 知识库 - 每日流水线"`
   - 步骤标签：`"[1/4] INGESTION"` vs `"[1/4] 数据采集"`
   - 完成摘要：`"Pipeline complete!"` vs `"流水线完成！"`

3. 当 `settings.language != "en"` 时，在流水线启动前增加一行日志提示，帮助用户确认配置生效：
   ```python
   if settings.language != "en":
       logger.info("Language set to %s", settings.language)
   ```

**验收标准**：
- `python -m kb.daily --lang zh` 正常运行，banner 显示中文
- `python -m kb.daily` 行为不变（英文）
- `KB_LANGUAGE=zh python -m kb.daily` 显示中文
- `KB_LANGUAGE=zh python -m kb.daily --lang en` CLI 覆盖 env，显示英文
- 当 `language != "en"` 时，日志中出现 `"Language set to zh"` 提示

---

### 步骤 3：`llm.py` — Prompt 语言指令注入 + 防御性 JSON key 校验

**文件**：`backend/kb/processing/llm.py`

**改动**：

1. 新增辅助函数 `_lang_instruction()`:
   ```python
   def _lang_instruction() -> str:
       """Return a prompt suffix that instructs the LLM to respond in the configured language."""
       if settings.language == "zh":
           return "\n\nIMPORTANT: Write your entire response in Chinese (简体中文)."
       return ""
   ```

2. 新增辅助函数 `_impact_lang_instruction()`（与 `_lang_instruction()` 分离，专用于 JSON 打分 prompt）:
   ```python
   def _impact_lang_instruction() -> str:
       """Return a precise language instruction for impact scoring prompt.
       
       Unlike _lang_instruction(), this does NOT instruct "entire response in Chinese"
       to avoid LLMs translating JSON keys (e.g. "原创性" instead of "originality_score"),
       which would cause _clamp_score(None) to silently default to 5.0 and mark the paper
       as is_processed=2 (permanent misclassification, no retry).
       """
       if settings.language == "zh":
           return '\n\nThe "impact_rationale" value should be written in Chinese (简体中文). All JSON keys and the numeric values must remain exactly as specified above (English keys, numeric scores).'
       return ""
   ```

3. 在 `summarize_and_score` 的 `summary_prompt` 末尾（第 190 行 `Only output the summary, nothing else."""` 之前）追加 `{_lang_instruction()}`（完整中文指令，因为摘要是纯文本，无结构化解析风险）

4. 在 `impact_prompt` 末尾（第 230 行 JSON 格式指令之后）追加 `{_impact_lang_instruction()}`（精确局部指令，**不含** "entire response in Chinese"）

5. **（新增）防御性 JSON key 存在性检查**：在 `summarize_and_score` 中，`result_json` 非 `None` 之后、调用 `_clamp_score` 之前，检查 `originality_score` 与 `impact_score` 两个 key 是否都存在，缺失则 `return False`（走重试路径）。约 5 行代码：
   ```python
   required_keys = ("originality_score", "impact_score")
   if not all(k in result_json for k in required_keys):
       logger.warning(
           "Impact JSON missing required keys %s, got keys: %s (paper %s)",
           required_keys, list(result_json.keys()), paper_id,
       )
       return False
   ```
   此检查即使不加中文模式也有独立价值——LLM 偶尔会返回 `originality` 等错位 key，当前代码会静默写入默认分 5.0 并标记 `is_processed=2`（永久错误分类）。

**安全约束**：
- `_lang_instruction()` 和 `_impact_lang_instruction()` 的返回值均为硬编码字符串，不包含任何用户输入
- `=== UNTRUSTED START/END ===` 包裹不变
- `_sanitize()` 调用不变

**验收标准**：
- `settings.language == "en"` 时，prompt 与当前完全一致（两个辅助函数均返回空串）
- `settings.language == "zh"` 时，`summary_prompt` 末尾包含完整中文输出指令
- `settings.language == "zh"` 时，`impact_prompt` 末尾仅包含针对 `impact_rationale` 的精确指令，**不含** "entire response in Chinese"
- JSON 打分结构（key 名）不受语言影响，仅 `impact_rationale` 值可能为中文
- **当 LLM 返回中文 key（如 `{"原创性": 8.0, ...}`）时，`summarize_and_score` 返回 `False`（走重试），不会静默误分类**
- Prompt 注入防护标记仍然存在

---

### 步骤 4：`reports.py` — 日报 prompt 与标题双语化

**文件**：`backend/kb/reports.py`

**改动**：

1. 在文件顶部 import `settings`：
   ```python
   from kb.config import settings
   ```

2. `generate_daily_report` 中的 LLM prompt（第 60-75 行），根据语言切换章节名和指令语言：
   - 当 `settings.language == "zh"` 时，prompt 末尾追加：
     ```
     IMPORTANT: Write the entire report in Chinese (简体中文). Use the following section names:
     1. **概要** 2. **重点论文** 3. **主题趋势** 4. **潜力之作** 5. **推荐阅读**
     ```
   - 当 `settings.language == "en"` 时，prompt 保持不变

3. `_upsert_report` 中的 `title` 模板（第 95 行）：
   ```python
   title = (
       f"每日研究简报 — {date.isoformat()}"
       if settings.language == "zh"
       else f"Daily Research Report — {date.isoformat()}"
   )
   ```

4. 空数据占位文案（第 42-44 行）双语化：
   ```python
   content = (
       f"{date.isoformat()} 无新论文入库，请检查采集流水线。"
       if settings.language == "zh"
       else f"No new papers were ingested on {date.isoformat()}. Check the ingestion pipeline."
   )
   ```

**验收标准**：
- `settings.language == "en"` 时，日报内容与当前完全一致
- `settings.language == "zh"` 时，日报标题为中文，LLM prompt 要求中文输出
- 空数据场景下占位文案为中文

---

### 步骤 5：测试

**文件**：`backend/tests/test_processing_llm.py` 和 `backend/tests/test_reports.py`

**新增测试用例**：

#### `test_processing_llm.py` 新增：

1. **`test_lang_instruction_returns_empty_for_en`**
   - 设置 `settings.language = "en"`
   - 断言 `_lang_instruction() == ""`

2. **`test_lang_instruction_returns_chinese_suffix_for_zh`**
   - 设置 `settings.language = "zh"`
   - 断言返回值包含 `"Chinese"` 和 `"简体中文"`

3. **`test_summarize_prompt_includes_lang_instruction_zh`**
   - 设置 `settings.language = "zh"`
   - mock `call_llm`，捕获传入的 prompt 字符串
   - 断言摘要 prompt 包含中文输出指令
   - 断言 `=== UNTRUSTED START ===` 仍存在（安全防护不变）

4. **`test_summarize_prompt_unchanged_for_en`**
   - 设置 `settings.language = "en"`（或不设置）
   - mock `call_llm`，捕获 prompt
   - 断言 `summary_prompt` 与 `impact_prompt` 都不包含 `"Chinese"` 或 `"简体中文"`（覆盖两个 prompt 在 en 下完全不变）

5. **`test_summarize_json_keys_translated_returns_false`**（新增 — 防御性校验测试）
   - mock `call_llm` 返回 `'{"原创性": 8.0, "影响力": 7.0, "impact_rationale": "很好的论文"}'`
   - 调用 `summarize_and_score`
   - 断言返回 `False`（走重试路径），而不是静默写入默认分 5.0
   - 验证 `is_processed` 未被设为 `2`（不会永久错误分类）

6. **`test_impact_prompt_no_entire_response_chinese`**（新增 — 确保 impact_prompt 不含完整中文指令）
   - 设置 `settings.language = "zh"`
   - mock `call_llm`，捕获传入 `impact_prompt` 的内容
   - 断言 prompt **不包含** `"Write your entire response in Chinese"`
   - 断言 prompt **包含** `"impact_rationale"` 和 `"Chinese"` 的精确局部指令

#### `test_reports.py` 新增：

7. **`test_report_title_chinese_when_lang_zh`**
   - 设置 `settings.language = "zh"`
   - 断言生成的报告标题包含 `"每日研究简报"`

8. **`test_report_prompt_includes_chinese_instruction_zh`**
   - 设置 `settings.language = "zh"`
   - mock `call_llm`，捕获 prompt
   - 断言 prompt 包含中文章节名（`"概要"` / `"重点论文"` 等）

9. **`test_report_empty_placeholder_chinese_when_lang_zh`**
   - 设置 `settings.language = "zh"`
   - 在无论文的情况下生成报告
   - 断言占位文案包含 `"无新论文入库"`

#### `test_daily_cli.py`（新文件，**必做**）：

10. **`test_daily_argparse_lang_flag`**（**required**，含 CLI 覆盖 env 子案例）
   - 子案例 (a)：直接调用 argparse 解析 `--lang zh`，断言 `args.lang == "zh"`
   - 子案例 (b)：通过 `monkeypatch.setenv("KB_LANGUAGE", "zh")` + 模拟 `--lang en` CLI 参数，断言最终 `settings.language == "en"`（CLI 覆盖 env 优先级）
   - 子案例 (c)：仅设置 env 无 CLI，断言 `settings.language == "zh"`（env 生效）

**验收标准**：
- 所有新测试通过
- 现有测试套件全部通过（回归验证）
- 新测试遵循现有 mock 约定（`monkeypatch.setattr(config.settings, ...)` + `patch.object(llm_mod, "call_llm", ...)`）

---

## 六、文件改动清单

| 文件 | 改动类型 | 预估行数 |
|------|----------|----------|
| `backend/kb/config.py` | 新增 1 个字段 | +3 |
| `backend/kb/daily.py` | 新增 argparse + 双语 banner + language logger.info | +28 |
| `backend/kb/processing/llm.py` | 新增 `_lang_instruction()` + `_impact_lang_instruction()` + prompt 追加 + 防御性 JSON key 校验 | +30 |
| `backend/kb/reports.py` | prompt 追加 + 标题/占位文案双语 | +20 |
| `backend/tests/test_processing_llm.py` | 新增 6 个测试（含防御性校验 + impact prompt 验证） | +80 |
| `backend/tests/test_reports.py` | 新增 3 个测试 | +40 |
| **合计** | **6 个文件** | **~201 行** |

---

## 七、风险与回滚策略

### 风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 中文输出指令导致 LLM JSON 打分 key 被翻译（如 `"原创性"` 代替 `"originality_score"`），造成永久错误分类 | 中（provider 依赖） | **高**（`is_processed=2` 不可重试，永久误分类） | ① `impact_prompt` 仅追加精确局部指令（不含 "entire response in Chinese"）；② 新增防御性 JSON key 存在性检查，缺失则 `return False` 走重试；③ 新增 `test_summarize_json_keys_translated_returns_false` 测试覆盖 |
| `settings.language` 直接赋值在多线程场景下不安全 | 极低 | 低 | `daily.py` 是单进程 CLI，不存在并发；API 进程不受影响（不走 argparse） |
| DeepSeek/hermes 对中文输出指令响应质量不一致 | 低 | 低 | 指令用英文写（`Write in Chinese`），主流模型均能理解 |

### 回滚策略

- 所有改动均为加法（新字段有默认值 `"en"`）
- 回滚方式：删除 `KB_LANGUAGE` 环境变量 / 不传 `--lang`，即恢复英文行为
- 无数据库迁移，无需回滚 schema

---

## 八、范围外 / Follow-up

1. **前端 UI i18n**：前端页面文案（搜索框、按钮、导航）的中英切换
2. **`/api/chat` 中文应答**：`main.py` 中 chat prompt 追加语言指令（可复用 `_lang_instruction()`）
3. **已有论文回填**：提供一个 `python -m kb.reprocess --lang zh` 命令，重置 `is_processed=0` 后重跑
4. **多语言扩展**：将 `"zh"` 扩展为 `"ja"` / `"ko"` 等
5. **日报 API 语言过滤**：`/api/reports` 按语言筛选（需要 `daily_reports` 表加 `lang` 字段）
6. **重试次数上限/退避**：当前防御性 key 检查 `return False` 会让 paper 保持 `is_processed=0` 无限重试。极端情况下同一条 paper 持续触发 LLM 翻译 key 时会反复消耗 token。考虑增加 `Paper.retry_count` 字段或基于 `updated_at` 的 backoff（实际概率极低，本期不做）
7. **`KB_LANGUAGE` 值校验**：当前未约束为 `Literal["en", "zh"]`，非法值（如 `KB_LANGUAGE=fr`）会静默退化为英文。可在 `config.py` 增加 `field_validator` 打 warning（不抛异常以保持可扩展性）

---

## 九、ADR（架构决策记录）

**Decision**：采用 CLI 参数 + 环境变量组合方式，通过 prompt 后缀注入语言指令，不改数据库 schema。

**Drivers**：
1. 用户需要中文日报以提升阅读效率
2. 实现成本必须可控（1 天内完成）
3. 不能破坏现有测试套件和 prompt 安全机制

**Alternatives considered**：
- 仅 env（选项 A）：临时切换不便，排除
- 仅 CLI（选项 B）：不能持久化默认值，与项目配置风格不符，排除
- 全中文 prompt 模板：维护成本翻倍，排除
- 新增 `summary_lang` 数据库字段：过度设计，当前场景不需要同时存多语言摘要，排除

**Why chosen**：选项 C（CLI+env）成本增量极小（~10 行 argparse），同时覆盖持久化和临时切换两种场景。Prompt 后缀方式复用现有英文 prompt，改动最小且效果可靠。

**Consequences**：
- 已处理论文不会自动获得中文摘要（需手动重置 `is_processed`）
- 日报中可能出现"中文日报引用英文摘要"的混合情况（因为摘要在 processing 阶段生成，日报在 report 阶段生成，两者语言设定可能不同）
- 为了 JSON 打分稳定性，`impact_rationale` 的中文化采取保守策略（精确局部指令而非完整中文输出指令），避免 LLM 翻译 JSON key 导致永久错误分类
- `KB_LANGUAGE` 字段类型为 `str` 而非 `Literal["en","zh"]`（保持未来多语言扩展性）；非 `en`/`zh` 的值（如 `KB_LANGUAGE=fr`）会被 `_lang_instruction()` 走 else 分支静默退化为英文输出。CLI `--lang` 已通过 `argparse` 的 `choices` 强校验
- 防御性 key 检查 `return False` 走重试路径，无重试次数上限——极端情况下同一坏 paper 每天消耗一次 LLM 调用（概率极低，已记入 follow-up #6）

**Follow-ups**：
- 提供 `reprocess` 命令用于回填
- 前端 i18n 作为独立任务
