from uuid import uuid4

from pkcs.db.repositories import ChunkRepository, CitationRepository, IngestJobRepository, SourceRepository
from pkcs.source_metadata import (
    KNOWLEDGE_TYPE_DOCUMENT,
    NORMALIZED_FORMAT_MARKDOWN,
    SOURCE_FORMAT_MD,
)


def test_repository_crud_round_trip(db_session) -> None:
    suffix = uuid4().hex
    sources = SourceRepository(db_session)
    chunks = ChunkRepository(db_session)
    citations = CitationRepository(db_session)
    ingest_jobs = IngestJobRepository(db_session)

    source = sources.create_source(
        canonical_key=f"document:test-{suffix}",
        title="Repository Test",
        knowledge_type_code=KNOWLEDGE_TYPE_DOCUMENT,
        origin_uri="tests/fixtures/repository-test.md",
    )
    version = sources.create_version(
        source=source,
        content_hash=f"hash-{suffix}",
        source_format_code=SOURCE_FORMAT_MD,
        normalized_format_code=NORMALIZED_FORMAT_MARKDOWN,
        file_path="tests/fixtures/repository-test.md",
        raw_archive_path=f"data/raw/document/{source.id}/version/repository-test.md",
    )
    chunk = chunks.create_chunk(
        source_id=source.id,
        version_id=version.id,
        chunk_index=0,
        title="Repository Test",
        source_format_code=SOURCE_FORMAT_MD,
        normalized_format_code=NORMALIZED_FORMAT_MARKDOWN,
        knowledge_type_code=KNOWLEDGE_TYPE_DOCUMENT,
        locator="line 1-2",
        line_start=1,
        line_end=2,
        content="Repository content",
        heading_path=["Repository Test"],
    )
    citation = citations.create_citation(
        source_id=source.id,
        version_id=version.id,
        chunk_id=chunk.id,
        locator=chunk.locator,
        line_start=chunk.line_start,
        line_end=chunk.line_end,
        quote=chunk.content,
    )
    job = ingest_jobs.create_job(
        knowledge_type_code=KNOWLEDGE_TYPE_DOCUMENT,
        input_path="tests/fixtures/repository-test.md",
        summary_json={"succeeded": [source.id], "skipped": [], "failed": []},
    )
    db_session.commit()

    loaded_source = sources.get_by_canonical_key(f"document:test-{suffix}")
    loaded_chunk = chunks.get(chunk.id)

    assert loaded_source is not None
    assert loaded_source.current_version_id == version.id
    assert loaded_chunk is not None
    assert loaded_chunk.heading_path == ["Repository Test"]
    assert citation.locator == "line 1-2"
    assert job.summary_json["succeeded"] == [source.id]
