# PKCS ingest normalization tooling 验收报告

日期：2026-06-15
任务：`.trellis/tasks/06-15-pkcs-ingest-normalization-tooling`
状态：自动验证通过，待用户验收

## 验收结论

已实现 `prepare-ingest command -> MCP ingest_source` 链路：

```text
uv run pkcs prepare-ingest <source>
  -> document.md + assets/ + tables/ + source-info.json + ingest-log.json
  -> MCP ingest_source(path=document.md, knowledge_type=document)
```

`pkcs-ingest` skill 已更新为这条真实链路的说明书。README 已在功能验证后补充从零环境安装、准备和摄入说明。

## 实现摘要

* `src/pkcs/ingest/normalization.py`
  * 新增 `PrepareIngestService`。
  * 支持 Markdown package 生成。
  * 本地图片复制到 `assets/` 并改写 Markdown/HTML/reference image 引用。
  * 远程图片保持 URL，不下载。
  * 大表落 `tables/table-001.md`，`document.md` 保留引用。
  * 外部 Docling CLI adapter 支持 PDF/DOCX/XLSX/HTML 转 Markdown。
  * Docling 缺失、超时、失败、空输出等返回 JSON `hard_fail`。
* `src/pkcs/cli.py`
  * 新增 `uv run pkcs prepare-ingest <source>`。
* `tests/test_ingest_normalization.py`
  * 覆盖 Markdown normalization、asset collision、missing image、Docling adapter、large table sidecar、CLI JSON、IngestService 链路和 MCP `ingest_source` 链路。
* `.agents/skills/pkcs-ingest/SKILL.md`
  * 更新为真实 agent workflow。
* `README.md`
  * 在验收后补充 zero-environment setup 和 pre-ingest 使用说明。

## 验收命令

```text
docker compose up -d postgres
docker compose ps postgres
uv run alembic upgrade head
uv run pytest tests/test_ingest_normalization.py -q
uv run pytest tests/test_ingest.py tests/test_ingest_trace.py tests/test_context_pack.py tests/test_search.py tests/test_ingest_normalization.py -q
uv run pytest
git diff --check
```

## 验收结果

```text
postgres: healthy
alembic: upgraded to head successfully
tests/test_ingest_normalization.py: 8 passed
related ingest/search/context tests: 33 passed
full pytest: 54 passed, 1 warning
git diff --check: passed
```

测试警告：

```text
StarletteDeprecationWarning from fastapi.testclient/httpx compatibility
```

该警告来自第三方测试客户端兼容层，不影响本任务结果。

## 明确边界

* Docling 作为外部 CLI 调用，不加入 PKCS 主依赖。
* 未新增 MCP tool；继续复用 `ingest_source`。
* 未实现目录批量 pre-ingest。
* 未下载远程图片。
* 未实现 OCR、vision summary、detected entities。
