"""initial schema

Revision ID: 20260604_0001
Revises:
Create Date: 2026-06-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260604_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("canonical_key", sa.String(length=512), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("origin_uri", sa.Text(), nullable=True),
        sa.Column("current_version_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("canonical_key", name="uq_sources_canonical_key"),
    )
    op.create_index("ix_sources_source_type", "sources", ["source_type"])

    op.create_table(
        "source_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("raw_archive_path", sa.Text(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("supersedes_version_id", sa.String(length=36), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], name="fk_source_versions_source_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["supersedes_version_id"],
            ["source_versions.id"],
            name="fk_source_versions_supersedes_version_id",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("source_id", "content_hash", name="uq_source_versions_source_hash"),
        sa.UniqueConstraint("source_id", "version_number", name="uq_source_versions_source_version_number"),
    )
    op.create_index("ix_source_versions_content_hash", "source_versions", ["content_hash"])
    op.create_index("ix_source_versions_source_id", "source_versions", ["source_id"])

    op.create_table(
        "chunks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column(
            "heading_path",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("locator", sa.String(length=128), nullable=False),
        sa.Column("line_start", sa.Integer(), nullable=False),
        sa.Column("line_end", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "setweight(to_tsvector('simple', coalesce(title, '')), 'A') || "
                "setweight(to_tsvector('simple', coalesce(content, '')), 'B')",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], name="fk_chunks_source_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["source_versions.id"], name="fk_chunks_version_id", ondelete="CASCADE"),
        sa.UniqueConstraint("version_id", "chunk_index", name="uq_chunks_version_chunk_index"),
    )
    op.create_index("ix_chunks_source_id", "chunks", ["source_id"])
    op.create_index("ix_chunks_version_id", "chunks", ["version_id"])
    op.create_index("ix_chunks_source_type", "chunks", ["source_type"])
    op.create_index("ix_chunks_search_vector", "chunks", ["search_vector"], postgresql_using="gin")

    op.create_table(
        "citations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("chunk_id", sa.String(length=36), nullable=False),
        sa.Column("locator", sa.String(length=128), nullable=False),
        sa.Column("line_start", sa.Integer(), nullable=False),
        sa.Column("line_end", sa.Integer(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["chunks.id"], name="fk_citations_chunk_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], name="fk_citations_source_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["source_versions.id"], name="fk_citations_version_id", ondelete="CASCADE"),
    )
    op.create_index("ix_citations_chunk_id", "citations", ["chunk_id"])
    op.create_index("ix_citations_source_version", "citations", ["source_id", "version_id"])

    op.create_table(
        "ingest_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("input_path", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "summary_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_ingest_jobs_source_type", "ingest_jobs", ["source_type"])
    op.create_index("ix_ingest_jobs_status", "ingest_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_ingest_jobs_status", table_name="ingest_jobs")
    op.drop_index("ix_ingest_jobs_source_type", table_name="ingest_jobs")
    op.drop_table("ingest_jobs")

    op.drop_index("ix_citations_source_version", table_name="citations")
    op.drop_index("ix_citations_chunk_id", table_name="citations")
    op.drop_table("citations")

    op.drop_index("ix_chunks_search_vector", table_name="chunks")
    op.drop_index("ix_chunks_source_type", table_name="chunks")
    op.drop_index("ix_chunks_version_id", table_name="chunks")
    op.drop_index("ix_chunks_source_id", table_name="chunks")
    op.drop_table("chunks")

    op.drop_index("ix_source_versions_source_id", table_name="source_versions")
    op.drop_index("ix_source_versions_content_hash", table_name="source_versions")
    op.drop_table("source_versions")

    op.drop_index("ix_sources_source_type", table_name="sources")
    op.drop_table("sources")

