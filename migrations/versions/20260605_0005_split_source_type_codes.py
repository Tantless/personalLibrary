"""split source type into metadata codes

Revision ID: 20260605_0005
Revises: 20260604_0004
Create Date: 2026-06-05
"""

from alembic import op
import sqlalchemy as sa


revision = "20260605_0005"
down_revision = "20260604_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("knowledge_type_code", sa.Integer(), nullable=True))
    op.add_column("source_versions", sa.Column("source_format_code", sa.Integer(), nullable=True))
    op.add_column("source_versions", sa.Column("normalized_format_code", sa.Integer(), nullable=True))
    op.add_column("chunks", sa.Column("source_format_code", sa.Integer(), nullable=True))
    op.add_column("chunks", sa.Column("normalized_format_code", sa.Integer(), nullable=True))
    op.add_column("chunks", sa.Column("knowledge_type_code", sa.Integer(), nullable=True))
    op.add_column("ingest_jobs", sa.Column("knowledge_type_code", sa.Integer(), nullable=True))

    op.execute(
        """
        update sources
        set knowledge_type_code = case
            when source_type = 'ai_conversation' then 2
            else 1
        end
        """
    )
    op.execute(
        """
        update source_versions
        set
            source_format_code = case
                when lower(file_path) like '%.jsonl' then 3
                when lower(file_path) like '%.txt' then 2
                else 1
            end,
            normalized_format_code = case
                when lower(file_path) like '%.md' then 1
                else 2
            end
        """
    )
    op.execute(
        """
        update chunks c
        set
            source_format_code = v.source_format_code,
            normalized_format_code = v.normalized_format_code,
            knowledge_type_code = case
                when c.source_type = 'ai_conversation' then 2
                else 1
            end
        from source_versions v
        where c.version_id = v.id
        """
    )
    op.execute(
        """
        update ingest_jobs
        set knowledge_type_code = case
            when source_type = 'ai_conversation' then 2
            else 1
        end
        """
    )

    op.alter_column("sources", "knowledge_type_code", nullable=False)
    op.alter_column("source_versions", "source_format_code", nullable=False)
    op.alter_column("source_versions", "normalized_format_code", nullable=False)
    op.alter_column("chunks", "source_format_code", nullable=False)
    op.alter_column("chunks", "normalized_format_code", nullable=False)
    op.alter_column("chunks", "knowledge_type_code", nullable=False)
    op.alter_column("ingest_jobs", "knowledge_type_code", nullable=False)

    op.drop_index("ix_sources_source_type", table_name="sources")
    op.drop_index("ix_chunks_source_type", table_name="chunks")
    op.drop_index("ix_ingest_jobs_source_type", table_name="ingest_jobs")
    op.drop_column("sources", "source_type")
    op.drop_column("chunks", "source_type")
    op.drop_column("ingest_jobs", "source_type")

    op.create_index("ix_sources_knowledge_type_code", "sources", ["knowledge_type_code"])
    op.create_index("ix_source_versions_source_format_code", "source_versions", ["source_format_code"])
    op.create_index("ix_chunks_source_format_code", "chunks", ["source_format_code"])
    op.create_index("ix_chunks_knowledge_type_code", "chunks", ["knowledge_type_code"])
    op.create_index("ix_ingest_jobs_knowledge_type_code", "ingest_jobs", ["knowledge_type_code"])

    for table_name, columns in _column_comments().items():
        for column_name, comment in columns.items():
            _comment_on_column(table_name, column_name, comment)


def downgrade() -> None:
    op.add_column("sources", sa.Column("source_type", sa.String(length=64), nullable=True))
    op.add_column("chunks", sa.Column("source_type", sa.String(length=64), nullable=True))
    op.add_column("ingest_jobs", sa.Column("source_type", sa.String(length=64), nullable=True))

    op.execute(
        """
        update sources
        set source_type = case
            when knowledge_type_code = 2 then 'ai_conversation'
            else 'markdown_doc'
        end
        """
    )
    op.execute(
        """
        update chunks
        set source_type = case
            when knowledge_type_code = 2 then 'ai_conversation'
            else 'markdown_doc'
        end
        """
    )
    op.execute(
        """
        update ingest_jobs
        set source_type = case
            when knowledge_type_code = 2 then 'ai_conversation'
            else 'markdown_doc'
        end
        """
    )

    op.alter_column("sources", "source_type", nullable=False)
    op.alter_column("chunks", "source_type", nullable=False)
    op.alter_column("ingest_jobs", "source_type", nullable=False)

    op.drop_index("ix_ingest_jobs_knowledge_type_code", table_name="ingest_jobs")
    op.drop_index("ix_chunks_knowledge_type_code", table_name="chunks")
    op.drop_index("ix_chunks_source_format_code", table_name="chunks")
    op.drop_index("ix_source_versions_source_format_code", table_name="source_versions")
    op.drop_index("ix_sources_knowledge_type_code", table_name="sources")

    op.drop_column("ingest_jobs", "knowledge_type_code")
    op.drop_column("chunks", "knowledge_type_code")
    op.drop_column("chunks", "normalized_format_code")
    op.drop_column("chunks", "source_format_code")
    op.drop_column("source_versions", "normalized_format_code")
    op.drop_column("source_versions", "source_format_code")
    op.drop_column("sources", "knowledge_type_code")

    op.create_index("ix_sources_source_type", "sources", ["source_type"])
    op.create_index("ix_chunks_source_type", "chunks", ["source_type"])
    op.create_index("ix_ingest_jobs_source_type", "ingest_jobs", ["source_type"])

    _comment_on_column("sources", "source_type", "资料类型：区分 AI 对话和文档。")
    _comment_on_column("chunks", "source_type", "资料类型：分块所属资料类型。")
    _comment_on_column("ingest_jobs", "source_type", "资料类型：本次摄入资料类型。")


def _column_comments() -> dict[str, dict[str, str]]:
    return {
        "sources": {
            "knowledge_type_code": _knowledge_type_comment(),
        },
        "source_versions": {
            "source_format_code": "原始格式：1:md，2:txt，3:jsonl；4:pdf，5:docx，6:xlsx预留。",
            "normalized_format_code": "规范格式：1:markdown，2:plain_text，3:table_markdown预留。",
        },
        "chunks": {
            "source_format_code": "原始格式：1:md，2:txt，3:jsonl；4:pdf，5:docx，6:xlsx预留。",
            "normalized_format_code": "规范格式：1:markdown，2:plain_text，3:table_markdown预留。",
            "knowledge_type_code": _knowledge_type_comment(),
        },
        "ingest_jobs": {
            "knowledge_type_code": _knowledge_type_comment(),
        },
    }


def _knowledge_type_comment() -> str:
    return "知识类型：1:document，2:ai_conversation，3:wiki_article预留，4:game_guide预留，5:diary预留，6:email预留。"


def _comment_on_column(table_name: str, column_name: str, comment: str) -> None:
    op.execute(f"COMMENT ON COLUMN {table_name}.{column_name} IS {_sql_comment(comment)}")


def _sql_comment(comment: str) -> str:
    return "'" + comment.replace("'", "''") + "'"
