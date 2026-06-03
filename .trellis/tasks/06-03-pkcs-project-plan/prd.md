# brainstorm: Personal Knowledge Context Server Project Plan

## Goal

把 `personal_knowledge_context_server_design.md` 中的愿景文档收敛成可执行项目规划：从第一步如何开始，到每个阶段如何开发、如何验收、如何确认完成，都形成双方同步的 PRD 与路线图。澄清阶段结束后，应能基于本 PRD 拆分阶段任务并进入 Trellis Phase 2 实施准备。

## What I Already Know

* 用户希望以 brainstorm 方式推进，不直接进入实现。
* 目标项目暂定名为 Personal Knowledge Context Server，简称 PKCS，中文名为个人知识上下文服务。
* 核心定位是“面向外部 Agent 的个人知识库后端服务”，不是聊天 UI，也不是替主 Agent 决策的自治 Agent。
* 核心输出是可追溯、可压缩、可注入主 Agent 上下文的 Context Pack。
* 外部使用者包括 Claude Code、Codex、OpenClaw、IDE Agent、本地 Agent、自动化脚本和未来自定义工作流。
* 总路线被设计为五个阶段：M1 接入骨架与数据底座，M2 摄入与基础检索 MVP，M3 检索编排与 Context Pack，M4 特色知识源增强，M5 知识沉淀、安全、评测与运维。
* 原设计已经给出 MVP 建议范围：MCP / HTTP 接入、Raw Archive、PostgreSQL metadata、基础搜索、read_source、get_context_pack v0、AI 对话 ingest、Markdown / 网页 ingest、GitHub repo ingest v0。
* 当前仓库尚无实现代码，只有 `AGENTS.md`、`.trellis/` 和 `personal_knowledge_context_server_design.md`。

## Assumptions (Temporary)

* 第一轮讨论目标是项目规划与 PRD 澄清，不要求本轮写业务代码。
* 本项目应优先支持本地个人使用，再逐步扩展到服务器部署和多 Agent 接入。
* 第一阶段应保持轻量，先验证 Agent 工具接口、Raw Archive、元数据、基础检索和证据回读闭环。
* `AGENTS.md` 中注入的规划上下文仅用于本次 PRD 澄清期间的防丢失，用户会在澄清结束后手动删除。

## Open Questions

* MVP 首个可运行版本应该优先选择哪种接入形态：MCP-only、HTTP-only，还是 MCP + HTTP 双接口？
* MVP 首个可运行版本应该优先支持哪些资料源：只做 AI 对话 + Markdown，还是同时包含 GitHub repo ingest v0？
* MVP 检索底座应该优先走轻量本地方案，还是从 PostgreSQL + OpenSearch/pgvector 开始？
* Context Pack v0 的输出格式应优先是 JSON、Markdown，还是 JSON + Markdown 混合？

## Requirements (Evolving)

* 项目规划必须覆盖从启动、开发、验收到完成确认的完整路线。
* 每个阶段必须有明确目标、产物、验收标准和完成定义。
* 每确认一个阶段 PRD，都要立即写入任务 PRD。
* 必须将澄清期必要上下文临时注入 `AGENTS.md`，降低会话信息丢失风险。
* 规划应优先控制范围，避免一开始引入复杂 Graph、完整 LLM Wiki、多 Agent 自治或复杂 UI。

## Acceptance Criteria (Evolving)

* [ ] 项目级目标、边界、阶段路线被整理成可执行 PRD。
* [ ] M1 到 M5 每个阶段都有目标、范围、产物、验收标准和完成定义。
* [ ] MVP 范围明确列出必须做与明确不做。
* [ ] 技术路线关键决策记录为 ADR-lite。
* [ ] 后续实施计划被拆成小 PR / 小任务顺序。
* [ ] `AGENTS.md` 包含本次澄清阶段的临时上下文块。

## Definition of Done

* 用户确认项目级路线与 MVP 边界。
* 用户确认至少第一个实施 PRD，可进入 Trellis Phase 2。
* 任务 PRD 与 `AGENTS.md` 临时块都反映最新共识。
* 明确如何开始、如何推进、如何验收、如何确认完成。

## Out of Scope (Explicit)

* 本轮不实现业务代码，除非用户明确要求进入实现。
* 本轮不搭建完整 LLM Wiki / GraphRAG / 多 Agent 自治系统。
* 本轮不追求完整 UI 产品。
* 本轮不自动导入真实私密资料。

## Technical Notes

* Source design document: `personal_knowledge_context_server_design.md`
* Task directory: `.trellis/tasks/06-03-pkcs-project-plan`
* Temporary planning context target: `AGENTS.md`
* Current repo implementation state: no application source code found via `rg --files`; planning starts from design document.

## Initial Project Structure Proposal

### Project-Level Phases

* Phase 0: Planning and executable PRD set
* Phase 1: M1 接入骨架与数据底座
* Phase 2: M2 摄入与基础检索 MVP
* Phase 3: M3 检索编排与 Context Pack
* Phase 4: M4 特色知识源增强
* Phase 5: M5 知识沉淀、安全、评测与运维

### MVP Success Statement

MVP 完成时，至少一个真实主 Agent 能调用 PKCS 工具，导入小型个人资料集，搜索相关资料，读取原文证据，并拿到带引用的 Context Pack v0 来完成一次真实规划、写作或编码任务。

