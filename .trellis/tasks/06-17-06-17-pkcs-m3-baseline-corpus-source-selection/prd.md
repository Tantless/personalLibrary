# brainstorm: PKCS M3 baseline corpus source selection

## Goal

为 M3 baseline 准备一批可人工验收、可由现有 `pkcs-ingest` skill 批量处理的真实公开技术资料源。当前只做资料源选择和摄入提示词设计，不下载、不转换、不调用 MCP ingest；实际摄入过程作为后续验收项单独执行。

## What I already know

* 用户要求从网上选取 50-100 篇真实技术文章/资料，最好按“这一百个文档”规划。
* 资料必须包含 `.pdf`、`.docx`、`.md` 格式；网页资料可以保存为 `.html` 后走当前 skill。
* 资料必须覆盖名人/主创访谈、技术文档、官方 QA、近期新闻等内容类型。
* 用户偏好试验领域为：游戏、动漫、AI 技术。
* 用户要求避免营销号和低质量 SEO 文章。
* 当前唯一摄入入口是 `pkcs-ingest` skill：本地单文件经 `uv run pkcs prepare-ingest` 规范化，再由 MCP `ingest_source(path=document.md, knowledge_type="document")` 摄入。
* 当前任务只负责创建 Trellis 资料准备项和选择文档，不直接完成摄入流程。

## Requirements

* 选源数量为 100 条候选资料，方便后续按批次抽样或全量摄入。
* 每条资料必须记录：
  * 稳定 ID。
  * 领域：AI 技术、游戏技术、动漫/动画。
  * 内容类型：技术文档、官方 QA、近期新闻、访谈、技术报告/论文。
  * 目标本地格式：`.html`、`.pdf`、`.docx`、`.md`。
  * 原始 URL。
  * 建议本地保存路径。
  * 建议 `canonical_key`。
  * 选择理由和摄入注意事项。
* 优先使用官方、厂商文档、学术/技术报告、权威行业组织、主流专业媒体或官方访谈。
* 网页资料只作为 `.html` 下载/保存候选；不要在本任务中抓取网页正文。
* PDF/DOCX/MD/HTML 全部必须是现有 `prepare-ingest` 支持的单文件输入。
* 后续提示词必须显式要求 Codex 使用 `pkcs-ingest` skill，不直接把 URL 当作 MCP `ingest_source` 输入。

## Acceptance Criteria

* [x] Trellis 任务目录存在。
* [x] 任务 PRD 记录目标、约束、范围外和验收标准。
* [x] 100 条候选资料源写入机器可读清单。
* [x] 候选资料覆盖 `.pdf`、`.docx`、`.md`、`.html`。
* [x] 候选资料覆盖 AI 技术、游戏技术、动漫/动画。
* [x] 候选资料覆盖访谈、技术文档、官方 QA、近期新闻、论文/报告。
* [x] 提供后续 Codex 批量下载、prepare-ingest、MCP ingest、验收报告提示词。
* [x] 明确本任务不实际下载、不转换、不摄入。

## Definition of Done

* 本任务提交 Trellis 文档变更。
* 文档能指导后续 agent 批量下载并使用 `pkcs-ingest` skill 摄入。
* 资料源清单不包含私有内容，不提交下载后的原文。

## Technical Approach

* 使用 `selected-sources.jsonl` 作为后续脚本或 agent 批处理的 source manifest。
* 使用 `source-selection-notes.md` 记录筛选标准、分布统计和后续批次建议。
* 使用 `codex-ingest-prompts.md` 提供可直接交给 Codex 的分阶段提示词。
* 后续实际摄入时，将远程资料下载到 `data/private/m3-baseline/source-downloads/`，再逐个执行：

```powershell
uv run pkcs prepare-ingest <source-path> --output-root data/private/ingest-prep --slug <slug>
```

成功后再调用 MCP：

```text
ingest_source(path="<document_path>", knowledge_type="document", canonical_key="<canonical_key>")
```

## Out of Scope

* 不在本任务中下载 URL。
* 不在本任务中运行 `prepare-ingest`。
* 不在本任务中生成 `image-enrichment.json`。
* 不在本任务中调用 MCP `ingest_source`。
* 不在本任务中编写 M3 eval queries；该工作应在 corpus 实际摄入验收后进行。

## Technical Notes

* 使用过的本地上下文：
  * `.trellis/tasks/06-16-06-16-pkcs-m3-retrieval-context-pack-design/prd.md`
  * `Z:\personalLibrary\.agents\skills\pkcs-ingest\SKILL.md`
  * `tests/fixtures/`
  * `data/private/acceptance-inputs/`
* 选源原则：
  * 官方优先：OpenAI、Anthropic、Google DeepMind、NVIDIA、Epic、Unity、Godot、AJA、Crunchyroll、Netflix 等。
  * 报告/论文优先：OpenAI/Anthropic PDF、arXiv、ESA、SIGGRAPH/real-time rendering、AJA industry report。
  * 访谈优先官方或专业媒体：OpenAI Forum、Unreal developer interviews、PlayStation Blog、Crunchyroll interviews、Netflix Tudum。
  * 避免低质量 SEO：未选择随机 Medium 汇总、Scribd 转存、广告型行业报告页、论坛碎片讨论和 Reddit。
