# M3 baseline corpus source selection notes

## Summary

本任务选择 100 条公开资料源，只作为 M3 baseline corpus 的候选下载/摄入计划。资料源按现有 `pkcs-ingest` skill 可处理的本地单文件格式规划：

| Format | Count | Intended handling |
|---|---:|---|
| HTML | 52 | 下载/保存为 `.html`，再运行 `prepare-ingest` |
| PDF | 23 | 直接下载为 `.pdf`，由 Docling 规范化 |
| MD | 19 | 下载 raw Markdown 为 `.md`，无需 Docling |
| DOCX | 6 | 直接下载为 `.docx`，由 Docling 规范化 |

领域分布：

| Domain | Count |
|---|---:|
| AI 技术 | 45 |
| 游戏技术 | 34 |
| 动漫/动画 | 21 |

内容类型覆盖：

| Content type | Examples |
|---|---|
| 技术文档 | OpenAI/GitHub docs, Unreal Lumen/Nanite docs, Unity Entities, Godot docs |
| 官方 QA | OpenAI Help Center, Unreal FAQ/license, Crunchyroll Help |
| 近期新闻 | OpenAI 2026 news, Anthropic 2026 news, Google 2026 AI updates, NVIDIA 2026 technical blog |
| 访谈 | Sam Altman event replay, Unreal developer interviews, Crunchyroll anime staff interviews, Netflix animation creator interview |
| 技术报告/论文 | OpenAI/Anthropic reports, AI Agent Index, arXiv anime/animation papers, ESA report, SIGGRAPH real-time rendering PDF |

## Selection Rules

* 只选公开资料源，不提交下载后的原文。
* 优先官方、学术、行业组织、开发者文档和专业媒体。
* 避免营销号、SEO 软文、低可信转存、需要登录付费或版权状态不清的来源。
* 对 AJA、GDC 等报告类资料，后续下载前应优先从官方 landing page 获取最新下载链接。
* 对 GitHub Markdown，优先使用 `raw.githubusercontent.com`，确保本地保存后扩展名是 `.md`。
* 对网页，后续应保存为单个 `.html` 文件；如页面大量依赖 JS，应记录下载 warning 并人工检查 `document.md` 是否为空。

## Recommended Batches

1. **Batch A: smoke batch, 12 docs**
   * 每个领域 4 条。
   * 每种格式至少 2 条。
   * 用于确认下载、Docling、Markdown package、MCP ingest 链路没有系统性问题。
2. **Batch B: balanced baseline, 50 docs**
   * AI 20、游戏 18、动漫/动画 12。
   * 保留访谈/QA/新闻/论文/文档混合。
   * 用于建立第一版 M3 no-marker eval queries。
3. **Batch C: full candidate corpus, 100 docs**
   * 全量摄入。
   * 用于压力测试 Context Pack source diversity、PDF/DOCX table/image artifact、long document retrieval。

## Files

* `selected-sources.jsonl`: 100 条候选资料源 manifest。
* `codex-ingest-prompts.md`: 后续给 Codex 的批量下载、摄入、验收提示词。
