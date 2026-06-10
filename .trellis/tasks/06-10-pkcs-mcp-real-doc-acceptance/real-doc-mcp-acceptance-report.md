# PKCS MCP 真实资料验收报告

日期：2026-06-10
任务：`.trellis/tasks/06-10-pkcs-mcp-real-doc-acceptance`
状态：通过

## 目标

清除本地 PKCS 原测试数据后，使用真实官方技术资料，严格通过 MCP 工具入口完成摄入、检索、证据读回和 Context Pack 验收。

## 环境与清理

执行前确认：

* `git fetch --dry-run` 无远端更新输出；本地 `main` ahead `origin/main` 4 个提交。
* 工作树已有用户本地改动：`.codex/config.toml`。本轮不修改、不提交该文件。
* Docker daemon 可用，版本 `29.2.1`。

清理动作：

* 执行 `docker compose down -v`，删除 `personallibrary_pkcs-postgres-data` volume。
* 删除 `Z:\personalLibrary\data\raw`。
* 重新执行 `docker compose up -d postgres`。
* 等待 `pkcs-postgres` healthcheck 为 `healthy`。
* 执行 `uv run alembic upgrade head`，迁移到 `20260609_0007`。

清库后计数：

```text
sources=0
chunks=0
ingest_jobs=0
```

## 测试资料

资料下载到 `data/private/acceptance-inputs/2026-06-10-mcp-real-docs/`，该目录被 `.gitignore` 覆盖，不提交。

| 名称 | URL | 本地文件 | 大小 | 时效性记录 |
| --- | --- | --- | ---: | --- |
| OpenAI latest model | https://developers.openai.com/api/docs/guides/latest-model.md | `openai-latest-model.md` | 13,104 bytes | `Last-Modified: Wed, 10 Jun 2026 09:55:19 GMT` |
| OpenAI reinforcement fine-tuning | https://developers.openai.com/api/docs/guides/reinforcement-fine-tuning.md | `openai-reinforcement-fine-tuning.md` | 50,805 bytes | `Last-Modified: Wed, 10 Jun 2026 10:50:05 GMT` |
| Anthropic tool use overview | https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview.md | `anthropic-tool-use-overview.md` | 9,642 bytes | HTTP 200，`text/markdown`; 响应头未提供 `Last-Modified` |
| Anthropic context editing | https://platform.claude.com/docs/en/build-with-claude/context-editing.md | `anthropic-context-editing.md` | 79,644 bytes | HTTP 200，`text/markdown`; 响应头未提供 `Last-Modified` |

## MCP 验收方式

使用 MCP SDK stdio client 启动并调用同一个 server：

```text
uv run mcp run src/pkcs/mcp/server.py:mcp
```

调用的工具全部来自 MCP：

```text
health_check
ingest_source
search_knowledge
read_source
get_context_pack
```

未使用 `pkcs` CLI 或直接 application service 完成业务动作。

## 验收结果

`health_check` 返回：

```text
status=ok
service=Personal Knowledge Context Server
version=0.1.0
environment=local
```

### OpenAI latest model

* `canonical_key`: `document:acceptance-openai-latest-model-20260610`
* `ingest_source`: `completed`
* `source_id`: `30fe9551-51e2-46e4-b17c-36a706f156ae`
* `version_id`: `0f511f30-1a59-4b0e-a9da-c92b30181979`
* `chunks_created`: 16
* `search_knowledge` query: `reasoning effort`
* `search_count`: 5
* 第一条 `chunk_id`: `97d3f2e5-db9c-40f0-8cde-3193f958c262`
* 第一条 locator: `line 27-34`
* `read_source` context: `line 25-36`
* 单文档 `get_context_pack` evidence: 3

### OpenAI reinforcement fine-tuning

* `canonical_key`: `document:acceptance-openai-rft-20260610`
* `ingest_source`: `completed`
* `source_id`: `e870ea83-35d7-43bd-a429-f69f1953475a`
* `version_id`: `449fd905-4213-4ddf-b42f-75a5459db7b7`
* `chunks_created`: 45
* `search_knowledge` query: `programmable grader`
* `search_count`: 1
* 第一条 `chunk_id`: `9f1c3afd-5b60-47db-bd17-c3abf2e2fb71`
* 第一条 locator: `line 1-47`
* `read_source` context: `line 1-49`
* 单文档 `get_context_pack` evidence: 1

### Anthropic tool use overview

* `canonical_key`: `document:acceptance-anthropic-tool-use-20260610`
* `ingest_source`: `completed`
* `source_id`: `e6dc865d-4d51-41d7-b69c-617b429e5fed`
* `version_id`: `d6945f20-43dd-4e42-984d-ed90c80fab8b`
* `chunks_created`: 8
* `search_knowledge` query: `client tools server tools`
* `search_count`: 3
* 第一条 `chunk_id`: `ddb103ab-8251-4f0c-9384-05fe064a290b`
* 第一条 locator: `line 1-61`
* `read_source` context: `line 1-63`
* 单文档 `get_context_pack` evidence: 3

### Anthropic context editing

* `canonical_key`: `document:acceptance-anthropic-context-editing-20260610`
* `ingest_source`: `completed`
* `source_id`: `c87f7806-da80-439b-a14a-94627c12bcde`
* `version_id`: `077c439f-b9b4-4271-906e-be203d2eabf3`
* `chunks_created`: 65
* `search_knowledge` query: `Tool result clearing`
* `search_count`: 5
* 第一条 `chunk_id`: `d6bf5712-5a38-473c-b507-53c6471a8772`
* 第一条 locator: `line 76-146`
* `read_source` context: `line 74-148`
* 单文档 `get_context_pack` evidence: 3

## 跨资料 Context Pack

调用：

```text
get_context_pack(query="tool use reasoning", top_k=10, budget_tokens=1400)
```

结果：

* `evidence_count`: 3
* `source_count`: 1
* `has_conflicts_caveats`: true
* 第一条 evidence：
  * `canonical_key`: `document:acceptance-openai-latest-model-20260610`
  * `chunk_id`: `e28cdf65-b516-4cbe-b45d-ce0150555cc8`
  * `source_id`: `30fe9551-51e2-46e4-b17c-36a706f156ae`
  * `version_id`: `0f511f30-1a59-4b0e-a9da-c92b30181979`
  * `locator`: `line 53-61`

说明：该跨资料查询被 PostgreSQL FTS 排序集中命中 OpenAI latest model 文档。这符合当前 MVP 的 FTS 行为；单文档验收已分别用 `canonical_key` 覆盖 4 份资料。

## 最终数据库状态

验收完成后计数：

```text
sources=4
source_versions=4
chunks=134
citations=134
ingest_jobs=4
```

Raw Archive 文件数：

```text
4
```

当前 source：

```text
document:acceptance-anthropic-context-editing-20260610
document:acceptance-anthropic-tool-use-20260610
document:acceptance-openai-latest-model-20260610
document:acceptance-openai-rft-20260610
```

## 观察与调整

第一次试跑中，OpenAI latest model 使用了过宽查询 `GPT-5.5 latest model upgrade reasoning effort migration`，PostgreSQL `websearch_to_tsquery` 没有在单个 chunk 内返回命中。随后将每份资料查询改为更贴近局部段落的关键词，并重新清库完整重跑。

这说明当前 MVP 检索适合精确关键词和局部证据检索；面向更自然语言的宽查询，后续 M3+ 可考虑语义召回、rerank 或查询改写。

## 结论

本轮真实资料 MCP 验收通过。当前最终实现可通过 MCP stdio transport 完成：

```text
health_check -> ingest_source -> search_knowledge -> read_source -> get_context_pack
```

所有 search result 和 Context Pack evidence 均可追溯到 `source_id`、`version_id`、`chunk_id` 与 locator。
