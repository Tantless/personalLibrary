from sqlalchemy import inspect, text


def test_initial_schema_and_indexes(db_session) -> None:
    inspector = inspect(db_session.bind)

    assert {"sources", "source_versions", "chunks", "citations", "ingest_jobs"}.issubset(
        set(inspector.get_table_names())
    )

    source_indexes = {index["name"] for index in inspector.get_indexes("sources")}
    version_indexes = {index["name"] for index in inspector.get_indexes("source_versions")}
    chunk_indexes = {index["name"] for index in inspector.get_indexes("chunks")}

    assert "ix_sources_source_type" in source_indexes
    assert "ix_source_versions_content_hash" in version_indexes
    assert "ix_chunks_search_vector" in chunk_indexes


def test_schema_tables_and_columns_have_concise_chinese_comments(db_session) -> None:
    expected_tables = {"sources", "source_versions", "chunks", "citations", "ingest_jobs", "alembic_version"}

    table_comments = db_session.execute(
        text(
            """
            select c.relname as table_name, obj_description(c.oid, 'pg_class') as comment
            from pg_class c
            join pg_namespace n on n.oid = c.relnamespace
            where n.nspname = 'public'
              and c.relkind = 'r'
              and c.relname in ('sources', 'source_versions', 'chunks', 'citations', 'ingest_jobs', 'alembic_version')
            """
        )
    ).mappings().all()
    column_comments = db_session.execute(
        text(
            """
            select c.relname as table_name, a.attname as column_name, col_description(c.oid, a.attnum) as comment
            from pg_class c
            join pg_namespace n on n.oid = c.relnamespace
            join pg_attribute a on a.attrelid = c.oid
            where n.nspname = 'public'
              and c.relkind = 'r'
              and c.relname in ('sources', 'source_versions', 'chunks', 'citations', 'ingest_jobs', 'alembic_version')
              and a.attnum > 0
              and not a.attisdropped
            order by c.relname, a.attnum
            """
        )
    ).mappings().all()

    missing_table_comments = [
        row["table_name"] for row in table_comments if not (row["comment"] or "").strip()
    ]
    missing_column_comments = [
        (row["table_name"], row["column_name"]) for row in column_comments if not (row["comment"] or "").strip()
    ]
    malformed_table_comments = [
        (row["table_name"], row["comment"]) for row in table_comments if not _is_name_explanation_comment(row["comment"])
    ]
    malformed_column_comments = [
        (row["table_name"], row["column_name"], row["comment"])
        for row in column_comments
        if not _is_name_explanation_comment(row["comment"])
    ]

    assert {row["table_name"] for row in table_comments} == expected_tables
    assert not missing_table_comments
    assert not missing_column_comments
    assert not malformed_table_comments
    assert not malformed_column_comments


def test_foreign_key_column_comments_include_referenced_table_and_column(db_session) -> None:
    foreign_keys = db_session.execute(
        text(
            """
            select
                tc.table_name,
                kcu.column_name,
                ccu.table_name as foreign_table_name,
                ccu.column_name as foreign_column_name
            from information_schema.table_constraints tc
            join information_schema.key_column_usage kcu
              on tc.constraint_name = kcu.constraint_name
             and tc.table_schema = kcu.table_schema
            join information_schema.constraint_column_usage ccu
              on ccu.constraint_name = tc.constraint_name
             and ccu.table_schema = tc.table_schema
            where tc.constraint_type = 'FOREIGN KEY'
              and tc.table_schema = 'public'
            order by tc.table_name, kcu.column_name
            """
        )
    ).mappings().all()
    comments = db_session.execute(
        text(
            """
            select c.relname as table_name, a.attname as column_name, col_description(c.oid, a.attnum) as comment
            from pg_class c
            join pg_namespace n on n.oid = c.relnamespace
            join pg_attribute a on a.attrelid = c.oid
            where n.nspname = 'public'
              and c.relkind = 'r'
              and a.attnum > 0
              and not a.attisdropped
            """
        )
    ).mappings().all()
    comments_by_column = {(row["table_name"], row["column_name"]): row["comment"] or "" for row in comments}

    missing_references = []
    for row in foreign_keys:
        comment = comments_by_column[(row["table_name"], row["column_name"])]
        expected_reference = f"关联 {row['foreign_table_name']}.{row['foreign_column_name']}"
        if "外键" not in comment or expected_reference not in comment:
            missing_references.append((row["table_name"], row["column_name"], comment, expected_reference))

    assert len(foreign_keys) == 7
    assert not missing_references


def _is_name_explanation_comment(comment: str | None) -> bool:
    if comment is None or "：" not in comment or len(comment) > 60:
        return False
    name, explanation = comment.split("：", 1)
    return bool(name.strip()) and bool(explanation.strip())


def test_chunks_search_vector_is_database_generated(db_session) -> None:
    source_id = "schema-source"
    version_id = "schema-version"
    chunk_id = "schema-chunk"

    db_session.execute(
        text(
            """
            insert into sources (id, canonical_key, title, source_type)
            values (:source_id, :canonical_key, :title, :source_type)
            on conflict (canonical_key) do nothing
            """
        ),
        {
            "source_id": source_id,
            "canonical_key": "test:schema",
            "title": "Schema Test",
            "source_type": "markdown_doc",
        },
    )
    db_session.execute(
        text(
            """
            insert into source_versions
                (id, source_id, version_number, content_hash, file_path, raw_archive_path, status)
            values
                (:version_id, :source_id, 1, :content_hash, :file_path, :raw_archive_path, 'imported')
            on conflict (source_id, content_hash) do nothing
            """
        ),
        {
            "version_id": version_id,
            "source_id": source_id,
            "content_hash": "schema-hash",
            "file_path": "tests/fixtures/schema.md",
            "raw_archive_path": "data/raw/markdown_doc/schema-source/schema-version/schema.md",
        },
    )
    db_session.execute(
        text(
            """
            insert into chunks
                (id, source_id, version_id, chunk_index, title, source_type, locator, line_start, line_end, content)
            values
                (:chunk_id, :source_id, :version_id, 0, :title, :source_type, 'line 1-1', 1, 1, :content)
            on conflict (version_id, chunk_index) do nothing
            """
        ),
        {
            "chunk_id": chunk_id,
            "source_id": source_id,
            "version_id": version_id,
            "title": "Context Pack",
            "source_type": "markdown_doc",
            "content": "Context Pack evidence citations",
        },
    )
    db_session.commit()

    generated = db_session.scalar(text("select search_vector::text from chunks where id = :chunk_id"), {"chunk_id": chunk_id})

    assert generated is not None
    assert "context" in generated
