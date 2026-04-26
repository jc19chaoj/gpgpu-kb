# Open Questions

## chinese-mode - 2026-04-26

- [ ] 中文日报引用英文摘要的混合问题 — 如果用户在 `language=en` 时处理了论文，之后切换到 `zh` 生成日报，日报 LLM prompt 中喂入的 `p.summary` 仍为英文，最终日报可能中英混杂。是否需要提供 reprocess 命令让用户主动回填中文摘要？（建议作为 follow-up）
- [ ] `settings.language` 直接赋值是否会影响 API 进程 — 当前设计中 `--lang` 只在 `daily.py` 的 `__main__` 中赋值，API 进程不走该路径。但如果未来 API 也需要语言切换，需要更正式的参数传递机制（如函数参数或 request-scoped config）
- [ ] 是否需要在 `/api/chat` 也支持语言参数 — 用户需求明确说"包括运行 kb.daily 时"，暗示 chat 不在本期范围，但值得确认
- [ ] DeepSeek / hermes 对"Write in Chinese"指令的实际响应质量 — 需要在实际运行时验证，尤其是 hermes 作为本地 CLI 工具，其中文能力未知
