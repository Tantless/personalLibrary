"""add markdown table and image artifacts

Revision ID: 20260610_0008
Revises: 20260609_0007
Create Date: 2026-06-10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260610_0008"
down_revision = "20260609_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "table_artifacts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("artifact_key", sa.String(length=64), nullable=False),
        sa.Column("locator", sa.String(length=128), nullable=False),
        sa.Column("line_start", sa.Integer(), nullable=False),
        sa.Column("line_end", sa.Integer(), nullable=False),
        sa.Column(
            "heading_path",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "columns",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "rows",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("normalized_markdown", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], name="fk_table_artifacts_source_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["version_id"], ["source_versions.id"], name="fk_table_artifacts_version_id", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("version_id", "artifact_key", name="uq_table_artifacts_version_key"),
    )
    op.create_index("ix_table_artifacts_source_id", "table_artifacts", ["source_id"])
    op.create_index("ix_table_artifacts_version_id", "table_artifacts", ["version_id"])

    op.create_table(
        "image_artifacts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("artifact_key", sa.String(length=64), nullable=False),
        sa.Column("locator", sa.String(length=128), nullable=False),
        sa.Column("line_start", sa.Integer(), nullable=False),
        sa.Column("line_end", sa.Integer(), nullable=False),
        sa.Column(
            "heading_path",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("original_uri", sa.Text(), nullable=False),
        sa.Column("asset_path", sa.Text(), nullable=True),
        sa.Column("alt_text", sa.Text(), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("nearby_text", sa.Text(), nullable=True),
        sa.Column("ocr_text", sa.Text(), nullable=True),
        sa.Column("vision_summary", sa.Text(), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], name="fk_image_artifacts_source_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["version_id"], ["source_versions.id"], name="fk_image_artifacts_version_id", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("version_id", "artifact_key", name="uq_image_artifacts_version_key"),
    )
    op.create_index("ix_image_artifacts_source_id", "image_artifacts", ["source_id"])
    op.create_index("ix_image_artifacts_version_id", "image_artifacts", ["version_id"])

    for table_name, comment in _table_comments().items():
        _comment_on_table(table_name, comment)
    for table_name, columns in _column_comments().items():
        for column_name, comment in columns.items():
            _comment_on_column(table_name, column_name, comment)


def downgrade() -> None:
    op.drop_index("ix_image_artifacts_version_id", table_name="image_artifacts")
    op.drop_index("ix_image_artifacts_source_id", table_name="image_artifacts")
    op.drop_table("image_artifacts")

    op.drop_index("ix_table_artifacts_version_id", table_name="table_artifacts")
    op.drop_index("ix_table_artifacts_source_id", table_name="table_artifacts")
    op.drop_table("table_artifacts")


def _table_comments() -> dict[str, str]:
    return {
        "table_artifacts": "表格对象表：保存 Markdown 表格结构。",
        "image_artifacts": "图片对象表：保存 Markdown 图片引用。",
    }


def _column_comments() -> dict[str, dict[str, str]]:
    shared = {
        "id": "对象ID：对象主键。",
        "source_id": "资料源ID：外键，关联 sources.id。",
        "version_id": "版本ID：外键，关联 source_versions.id。",
        "artifact_key": "对象键：版本内可读对象编号。",
        "locator": "定位符：原文行号范围。",
        "line_start": "起始行：对象原文开始行。",
        "line_end": "结束行：对象原文结束行。",
        "heading_path": "标题路径：Markdown 标题层级。",
        "metadata_json": "元数据：对象级 JSON 附加信息。",
        "created_at": "创建时间：对象创建时间。",
    }
    return {
        "table_artifacts": {
            **shared,
            "columns": "列名：表格列名数组。",
            "rows": "行数据：表格行 JSON 数组。",
            "normalized_markdown": "规范表格：标准化 Markdown 表格。",
            "summary": "摘要：表格增强摘要。",
        },
        "image_artifacts": {
            **shared,
            "original_uri": "原始URI：Markdown 图片原始路径。",
            "asset_path": "资产路径：Raw Archive 图片副本位置。",
            "alt_text": "替代文本：Markdown 图片 alt 文本。",
            "caption": "说明文字：图片附近说明。",
            "nearby_text": "邻近文本：图片周边文本。",
            "ocr_text": "OCR文本：图片文字识别结果。",
            "vision_summary": "视觉摘要：图片视觉理解结果。",
        },
    }


def _comment_on_table(table_name: str, comment: str) -> None:
    op.execute(f"COMMENT ON TABLE {table_name} IS {_sql_comment(comment)}")


def _comment_on_column(table_name: str, column_name: str, comment: str) -> None:
    op.execute(f"COMMENT ON COLUMN {table_name}.{column_name} IS {_sql_comment(comment)}")


def _sql_comment(comment: str) -> str:
    return "'" + comment.replace("'", "''") + "'"
