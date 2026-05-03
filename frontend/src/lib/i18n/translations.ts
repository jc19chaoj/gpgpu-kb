// Flat translation dictionary. Add a key here once, reference everywhere via
// the useT() hook. Keep keys English-ish for searchability; values are the
// actual rendered strings per locale.

export type Locale = "en" | "zh";

export const LOCALES: readonly Locale[] = ["en", "zh"] as const;

export const LOCALE_LABELS: Record<Locale, string> = {
  en: "EN",
  zh: "中",
};

export const LOCALE_FULL_LABELS: Record<Locale, string> = {
  en: "English",
  zh: "简体中文",
};

export type TranslationKey = keyof typeof translations.en;

const translations = {
  en: {
    // Brand / shell
    "brand.name": "GPGPU KB",
    "shell.openMenu": "Open menu",
    "shell.closeMenu": "Close menu",
    "shell.version": "v",

    // Sidebar nav
    "nav.browse": "Browse",
    "nav.chat": "Chat (RAG)",
    "nav.reports": "Daily Reports",
    "nav.stats": "Stats",
    "nav.primary": "Primary navigation",

    // Language switcher
    "lang.switch": "Switch language",
    "lang.english": "English",
    "lang.chinese": "Chinese",

    // Theme switcher
    "theme.switch": "Switch theme",
    "theme.light": "Light",
    "theme.dark": "Dark",

    // Search bar
    "search.placeholder": "Search papers, blogs, projects...",

    // Browse
    "browse.title": "Browse",
    "browse.search": "Search:",
    "browse.items": "{count} items",
    "browse.sort": "Sort:",
    "browse.sort.score": "Score",
    "browse.sort.date": "Date",
    "browse.filter.all": "All",
    "browse.filter.papers": "Papers",
    "browse.filter.blogs": "Blogs",
    "browse.filter.projects": "Projects",
    "browse.filter.talks": "Talks",
    "browse.empty.title": "No papers found",
    "browse.empty.hint": "Try adjusting your filters or run the ingestion pipeline first.",
    "browse.pagination.previous": "Previous",
    "browse.pagination.next": "Next",
    "browse.pagination.page": "Page {page} of {total}",

    // Paper card
    "card.morePeople": " +{count} more",
    "card.processing": "Processing...",
    "card.source": "Source",
    "card.pdf": "PDF",
    "score.originality": "Originality",
    "score.impact": "Impact",
    "score.depth": "Depth",
    "score.actionability": "Actionability",
    "score.innovation": "Innovation",
    "score.maturity": "Maturity",
    "score.quality": "Quality",
    "score.relevance": "Relevance",

    // Paper detail
    "paper.back": "← Back to browse",
    "paper.openSource": "Open source",
    "paper.pdf": "PDF",
    "paper.chatAbout": "Chat about this",
    "paper.summary": "Summary",
    "paper.notFound": "Paper not found.",
    "paper.processingHint": "This item is still being processed. Summary coming soon.",
    "paper.originalAbstract": "Original Abstract",
    "paper.originalExcerpt": "Original Excerpt",
    "paper.morePeople": " +{count}",
    "paper.organizationsLabel": "",

    // Reports
    "reports.title": "Daily Reports",
    "reports.papersCovered": "{count} papers covered",
    "reports.empty": "No reports generated yet.",
    "reports.back": "← Back to reports",
    "reports.notFound": "Report not found.",

    // Stats
    "stats.title": "Knowledge Base Stats",
    "stats.totalItems": "Total Items",
    "stats.processed": "Processed",
    "stats.byType.paper": "Papers",
    "stats.byType.blog": "Blogs",
    "stats.byType.project": "Projects",
    "stats.byType.talk": "Talks",
    "stats.topImpact": "Highest Impact Papers",

    // Chat
    "chat.welcome":
      "I'm your GPGPU research assistant. Ask me anything about papers, architectures, optimizations, or trends in the knowledge base. Pin a source on the right to chat with a single paper or blog (arXiv PDFs are loaded in full).",
    "chat.role.assistant": "Assistant",
    "chat.role.you": "You",
    "chat.sources": "Sources:",
    "chat.placeholder.default": "Ask about GPU architectures, attention, LLMs...",
    "chat.placeholder.anchored": "Ask about \"{title}...\"",
    "chat.send": "Send",
    "chat.stop": "Stop generating",
    "chat.loading.search": "Searching knowledge base...",
    "chat.loading.reading": "Reading the source...",
    "chat.disclaimer.default":
      "Answers are based on papers in the knowledge base. Results may vary by processing state.",
    "chat.disclaimer.anchored":
      "Anchored to a single source — the LLM sees its full content.",
    "chat.error.generic":
      "Sorry, I couldn't process that query. Is the backend running?",
    "chat.empty": "(LLM produced no output)",
    "chat.banner.anchored": "Anchored to:",

    // Chat sidebar
    "chat.tabs.history": "History",
    "chat.tabs.source": "Source",
    "chat.newChat": "New chat",
    "chat.history.loading": "Loading…",
    "chat.history.empty":
      "No saved conversations yet. Start chatting and your sessions will appear here.",
    "chat.history.delete": "Delete conversation",
    "chat.time.justNow": "just now",
    "chat.time.minutes": "{n}m ago",
    "chat.time.hours": "{n}h ago",
    "chat.time.days": "{n}d ago",
    "chat.source.intro":
      "Pin a single source. Its full content (PDF text for arXiv) is loaded into every prompt instead of relying on retrieval.",
    "chat.source.empty": "No source pinned (using RAG).",
    "chat.source.pick": "Pick source",
    "chat.source.change": "Change source",
    "chat.source.clear": "Clear source",

    // Source picker
    "picker.title": "Pick a source for this chat",
    "picker.description":
      "Choose a paper, blog, project, or talk. Its full content will anchor the conversation.",
    "picker.placeholder": "Search by title, abstract, or summary...",
    "picker.searching": "Searching...",
    "picker.empty": "No matching sources.",
    "picker.hint": "Type to search the knowledge base.",
  },

  zh: {
    "brand.name": "GPGPU 知识库",
    "shell.openMenu": "打开菜单",
    "shell.closeMenu": "关闭菜单",
    "shell.version": "版本 ",

    "nav.browse": "浏览",
    "nav.chat": "对话 (RAG)",
    "nav.reports": "每日简报",
    "nav.stats": "统计",
    "nav.primary": "主导航",

    "lang.switch": "切换语言",
    "lang.english": "英文",
    "lang.chinese": "中文",

    "theme.switch": "切换主题",
    "theme.light": "明亮",
    "theme.dark": "暗黑",

    "search.placeholder": "搜索论文、博客、项目……",

    "browse.title": "浏览",
    "browse.search": "搜索：",
    "browse.items": "共 {count} 条",
    "browse.sort": "排序：",
    "browse.sort.score": "评分",
    "browse.sort.date": "时间",
    "browse.filter.all": "全部",
    "browse.filter.papers": "论文",
    "browse.filter.blogs": "博客",
    "browse.filter.projects": "项目",
    "browse.filter.talks": "演讲",
    "browse.empty.title": "暂无匹配结果",
    "browse.empty.hint": "试着调整筛选条件，或先运行一次抓取流水线。",
    "browse.pagination.previous": "上一页",
    "browse.pagination.next": "下一页",
    "browse.pagination.page": "第 {page} 页，共 {total} 页",

    "card.morePeople": " 等 {count} 人",
    "card.processing": "处理中……",
    "card.source": "原文",
    "card.pdf": "PDF",
    "score.originality": "原创性",
    "score.impact": "影响力",
    "score.depth": "深度",
    "score.actionability": "实操性",
    "score.innovation": "创新性",
    "score.maturity": "成熟度",
    "score.quality": "质量",
    "score.relevance": "相关性",

    "paper.back": "← 返回列表",
    "paper.openSource": "查看原文",
    "paper.pdf": "PDF",
    "paper.chatAbout": "就此对话",
    "paper.summary": "摘要",
    "paper.notFound": "未找到该条目。",
    "paper.processingHint": "该条目仍在处理，摘要稍后生成。",
    "paper.originalAbstract": "原始摘要",
    "paper.originalExcerpt": "原始片段",
    "paper.morePeople": " 等 {count}",
    "paper.organizationsLabel": "",

    "reports.title": "每日简报",
    "reports.papersCovered": "覆盖 {count} 项",
    "reports.empty": "暂未生成任何简报。",
    "reports.back": "← 返回简报列表",
    "reports.notFound": "未找到该简报。",

    "stats.title": "知识库统计",
    "stats.totalItems": "总条目",
    "stats.processed": "已处理",
    "stats.byType.paper": "论文",
    "stats.byType.blog": "博客",
    "stats.byType.project": "项目",
    "stats.byType.talk": "演讲",
    "stats.topImpact": "高影响力论文",

    "chat.welcome":
      "我是你的 GPGPU 研究助理。可以向我询问知识库里任何论文、架构、优化或趋势相关的问题。你也可以在右侧固定一个来源，与单篇论文或博客对话（arXiv 论文会读取完整 PDF）。",
    "chat.role.assistant": "助理",
    "chat.role.you": "你",
    "chat.sources": "参考来源：",
    "chat.placeholder.default": "问问 GPU 架构、Attention、LLM……",
    "chat.placeholder.anchored": "围绕「{title}……」提问",
    "chat.send": "发送",
    "chat.stop": "停止生成",
    "chat.loading.search": "正在检索知识库……",
    "chat.loading.reading": "正在阅读来源……",
    "chat.disclaimer.default":
      "回答基于知识库中的论文，结果可能受处理状态影响。",
    "chat.disclaimer.anchored":
      "已固定到单一来源——大模型能看到它的完整内容。",
    "chat.error.generic":
      "抱歉，无法处理该问题。后端服务是否在运行？",
    "chat.empty": "（模型未输出内容）",
    "chat.banner.anchored": "已锚定来源：",

    "chat.tabs.history": "历史",
    "chat.tabs.source": "来源",
    "chat.newChat": "新建对话",
    "chat.history.loading": "加载中……",
    "chat.history.empty": "暂无保存的对话。开始聊天后会自动出现在这里。",
    "chat.history.delete": "删除对话",
    "chat.time.justNow": "刚刚",
    "chat.time.minutes": "{n} 分钟前",
    "chat.time.hours": "{n} 小时前",
    "chat.time.days": "{n} 天前",
    "chat.source.intro":
      "固定一个来源后，每次提问都会把它的完整内容（arXiv 论文是 PDF 全文）注入到 prompt，而不再依赖检索。",
    "chat.source.empty": "未固定来源（使用 RAG 检索）。",
    "chat.source.pick": "选择来源",
    "chat.source.change": "更换来源",
    "chat.source.clear": "清除来源",

    "picker.title": "为本次对话选择一个来源",
    "picker.description":
      "选择论文、博客、项目或演讲，它的完整内容将作为本次对话的锚点。",
    "picker.placeholder": "按标题、摘要或正文搜索……",
    "picker.searching": "搜索中……",
    "picker.empty": "未找到匹配的来源。",
    "picker.hint": "输入关键字以检索知识库。",
  },
} as const;

export default translations;
