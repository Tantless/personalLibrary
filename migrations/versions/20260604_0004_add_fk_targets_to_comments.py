"""add foreign key targets to comments

Revision ID: 20260604_0004
Revises: 20260604_0003
Create Date: 2026-06-04
"""

from alembic import op


revision = "20260604_0004"
down_revision = "20260604_0003"
branch_labels = None
depends_on = None


FK_COLUMN_COMMENTS = {
    "source_versions": {
        "source_id": "资料源ID：外键，关联 sources.id。",
        "supersedes_version_id": "上一版本ID：外键，关联 source_versions.id。",
    },
    "chunks": {
        "source_id": "资料源ID：外键，关联 sources.id。",
        "version_id": "版本ID：外键，关联 source_versions.id。",
    },
    "citations": {
        "source_id": "资料源ID：外键，关联 sources.id。",
        "version_id": "版本ID：外键，关联 source_versions.id。",
        "chunk_id": "分块ID：外键，关联 chunks.id。",
    },
}


PREVIOUS_FK_COLUMN_COMMENTS = {
    "source_versions": {
        "source_id": "资料源ID：所属资料源。",
        "supersedes_version_id": "上一版本ID：被当前版本替代的版本。",
    },
    "chunks": {
        "source_id": "资料源ID：所属资料源。",
        "version_id": "版本ID：所属资料版本。",
    },
    "citations": {
        "source_id": "资料源ID：引用所属资料源。",
        "version_id": "版本ID：引用所属资料版本。",
        "chunk_id": "分块ID：引用对应内容分块。",
    },
}


def upgrade() -> None:
    for table_name, columns in FK_COLUMN_COMMENTS.items():
        for column_name, comment in columns.items():
            _comment_on_column(table_name, column_name, comment)


def downgrade() -> None:
    for table_name, columns in PREVIOUS_FK_COLUMN_COMMENTS.items():
        for column_name, comment in columns.items():
            _comment_on_column(table_name, column_name, comment)


def _comment_on_column(table_name: str, column_name: str, comment: str) -> None:
    op.execute(f"COMMENT ON COLUMN {table_name}.{column_name} IS {_sql_comment(comment)}")


def _sql_comment(comment: str) -> str:
    return "'" + comment.replace("'", "''") + "'"
