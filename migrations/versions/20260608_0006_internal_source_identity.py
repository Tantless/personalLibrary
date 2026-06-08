"""use internal source identity paths

Revision ID: 20260608_0006
Revises: 20260605_0005
Create Date: 2026-06-08
"""

from alembic import op
import sqlalchemy as sa


revision = "20260608_0006"
down_revision = "20260605_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_key_counters",
        sa.Column("prefix", sa.String(length=8), nullable=False),
        sa.Column("next_number", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("prefix"),
    )

    op.execute(
        """
        insert into source_key_counters (prefix, next_number)
        select
            p.prefix,
            coalesce(max(substring(s.canonical_key from 2 for 5)::integer), 0) + 1
        from (values ('D'), ('A'), ('W'), ('G'), ('J'), ('E')) as p(prefix)
        left join sources s
          on s.canonical_key ~ ('^' || p.prefix || '[0-9]{5}$')
        group by p.prefix
        """
    )

    op.add_column("ingest_jobs", sa.Column("input_name", sa.Text(), nullable=True))
    op.execute(
        """
        update ingest_jobs
        set input_name = coalesce(
            nullif(regexp_replace(replace(input_path, E'\\\\', '/'), '^.*/', ''), ''),
            'input'
        )
        """
    )
    op.alter_column("ingest_jobs", "input_name", nullable=False)

    op.drop_column("sources", "origin_uri")
    op.drop_column("source_versions", "file_path")
    op.drop_column("ingest_jobs", "input_path")

    _comment_on_table("source_key_counters", "编号计数器：默认 canonical_key 前缀递增计数。")
    _comment_on_column("source_key_counters", "prefix", "前缀：默认 canonical_key 的字母前缀。")
    _comment_on_column("source_key_counters", "next_number", "下个编号：下一次分配使用的递增数字。")
    _comment_on_column("ingest_jobs", "input_name", "输入名称：本次摄入文件或目录的名称。")
    _comment_on_column("source_versions", "raw_archive_path", "内部源路径：Raw Archive 中的内部源文件位置。")


def downgrade() -> None:
    op.add_column("sources", sa.Column("origin_uri", sa.Text(), nullable=True))

    op.add_column("source_versions", sa.Column("file_path", sa.Text(), nullable=True))
    op.execute("update source_versions set file_path = raw_archive_path")
    op.alter_column("source_versions", "file_path", nullable=False)

    op.add_column("ingest_jobs", sa.Column("input_path", sa.Text(), nullable=True))
    op.execute("update ingest_jobs set input_path = input_name")
    op.alter_column("ingest_jobs", "input_path", nullable=False)
    op.drop_column("ingest_jobs", "input_name")

    op.drop_table("source_key_counters")

    _comment_on_column("sources", "origin_uri", "来源路径：摄入时的原始路径记录。")
    _comment_on_column("source_versions", "file_path", "文件路径：摄入时的本地文件路径。")
    _comment_on_column("ingest_jobs", "input_path", "输入路径：本次摄入文件或目录。")


def _comment_on_table(table_name: str, comment: str) -> None:
    op.execute(f"COMMENT ON TABLE {table_name} IS {_sql_comment(comment)}")


def _comment_on_column(table_name: str, column_name: str, comment: str) -> None:
    op.execute(f"COMMENT ON COLUMN {table_name}.{column_name} IS {_sql_comment(comment)}")


def _sql_comment(comment: str) -> str:
    return "'" + comment.replace("'", "''") + "'"
