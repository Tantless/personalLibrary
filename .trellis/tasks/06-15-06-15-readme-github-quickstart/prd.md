# brainstorm: simplify README for GitHub quickstart

## Goal

精简当前 `README.md`，让它更像一个面向 GitHub 用户的项目 README：用户能看懂项目用途，自行安装必要环境，并快速启动本地服务与 CLI。

## What I already know

* 用户要求减少项目流程说明，不要臃肿。
* 当前 README 包含大量 PR 阶段、MVP 进度、内部验收和实现细节。
* 项目运行依赖 Python 3.11+、uv、Docker Compose PostgreSQL。
* CLI 入口是 `uv run pkcs`，常用命令包括 `health`、`ingest`、`prepare-ingest`、`search`、`read`、`context-pack`。

## Assumptions

* README 应保留中文自然语言说明，技术名词、命令和配置键保留英文。
* README 不需要记录 Trellis 任务流、PR 阶段或内部验收历史。

## Requirements

* 保留项目简介、功能概览、环境要求、快速启动、常用命令、测试和配置说明。
* 移除过长的开发流程、PR 进度、详细 schema 说明和内部验收记录。
* 保持命令与当前代码入口一致。

## Acceptance Criteria

* [ ] README 能指导新用户完成安装依赖、启动 PostgreSQL、迁移数据库和运行健康检查。
* [ ] README 包含摄入、搜索、读取证据、Context Pack 的最小 CLI 示例。
* [ ] README 不再包含 PR1/PR2 等内部项目进度叙述。

## Definition of Done

* README 精简完成。
* Markdown 格式检查通过。
* 变更提交到 git。

## Out of Scope

* 不修改应用代码。
* 不新增安装脚本或 MCP 客户端配置模板。
* 不更新 Trellis/spec 规范。

## Technical Notes

* `pyproject.toml` declares `requires-python = ">=3.11"` and script `pkcs = "pkcs.cli:app"`。
* `docker-compose.yml` exposes PostgreSQL on local port `54329`。
* `src/pkcs/config.py` documents relevant `PKCS_` environment settings and defaults。
