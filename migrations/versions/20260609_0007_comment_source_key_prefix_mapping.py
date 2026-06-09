"""comment source key prefix mappings

Revision ID: 20260609_0007
Revises: 20260608_0006
Create Date: 2026-06-09
"""

from alembic import op


revision = "20260609_0007"
down_revision = "20260608_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _comment_on_column(
        "source_key_counters",
        "prefix",
        "前缀：默认 canonical_key 字母前缀，D:document，A:ai_conversation，W:wiki_article，G:game_guide，J:diary，E:email。",
    )


def downgrade() -> None:
    _comment_on_column("source_key_counters", "prefix", "前缀：默认 canonical_key 的字母前缀。")


def _comment_on_column(table_name: str, column_name: str, comment: str) -> None:
    op.execute(f"COMMENT ON COLUMN {table_name}.{column_name} IS {_sql_comment(comment)}")


def _sql_comment(comment: str) -> str:
    return "'" + comment.replace("'", "''") + "'"
