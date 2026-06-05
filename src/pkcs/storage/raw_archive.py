from pathlib import Path


class RawArchiveWriter:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def write_bytes(
        self,
        *,
        knowledge_type: str,
        source_id: str,
        version_id: str,
        original_path: Path | str,
        content: bytes,
    ) -> Path:
        filename = Path(original_path).name or "source.bin"
        destination = self.root / knowledge_type / source_id / version_id / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        return destination
