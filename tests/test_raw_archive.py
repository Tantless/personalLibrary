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


def test_raw_archive_writer_preserves_safe_relative_asset_path(tmp_path) -> None:
    writer = RawArchiveWriter(tmp_path)
    source_asset = tmp_path / "source" / "assets" / "diagram.png"
    source_asset.parent.mkdir(parents=True)
    source_asset.write_bytes(b"diagram")

    written = writer.write_asset(
        knowledge_type="document",
        source_id="src_1",
        version_id="ver_1",
        artifact_key="img_001",
        original_path=source_asset,
        relative_path="assets/diagram.png",
    )

    assert written == tmp_path / "document" / "src_1" / "ver_1" / "assets" / "diagram.png"
    assert written.read_bytes() == b"diagram"


def test_raw_archive_writer_rejects_unsafe_asset_relative_paths(tmp_path) -> None:
    writer = RawArchiveWriter(tmp_path)
    source_asset = tmp_path / "outside.png"
    source_asset.write_bytes(b"outside")

    for unsafe_path in ["../outside.png", "/tmp/outside.png", "C:/outside.png", r"C:\outside.png"]:
        written = writer.write_asset(
            knowledge_type="document",
            source_id="src_1",
            version_id="ver_1",
            artifact_key="img_001",
            original_path=source_asset,
            relative_path=unsafe_path,
        )

        assert written is None

    assert not (tmp_path / "document" / "src_1" / "outside.png").exists()
