from pathlib import Path, PurePosixPath, PureWindowsPath


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

    def version_root(self, *, knowledge_type: str, source_id: str, version_id: str) -> Path:
        return self.root / knowledge_type / source_id / version_id

    def write_asset(
        self,
        *,
        knowledge_type: str,
        source_id: str,
        version_id: str,
        artifact_key: str,
        original_path: Path | str,
        relative_path: str | None = None,
    ) -> Path | None:
        source_path = Path(original_path)
        destination = self._asset_destination(
            knowledge_type=knowledge_type,
            source_id=source_id,
            version_id=version_id,
            artifact_key=artifact_key,
            original_path=source_path,
            relative_path=relative_path,
        )
        if destination is None:
            return None
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source_path.read_bytes())
        return destination

    def _asset_destination(
        self,
        *,
        knowledge_type: str,
        source_id: str,
        version_id: str,
        artifact_key: str,
        original_path: Path,
        relative_path: str | None,
    ) -> Path | None:
        version_root = self.version_root(
            knowledge_type=knowledge_type,
            source_id=source_id,
            version_id=version_id,
        )
        if relative_path is not None:
            safe_relative_path = _safe_asset_relative_path(relative_path)
            if safe_relative_path is None:
                return None
            return version_root / safe_relative_path

        filename = f"{artifact_key}-{original_path.name or 'asset'}"
        return version_root / "assets" / filename


def _safe_asset_relative_path(value: str) -> Path | None:
    raw_value = value.strip()
    if not raw_value:
        return None

    posix_value = raw_value.replace("\\", "/")
    posix_path = PurePosixPath(posix_value)
    windows_path = PureWindowsPath(raw_value)
    if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        return None

    parts: list[str] = []
    for part in posix_path.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            return None
        parts.append(part)

    if not parts:
        return None
    return Path(*parts)
