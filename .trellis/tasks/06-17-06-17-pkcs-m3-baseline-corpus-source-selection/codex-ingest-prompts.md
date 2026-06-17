# Codex prompts for M3 baseline corpus ingestion

以下提示词供后续验收时分阶段使用。不要在本任务中执行。

## Prompt 1: 下载和落盘，不摄入

```text
使用 pkcs-ingest skill 的输入约束，但这一步只下载资料，不运行 prepare-ingest，也不调用 MCP ingest_source。

请读取：
.trellis/tasks/06-17-06-17-pkcs-m3-baseline-corpus-source-selection/selected-sources.jsonl

任务：
1. 创建 data/private/m3-baseline/source-downloads/。
2. 按 selected-sources.jsonl 的 suggested_local_path 下载每个 URL。
3. 对 format=html 的资料，将页面保存成单个 .html 文件；如站点阻止或页面依赖 JS，记录到 data/private/m3-baseline/download-report.json，不要伪造内容。
4. 对 format=md 的资料，下载 raw Markdown，确保本地文件扩展名是 .md。
5. 对 format=pdf/docx 的资料，保存原始二进制文件，扩展名保持 .pdf/.docx。
6. 不提交 data/private 下任何文件。
7. 输出 download-report.json，字段包含 id、url、local_path、status、content_type、bytes、warning、error。

验收：
* 至少 smoke batch 的 12 条资料下载成功。
* 下载失败只记录，不改 selected-sources.jsonl。
* 不运行 uv run pkcs prepare-ingest。
* 不调用 MCP ingest_source。
```

## Prompt 2: smoke batch prepare-ingest，不 MCP 摄入

```text
使用 pkcs-ingest skill。只对 data/private/m3-baseline/source-downloads/ 中已下载的 smoke batch 资料运行 prepare-ingest，不调用 MCP ingest_source。

任务：
1. 读取 selected-sources.jsonl 和 data/private/m3-baseline/download-report.json。
2. 选择每个领域各 4 条，并覆盖 html/pdf/docx/md 四种格式。
3. 对每个本地文件运行：
   uv run pkcs prepare-ingest <source-path> --output-root data/private/ingest-prep --slug <id-lowercase>
4. 读取命令 JSON 输出，汇总 status、document_path、prep_dir、counts、warnings、errors。
5. 对 success/success_with_warnings 的 package，检查 document.md 非空，记录 assets/tables 数量。
6. 不生成 image-enrichment.json，除非当前验收明确要求视觉理解。
7. 不调用 MCP ingest_source。

输出：
data/private/m3-baseline/prepare-smoke-report.json

验收：
* 每种格式至少 1 条 prepare-ingest 成功或 success_with_warnings。
* hard_fail 必须记录 errors 和 ingest_log_path。
* 不摄入知识库。
```

## Prompt 3: smoke batch MCP 摄入

```text
使用 pkcs-ingest skill。只摄入 smoke batch 中 prepare-ingest 成功的 package。

任务：
1. 读取 data/private/m3-baseline/prepare-smoke-report.json。
2. 对 status=success 或 success_with_warnings 的每个条目，使用 document_path 调用 MCP：
   ingest_source(path="<document_path>", knowledge_type="document", canonical_key="<selected canonical_key>")
3. canonical_key 使用 selected-sources.jsonl 中对应条目的 canonical_key。
4. 记录 MCP 返回的 source_id、version_id、canonical_key、status。
5. 对每条摄入资料，用 search/read/context_pack 做最小 smoke：
   * search_knowledge 查询标题中的 2-4 个关键词。
   * read_source 读回一段 evidence。
   * get_context_pack 生成一个小 budget 的 Context Pack。
6. 不把原文贴到对话里，只报告结构和 warnings。

输出：
data/private/m3-baseline/ingest-smoke-report.json

验收：
* 至少 8 条资料完成 MCP 摄入。
* 每条成功资料至少能被 search 命中一次。
* 每条成功资料至少能 read_source 读回 evidence。
* Context Pack evidence 必须可追溯 source_id/version_id/locator 或 chunk_id。
```

## Prompt 4: full corpus 批量摄入和验收报告

```text
使用 pkcs-ingest skill。基于 selected-sources.jsonl 全量执行下载、prepare-ingest、MCP ingest 和验收报告；继续遵守 data/private 不提交原则。

任务：
1. 对所有未下载资料执行下载；保留 download-report.json。
2. 对所有下载成功资料执行 prepare-ingest；保留 prepare-full-report.json。
3. 对所有 prepare 成功或 success_with_warnings 的 document.md 调用 MCP ingest_source。
4. canonical_key 使用 selected-sources.jsonl 中的 canonical_key。
5. 汇总每个领域、格式、内容类型的成功/失败数量。
6. 抽样生成 30 条候选 no-marker eval query 草稿，暂存到 data/private/m3-baseline/eval-query-draft.jsonl。
7. 不提交原文、下载文件、ingest-prep package 或 private report；如需要提交，只提交结构性摘要到 Trellis。

验收：
* 下载、prepare、ingest 三个阶段都有 machine-readable report。
* 失败项可以重试但不要静默跳过。
* 不改变 PKCS 代码。
* 不把 URL 直接传给 MCP ingest_source；MCP 只接收 prepare-ingest 生成的 document.md。
```

