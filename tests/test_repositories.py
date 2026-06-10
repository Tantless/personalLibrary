from uuid import uuid4

from pkcs.db.repositories import (
    ChunkRepository,
    CitationRepository,
    ImageArtifactRepository,
    IngestJobRepository,
    SourceKeyCounterRepository,
    SourceRepository,
    TableArtifactRepository,
)
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
    tables = TableArtifactRepository(db_session)
    images = ImageArtifactRepository(db_session)
    ingest_jobs = IngestJobRepository(db_session)
    source_keys = SourceKeyCounterRepository(db_session)
    generated_key = source_keys.allocate("D")

    source = sources.create_source(
        canonical_key=generated_key,
        title="Repository Test",
        knowledge_type_code=KNOWLEDGE_TYPE_DOCUMENT,
    )
    version = sources.create_version(
        source=source,
        content_hash=f"hash-{suffix}",
        source_format_code=SOURCE_FORMAT_MD,
        normalized_format_code=NORMALIZED_FORMAT_MARKDOWN,
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
    table = tables.create_table_artifact(
        source_id=source.id,
        version_id=version.id,
        artifact_key="tbl_001",
        locator="line 3-5",
        line_start=3,
        line_end=5,
        heading_path=["Repository Test"],
        columns=["Name", "Role"],
        rows=[{"Name": "Retriever", "Role": "Find chunks"}],
        normalized_markdown="| Name | Role |\n| --- | --- |\n| Retriever | Find chunks |",
        summary="Repository table artifact",
    )
    image = images.create_image_artifact(
        source_id=source.id,
        version_id=version.id,
        artifact_key="img_001",
        locator="line 7-7",
        line_start=7,
        line_end=7,
        heading_path=["Repository Test"],
        original_uri="images/rag.png",
        asset_path="data/raw/document/source/version/assets/img_001-rag.png",
        alt_text="RAG architecture",
    )
    job = ingest_jobs.create_job(
        knowledge_type_code=KNOWLEDGE_TYPE_DOCUMENT,
        input_name="repository-test.md",
        summary_json={"succeeded": [source.id], "skipped": [], "failed": []},
    )
    db_session.commit()

    loaded_source = sources.get_by_canonical_key(generated_key)
    loaded_chunk = chunks.get(chunk.id)
    loaded_table = tables.get(table.id)
    loaded_image = images.get(image.id)

    assert loaded_source is not None
    assert generated_key.startswith("D")
    assert len(generated_key) == 6
    assert generated_key[1:].isdigit()
    assert loaded_source.current_version_id == version.id
    assert loaded_chunk is not None
    assert loaded_chunk.heading_path == ["Repository Test"]
    assert citation.locator == "line 1-2"
    assert loaded_table is not None
    assert loaded_table.column_names == ["Name", "Role"]
    assert loaded_table.rows[0]["Name"] == "Retriever"
    assert loaded_image is not None
    assert loaded_image.alt_text == "RAG architecture"
    assert job.summary_json["succeeded"] == [source.id]
