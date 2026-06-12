# PKCS Table/Image Artifact Enrichment 验收报告

日期：2026-06-12
任务：`.trellis/tasks/06-10-pkcs-table-image-artifact-enrichment`
状态：通过

## 验收结论

当前代码已经实现本任务确认的 Markdown-only artifact-aware ingest skeleton，并通过本地数据库集成验收。

本轮验收确认：

* Markdown table/image artifact 设计已落地到数据库、parser、ingest service、search、Context Pack 和测试。
* 基础 ingest 不依赖 Codex/Claude Code 视觉能力，也不接入 OCR、vision API、embedding 或 reranker。
* Raw Archive 继续作为证据源；Markdown 原文 locator 保持可读回。
* table/image artifact 会生成结构化对象，并通过 chunk metadata 与 narrative/derived chunks 建立可靠关联。
* Context Pack 可以对 narrative chunk 或 artifact-derived chunk 做轻量 artifact hydration。

## 已验收范围

* Alembic migration 新增 `table_artifacts` 与 `image_artifacts`。
* SQLAlchemy ORM 与 repository 支持 table/image artifact 写入和读取。
* Markdown parser 识别 Markdown table 与单行 Markdown image reference。
* narrative chunk 使用 placeholder 保留上下文，并在 `metadata_json.linked_artifacts` 中保存可靠关联。
* table artifact 派生 `table_summary` 与 `table_rows` chunks。
* image artifact 派生 `image_summary` chunk。
* ingest service 负责创建 artifact rows、复制本地相对图片资产到 Raw Archive、把 artifact key 映射为 artifact id。
* search result 能返回 artifact-derived chunk metadata。
* Context Pack 能根据 `artifact_id` hydrate table/image 基础摘要。
* 测试覆盖 schema、repository、ingest、search、Context Pack、Raw Archive。

## 验收命令

```text
git fetch --dry-run
docker compose ps postgres
docker compose up -d postgres
uv run alembic upgrade head
uv run pytest
python .trellis/scripts/task.py validate .trellis/tasks/06-10-pkcs-table-image-artifact-enrichment
git diff --check
```

## 验收结果

```text
git fetch --dry-run: no remote updates printed
docker engine: started successfully, server version 29.2.1
postgres: pkcs-postgres healthy on 54329
alembic: upgraded to head successfully
pytest: 41 passed, 1 warning
trellis validate: implement 17, check 10, debug 7 all passed
git diff --check: passed
```

测试警告：

```text
StarletteDeprecationWarning from fastapi.testclient/httpx compatibility
```

该警告来自第三方测试客户端兼容层，不影响本任务验收结果。

## 相关提交

* `371ce9c` docs: plan table image artifact enrichment
* `0630300` docs: confirm markdown-only artifact scope
* `ca65926` feat: add markdown artifact-aware ingest skeleton
* `37fa093` test: isolate pytest database
* `be72f2d` chore: configure artifact enrichment task context

## 保持范围外

本轮未实现：

* PDF、HTML、docx 中的表格/图片解析。
* OCR、vision summary、detected entities。
* embedding、rerank、semantic retrieval。
* Codex/Claude Code 作为默认 ingest-time vision provider。
* UI 或远程服务暴露。

