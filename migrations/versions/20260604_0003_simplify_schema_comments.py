"""simplify schema comments

Revision ID: 20260604_0003
Revises: 20260604_0002
Create Date: 2026-06-04
"""

from alembic import op


revision = "20260604_0003"
down_revision = "20260604_0002"
branch_labels = None
depends_on = None


TABLE_COMMENTS = {
    "sources": "资料源表：保存长期资料身份。",
    "source_versions": "资料版本表：保存资料每次导入版本。",
    "chunks": "内容分块表：保存可检索资料片段。",
    "citations": "引用表：保存分块原文定位。",
    "ingest_jobs": "摄入任务表：记录摄入执行结果。",
    "alembic_version": "迁移版本表：记录数据库结构版本。",
}


COLUMN_COMMENTS = {
    "sources": {
        "id": "资料源ID：资料源主键。",
        "canonical_key": "规范键：同一长期资料的稳定身份。",
        "title": "标题：资料源显示标题。",
        "source_type": "资料类型：区分 AI 对话和文档。",
        "origin_uri": "来源路径：摄入时的原始路径记录。",
        "current_version_id": "当前版本ID：指向最新资料版本。",
        "created_at": "创建时间：资料源首次创建时间。",
        "updated_at": "更新时间：资料源最近更新时间。",
    },
    "source_versions": {
        "id": "版本ID：资料版本主键。",
        "source_id": "资料源ID：所属资料源。",
        "version_number": "版本号：同一资料源内递增序号。",
        "content_hash": "内容哈希：用于识别重复内容。",
        "file_path": "文件路径：摄入时的本地文件路径。",
        "raw_archive_path": "归档路径：Raw Archive 中的原文位置。",
        "imported_at": "导入时间：版本导入时间。",
        "status": "状态：版本导入状态。",
        "supersedes_version_id": "上一版本ID：被当前版本替代的版本。",
        "metadata_json": "元数据：版本级 JSON 附加信息。",
    },
    "chunks": {
        "id": "分块ID：内容分块主键。",
        "source_id": "资料源ID：所属资料源。",
        "version_id": "版本ID：所属资料版本。",
        "chunk_index": "分块序号：版本内的分块顺序。",
        "title": "分块标题：章节或对话窗口标题。",
        "source_type": "资料类型：分块所属资料类型。",
        "heading_path": "标题路径：Markdown 标题层级。",
        "locator": "定位符：原文行号范围。",
        "line_start": "起始行：分块原文开始行。",
        "line_end": "结束行：分块原文结束行。",
        "content": "正文：分块可检索文本。",
        "token_count": "Token数：预留的分块长度字段。",
        "metadata_json": "元数据：分块级 JSON 附加信息。",
        "search_vector": "全文检索向量：PostgreSQL 自动生成索引内容。",
        "created_at": "创建时间：分块创建时间。",
    },
    "citations": {
        "id": "引用ID：引用记录主键。",
        "source_id": "资料源ID：引用所属资料源。",
        "version_id": "版本ID：引用所属资料版本。",
        "chunk_id": "分块ID：引用对应内容分块。",
        "locator": "定位符：引用原文行号范围。",
        "line_start": "起始行：引用开始行。",
        "line_end": "结束行：引用结束行。",
        "quote": "引用片段：原文片段快照。",
        "metadata_json": "元数据：引用级 JSON 附加信息。",
        "created_at": "创建时间：引用创建时间。",
    },
    "ingest_jobs": {
        "id": "任务ID：摄入任务主键。",
        "source_type": "资料类型：本次摄入资料类型。",
        "input_path": "输入路径：本次摄入文件或目录。",
        "status": "状态：摄入任务执行状态。",
        "started_at": "开始时间：摄入开始时间。",
        "completed_at": "完成时间：摄入完成时间。",
        "summary_json": "结果摘要：摄入报告 JSON。",
        "error_message": "错误信息：任务级错误摘要。",
    },
    "alembic_version": {
        "version_num": "迁移版本：当前数据库结构版本。",
    },
}


def upgrade() -> None:
    for table_name, comment in TABLE_COMMENTS.items():
        _comment_on_table(table_name, comment)
    for table_name, columns in COLUMN_COMMENTS.items():
        for column_name, comment in columns.items():
            _comment_on_column(table_name, column_name, comment)


def downgrade() -> None:
    for table_name, comment in _previous_table_comments().items():
        _comment_on_table(table_name, comment)
    for table_name, columns in _previous_column_comments().items():
        for column_name, comment in columns.items():
            _comment_on_column(table_name, column_name, comment)


def _comment_on_table(table_name: str, comment: str | None) -> None:
    op.execute(f"COMMENT ON TABLE {table_name} IS {_sql_comment(comment)}")


def _comment_on_column(table_name: str, column_name: str, comment: str | None) -> None:
    op.execute(f"COMMENT ON COLUMN {table_name}.{column_name} IS {_sql_comment(comment)}")


def _sql_comment(comment: str | None) -> str:
    if comment is None:
        return "NULL"
    return "'" + comment.replace("'", "''") + "'"


def _previous_table_comments() -> dict[str, str]:
    return {
        "sources": "资料源表：保存一份长期资料的稳定身份，例如一篇文档或一段 AI 对话。",
        "source_versions": "资料版本表：保存同一资料源的每次内容版本和原始归档位置。",
        "chunks": "内容分块表：保存可检索、可引用的资料片段。",
        "citations": "引用表：保存分块对应的原文定位和引用片段。",
        "ingest_jobs": "摄入任务表：记录每次资料摄入的状态、摘要和错误信息。",
        "alembic_version": "数据库迁移版本表：由 Alembic 维护，用于记录当前数据库结构版本。",
    }


def _previous_column_comments() -> dict[str, dict[str, str]]:
    return {
        "sources": {
            "id": "资料源唯一 ID，内部主键。",
            "canonical_key": "规范化资料键，用于识别同一份长期资料源；通常由资料类型和路径组成，也可由调用方显式传入。",
            "title": "资料源标题，来自文档标题、对话标题或文件名。",
            "source_type": "资料类型；MVP 支持 ai_conversation 和 markdown_doc。",
            "origin_uri": "资料原始位置 URI 或文件路径，仅用于记录来源，不作为读回证据的依据。",
            "current_version_id": "当前最新资料版本 ID，用于快速定位最新版本。",
            "created_at": "资料源首次创建时间。",
            "updated_at": "资料源最近更新时间。",
        },
        "source_versions": {
            "id": "资料版本唯一 ID，内部主键。",
            "source_id": "所属资料源 ID，关联 sources.id。",
            "version_number": "同一资料源下的版本序号，从 1 开始递增。",
            "content_hash": "内容哈希，使用 SHA-256 标识本版本原始内容，用于重复导入检测。",
            "file_path": "摄入时的原始本地文件路径，仅作来源记录。",
            "raw_archive_path": "Raw Archive 原始归档文件路径；read_source 从这里读回证据。",
            "imported_at": "本资料版本导入时间。",
            "status": "资料版本状态，例如 imported。",
            "supersedes_version_id": "被当前版本替代的上一版本 ID，关联 source_versions.id。",
            "metadata_json": "资料版本元数据 JSON，例如原始文件名、对话参与者或解析格式。",
        },
        "chunks": {
            "id": "内容分块唯一 ID，内部主键。",
            "source_id": "所属资料源 ID，关联 sources.id。",
            "version_id": "所属资料版本 ID，关联 source_versions.id。",
            "chunk_index": "分块在同一资料版本内的顺序编号，从 0 开始。",
            "title": "分块标题，通常来自文档标题、章节标题或对话标题。",
            "source_type": "分块所属资料类型；MVP 支持 ai_conversation 和 markdown_doc。",
            "heading_path": "文档标题路径 JSON；AI 对话可为空数组。",
            "locator": "原文定位符，MVP 使用 line N-M 行号范围格式。",
            "line_start": "分块在原始资料中的起始行号，从 1 开始。",
            "line_end": "分块在原始资料中的结束行号，包含该行。",
            "content": "分块正文内容，用于搜索、引用和 Context Pack 证据。",
            "token_count": "预留 token 数字段；MVP 暂未精确计算。",
            "metadata_json": "分块元数据 JSON，例如 heading_path、对话角色、turn 范围等。",
            "search_vector": "PostgreSQL 自动生成的全文检索向量，由 title 和 content 计算，应用层不直接写入。",
            "created_at": "分块创建时间。",
        },
        "citations": {
            "id": "引用唯一 ID，内部主键。",
            "source_id": "引用所属资料源 ID，关联 sources.id。",
            "version_id": "引用所属资料版本 ID，关联 source_versions.id。",
            "chunk_id": "引用对应的内容分块 ID，关联 chunks.id。",
            "locator": "引用原文定位符，MVP 使用 line N-M 行号范围格式。",
            "line_start": "引用在原始资料中的起始行号，从 1 开始。",
            "line_end": "引用在原始资料中的结束行号，包含该行。",
            "quote": "引用片段文本快照，通常保存分块内容的前一部分。",
            "metadata_json": "引用元数据 JSON，例如标题路径、角色或 turn 信息。",
            "created_at": "引用记录创建时间。",
        },
        "ingest_jobs": {
            "id": "摄入任务唯一 ID，内部主键。",
            "source_type": "本次摄入的资料类型；MVP 支持 ai_conversation 和 markdown_doc。",
            "input_path": "本次摄入的输入路径，可以是单个本地文件或非递归目录。",
            "status": "摄入任务状态，例如 started、completed、skipped、failed 或 completed_with_errors。",
            "started_at": "摄入任务开始时间。",
            "completed_at": "摄入任务完成时间；未完成时为空。",
            "summary_json": "摄入结果摘要 JSON，包含 succeeded、skipped、failed 等报告字段。",
            "error_message": "摄入任务级错误摘要；单文件错误也会进入 summary_json。",
        },
        "alembic_version": {
            "version_num": "当前数据库结构迁移版本号，由 Alembic 自动维护。",
        },
    }
