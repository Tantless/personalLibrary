from pkcs.storage.raw_archive import RawArchiveWriter


def test_raw_archive_writer_writes_by_knowledge_type_source_and_version(tmp_path) -> None:
    writer = RawArchiveWriter(tmp_path)

    written = writer.write_bytes(
        knowledge_type="document",
        source_id="src_1",
        version_id="ver_1",
        original_path="example.md",
        content=b"# Example\n",
    )

    assert written == tmp_path / "document" / "src_1" / "ver_1" / "example.md"
    assert written.read_bytes() == b"# Example\n"

