import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pkcs.ingest.models import (
    KNOWLEDGE_TYPE_NAME_AI_CONVERSATION,
    KNOWLEDGE_TYPE_NAME_DOCUMENT,
    ParsedArtifactBinding,
    ParsedChunk,
    ParsedImageArtifact,
    ParsedMarkdownBlock,
    ParsedMarkdownBlockEdge,
    ParsedMarkdownBlockGraph,
    ParsedSource,
    ParsedTableArtifact,
)


class IngestParseError(ValueError):
    pass


@dataclass(frozen=True)
class _Section:
    title: str
    heading_path: list[str]
    line_start: int
    lines: list[str]


@dataclass(frozen=True)
class _ChunkBlockEntry:
    block: ParsedMarkdownBlock
    rendered_text: str
    linked_artifact: dict[str, Any] | None = None
    ownership: str = "primary"


@dataclass(frozen=True)
class _Turn:
    role: str
    text: str
    line_start: int
    line_end: int


@dataclass(frozen=True)
class _TurnWindow:
    turns: list[_Turn]
    turn_start: int
    turn_end: int


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_SPEAKER_RE = re.compile(r"^([A-Za-z][A-Za-z0-9 _.-]{0,40}):\s*(.*)$")
_IMAGE_LINE_RE = re.compile(r"^\s*!\[([^\]]*)\]\((.+?)\)\s*$")
_TABLE_SEPARATOR_CELL_RE = re.compile(r"^:?-{3,}:?$")


def parse_source_file(
    *,
    path: Path,
    knowledge_type: str,
    content_bytes: bytes,
    max_chars: int,
    overlap_lines: int,
) -> ParsedSource:
    text = _decode_utf8(content_bytes, path)
    if knowledge_type == KNOWLEDGE_TYPE_NAME_DOCUMENT:
        return _parse_document_source(path=path, text=text, max_chars=max_chars, overlap_lines=overlap_lines)
    if knowledge_type == KNOWLEDGE_TYPE_NAME_AI_CONVERSATION:
        if path.suffix.lower() == ".jsonl":
            return _parse_ai_jsonl(path=path, text=text, max_chars=max_chars)
        return _parse_ai_transcript(path=path, text=text, max_chars=max_chars)
    raise IngestParseError(f"unsupported knowledge_type: {knowledge_type}")


def _decode_utf8(content_bytes: bytes, path: Path) -> str:
    try:
        return content_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IngestParseError(f"{path} is not valid UTF-8 text") from exc


def _parse_document_source(*, path: Path, text: str, max_chars: int, overlap_lines: int) -> ParsedSource:
    lines = text.splitlines()
    if not any(line.strip() for line in lines):
        raise IngestParseError("document is empty")

    if path.suffix.lower() == ".txt":
        title = _safe_title(_first_nonblank(lines) or path.stem)
        sections = [_Section(title=title, heading_path=[], line_start=1, lines=lines)]
        chunks: list[ParsedChunk] = []
        for section in sections:
            chunks.extend(
                _chunks_from_section(
                    section=section,
                    knowledge_type=KNOWLEDGE_TYPE_NAME_DOCUMENT,
                    max_chars=max_chars,
                    overlap_lines=overlap_lines,
                )
            )
        table_artifacts: list[ParsedTableArtifact] = []
        image_artifacts: list[ParsedImageArtifact] = []
    else:
        title, sections = _markdown_sections(path=path, lines=lines)
        chunks, table_artifacts, image_artifacts, markdown_block_graph = _chunks_from_markdown_sections(
            title=title,
            sections=sections,
            max_chars=max_chars,
            overlap_lines=overlap_lines,
        )

    if not chunks:
        raise IngestParseError("document produced no chunks")

    return ParsedSource(
        title=_safe_title(title),
        knowledge_type=KNOWLEDGE_TYPE_NAME_DOCUMENT,
        metadata_json={
            "format": path.suffix.lower().lstrip(".") or "text",
            "line_count": len(lines),
        },
        chunks=chunks,
        table_artifacts=table_artifacts,
        image_artifacts=image_artifacts,
        markdown_block_graph=markdown_block_graph if path.suffix.lower() != ".txt" else None,
    )


def _markdown_sections(*, path: Path, lines: list[str]) -> tuple[str, list[_Section]]:
    sections: list[_Section] = []
    heading_stack: list[str] = []
    current_start = 1
    current_title = _safe_title(path.stem)
    current_heading_path: list[str] = []
    document_title: str | None = None

    for line_no, line in enumerate(lines, start=1):
        match = _HEADING_RE.match(line)
        if not match:
            continue

        if line_no > current_start:
            sections.append(
                _Section(
                    title=current_title,
                    heading_path=current_heading_path,
                    line_start=current_start,
                    lines=lines[current_start - 1 : line_no - 1],
                )
            )

        level = len(match.group(1))
        heading_text = _safe_title(match.group(2).strip())
        heading_stack = heading_stack[: level - 1] + [heading_text]
        current_start = line_no
        current_title = heading_text
        current_heading_path = heading_stack.copy()
        document_title = document_title or heading_text

    if current_start <= len(lines):
        sections.append(
            _Section(
                title=current_title,
                heading_path=current_heading_path,
                line_start=current_start,
                lines=lines[current_start - 1 :],
            )
        )

    if not sections:
        sections.append(_Section(title=_safe_title(path.stem), heading_path=[], line_start=1, lines=lines))

    return _safe_title(document_title or path.stem), sections


def _chunks_from_section(
    *,
    section: _Section,
    knowledge_type: str,
    max_chars: int,
    overlap_lines: int,
) -> list[ParsedChunk]:
    chunks: list[ParsedChunk] = []
    for line_start, chunk_lines in _split_lines(section.line_start, section.lines, max_chars, overlap_lines):
        content = "\n".join(chunk_lines).strip()
        if not content:
            continue
        line_end = line_start + len(chunk_lines) - 1
        chunks.append(
            ParsedChunk(
                title=section.title,
                content=content,
                line_start=line_start,
                line_end=line_end,
                heading_path=section.heading_path,
                metadata_json={
                    "knowledge_type": knowledge_type,
                    "heading_path": section.heading_path,
                },
            )
        )
    return chunks


def _chunks_from_markdown_sections(
    *,
    title: str,
    sections: list[_Section],
    max_chars: int,
    overlap_lines: int,
) -> tuple[list[ParsedChunk], list[ParsedTableArtifact], list[ParsedImageArtifact], ParsedMarkdownBlockGraph]:
    block_graph = _build_markdown_block_graph(title=title, sections=sections)
    table_artifacts, image_artifacts, artifact_bindings, artifact_by_block_id = _artifacts_from_block_graph(
        block_graph
    )
    block_graph = _block_graph_with_artifact_bindings(block_graph, artifact_bindings)
    narrative_chunks: list[ParsedChunk] = []

    for section_index, section in enumerate(sections):
        section_blocks = [
            block
            for block in block_graph.blocks
            if block.metadata_json.get("section_index") == section_index
        ]
        entries = _rendered_block_entries(blocks=section_blocks, artifact_by_block_id=artifact_by_block_id)
        narrative_chunks.extend(
            _narrative_chunks_from_blocks(
                section_title=section.title,
                section_heading_path=section.heading_path,
                entries=entries,
                start_index=len(narrative_chunks),
                max_chars=max_chars,
                overlap_lines=overlap_lines,
            )
        )

    parent_chunk_by_artifact_key: dict[str, str] = {}
    for chunk in narrative_chunks:
        chunk_key = chunk.chunk_key or ""
        for artifact_ref in chunk.metadata_json.get("linked_artifacts", []):
            if artifact_ref.get("role") != "primary_reference":
                continue
            artifact_key = artifact_ref.get("artifact_key")
            if artifact_key and artifact_key not in parent_chunk_by_artifact_key:
                parent_chunk_by_artifact_key[artifact_key] = chunk_key
    for chunk in narrative_chunks:
        chunk_key = chunk.chunk_key or ""
        for artifact_ref in chunk.metadata_json.get("linked_artifacts", []):
            artifact_key = artifact_ref.get("artifact_key")
            if artifact_key and artifact_key not in parent_chunk_by_artifact_key:
                parent_chunk_by_artifact_key[artifact_key] = chunk_key

    artifact_chunks = _artifact_chunks(
        table_artifacts=table_artifacts,
        image_artifacts=image_artifacts,
        parent_chunk_by_artifact_key=parent_chunk_by_artifact_key,
    )
    return [*narrative_chunks, *artifact_chunks], table_artifacts, image_artifacts, block_graph


def _build_markdown_block_graph(*, title: str, sections: list[_Section]) -> ParsedMarkdownBlockGraph:
    blocks: list[ParsedMarkdownBlock] = []
    edges: list[ParsedMarkdownBlockEdge] = []
    diagnostics: list[dict[str, Any]] = []
    previous_block_id: str | None = None

    for section_index, section in enumerate(sections):
        index = 0
        while index < len(section.lines):
            line = section.lines[index]
            absolute_line = section.line_start + index
            fence = _fence_marker(line)
            if fence is not None:
                end_index = _code_fence_end_index(section.lines, index, fence)
                block_lines = section.lines[index : end_index + 1]
                block = _markdown_block(
                    block_index=len(blocks),
                    block_type="code_fence",
                    line_start=absolute_line,
                    line_end=section.line_start + end_index,
                    heading_path=section.heading_path,
                    raw_text="\n".join(block_lines),
                    metadata_json={
                        "section_index": section_index,
                        "section_title": section.title,
                        "fence_marker": fence,
                    },
                )
                blocks.append(block)
                previous_block_id = _append_follows_edge(edges, previous_block_id, block.block_id)
                index = end_index + 1
                continue

            table_end = _table_end_index(section.lines, index)
            if table_end is not None:
                table_lines = section.lines[index : table_end + 1]
                columns, rows = _parse_table(table_lines)
                normalized_markdown = _normalized_table_markdown(columns, rows)
                block = _markdown_block(
                    block_index=len(blocks),
                    block_type="table",
                    line_start=absolute_line,
                    line_end=section.line_start + table_end,
                    heading_path=section.heading_path,
                    raw_text="\n".join(table_lines),
                    normalized_text=normalized_markdown,
                    metadata_json={
                        "section_index": section_index,
                        "section_title": section.title,
                        "columns": columns,
                        "rows": rows,
                        "row_count": len(rows),
                        "summary": _table_summary(columns=columns, rows=rows),
                    },
                )
                blocks.append(block)
                previous_block_id = _append_follows_edge(edges, previous_block_id, block.block_id)
                index = table_end + 1
                continue

            image_match = _IMAGE_LINE_RE.match(line)
            if image_match:
                original_uri = _parse_image_uri(image_match.group(2))
                block = _markdown_block(
                    block_index=len(blocks),
                    block_type="image",
                    line_start=absolute_line,
                    line_end=absolute_line,
                    heading_path=section.heading_path,
                    raw_text=line,
                    normalized_text=original_uri,
                    metadata_json={
                        "section_index": section_index,
                        "section_title": section.title,
                        "image_syntax": "markdown_image",
                        "original_uri": original_uri,
                        "alt_text": _optional_str(image_match.group(1)),
                    },
                )
                blocks.append(block)
                previous_block_id = _append_follows_edge(edges, previous_block_id, block.block_id)
                index += 1
                continue

            block_type = _markdown_text_block_type(line)
            diagnostics.extend(_markdown_block_diagnostics(line=line, line_no=absolute_line))
            block = _markdown_block(
                block_index=len(blocks),
                block_type=block_type,
                line_start=absolute_line,
                line_end=absolute_line,
                heading_path=section.heading_path,
                raw_text=line,
                metadata_json={
                    "section_index": section_index,
                    "section_title": section.title,
                },
            )
            blocks.append(block)
            previous_block_id = _append_follows_edge(edges, previous_block_id, block.block_id)
            index += 1

    return ParsedMarkdownBlockGraph(title=title, blocks=blocks, edges=edges, diagnostics=diagnostics)


def _markdown_block(
    *,
    block_index: int,
    block_type: str,
    line_start: int,
    line_end: int,
    heading_path: list[str],
    raw_text: str,
    normalized_text: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> ParsedMarkdownBlock:
    return ParsedMarkdownBlock(
        block_id=f"blk_{block_index + 1:03d}",
        block_type=block_type,
        line_start=line_start,
        line_end=line_end,
        heading_path=heading_path,
        raw_text=raw_text,
        normalized_text=normalized_text,
        metadata_json=metadata_json or {},
    )


def _append_follows_edge(
    edges: list[ParsedMarkdownBlockEdge],
    previous_block_id: str | None,
    block_id: str,
) -> str:
    if previous_block_id is not None:
        edges.append(
            ParsedMarkdownBlockEdge(
                source_block_id=previous_block_id,
                target_block_id=block_id,
                edge_type="follows",
            )
        )
    return block_id


def _code_fence_end_index(lines: list[str], start_index: int, fence_marker: str) -> int:
    index = start_index + 1
    while index < len(lines):
        if _fence_marker(lines[index]) == fence_marker:
            return index
        index += 1
    return len(lines) - 1


def _markdown_text_block_type(line: str) -> str:
    stripped = line.strip()
    if not stripped:
        return "blank"
    if _HEADING_RE.match(line):
        return "heading"
    if stripped.startswith(">"):
        return "blockquote"
    if re.match(r"^(\s*([-*+]|\d+[.)])\s+)", line):
        return "list"
    if stripped in {"---", "***", "___"}:
        return "thematic_break"
    if stripped.startswith("<"):
        return "html"
    return "paragraph"


def _markdown_block_diagnostics(*, line: str, line_no: int) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    stripped = line.strip()
    if "[![" in stripped:
        diagnostics.append(
            {
                "line": line_no,
                "code": "unsupported_linked_markdown_image",
                "message": "Linked Markdown image remains paragraph text in this task.",
            }
        )
    if "<img" in stripped.lower():
        diagnostics.append(
            {
                "line": line_no,
                "code": "unsupported_html_image",
                "message": "HTML image remains HTML/text block in this task.",
            }
        )
    return diagnostics


def _artifacts_from_block_graph(
    graph: ParsedMarkdownBlockGraph,
) -> tuple[
    list[ParsedTableArtifact],
    list[ParsedImageArtifact],
    list[ParsedArtifactBinding],
    dict[str, ParsedTableArtifact | ParsedImageArtifact],
]:
    table_artifacts: list[ParsedTableArtifact] = []
    image_artifacts: list[ParsedImageArtifact] = []
    artifact_bindings: list[ParsedArtifactBinding] = []
    artifact_by_block_id: dict[str, ParsedTableArtifact | ParsedImageArtifact] = {}

    for block_index, block in enumerate(graph.blocks):
        if block.block_type == "table":
            artifact_key = f"tbl_{len(table_artifacts) + 1:03d}"
            columns = _list_metadata(block.metadata_json.get("columns"))
            rows = _rows_metadata(block.metadata_json.get("rows"))
            normalized_markdown = block.normalized_text or _normalized_table_markdown(columns, rows)
            artifact = ParsedTableArtifact(
                artifact_key=artifact_key,
                line_start=block.line_start,
                line_end=block.line_end,
                heading_path=block.heading_path,
                columns=columns,
                rows=rows,
                normalized_markdown=normalized_markdown,
                summary=_optional_str(block.metadata_json.get("summary"))
                or _table_summary(columns=columns, rows=rows),
                metadata_json={
                    "source_block_id": block.block_id,
                    "bound_block_ids": [block.block_id],
                    "source_block_type": block.block_type,
                },
            )
            table_artifacts.append(artifact)
            artifact_by_block_id[block.block_id] = artifact
            artifact_bindings.append(_artifact_binding("table", artifact, block))
            continue

        if block.block_type == "image":
            artifact_key = f"img_{len(image_artifacts) + 1:03d}"
            nearby_text = _nearby_text_for_image_block(blocks=graph.blocks, image_index=block_index)
            artifact = ParsedImageArtifact(
                artifact_key=artifact_key,
                line_start=block.line_start,
                line_end=block.line_end,
                heading_path=block.heading_path,
                original_uri=str(block.metadata_json["original_uri"]),
                alt_text=_optional_str(block.metadata_json.get("alt_text")),
                nearby_text=nearby_text,
                metadata_json={
                    "source_block_id": block.block_id,
                    "bound_block_ids": [block.block_id],
                    "source_block_type": block.block_type,
                    "image_syntax": block.metadata_json.get("image_syntax"),
                },
            )
            image_artifacts.append(artifact)
            artifact_by_block_id[block.block_id] = artifact
            artifact_bindings.append(_artifact_binding("image", artifact, block))

    return table_artifacts, image_artifacts, artifact_bindings, artifact_by_block_id


def _artifact_binding(
    artifact_type: str,
    artifact: ParsedTableArtifact | ParsedImageArtifact,
    block: ParsedMarkdownBlock,
) -> ParsedArtifactBinding:
    return ParsedArtifactBinding(
        artifact_type=artifact_type,  # type: ignore[arg-type]
        artifact_key=artifact.artifact_key,
        source_block_id=block.block_id,
        bound_block_ids=[block.block_id],
        role="primary",
        locator=artifact.locator,
    )


def _block_graph_with_artifact_bindings(
    graph: ParsedMarkdownBlockGraph,
    artifact_bindings: list[ParsedArtifactBinding],
) -> ParsedMarkdownBlockGraph:
    return ParsedMarkdownBlockGraph(
        title=graph.title,
        blocks=graph.blocks,
        edges=graph.edges,
        artifact_bindings=artifact_bindings,
        diagnostics=graph.diagnostics,
    )


def _rendered_block_entries(
    *,
    blocks: list[ParsedMarkdownBlock],
    artifact_by_block_id: dict[str, ParsedTableArtifact | ParsedImageArtifact],
) -> list[_ChunkBlockEntry]:
    entries: list[_ChunkBlockEntry] = []
    for block in blocks:
        artifact = artifact_by_block_id.get(block.block_id)
        if isinstance(artifact, ParsedTableArtifact):
            entries.append(
                _ChunkBlockEntry(
                    block=block,
                    rendered_text=_table_placeholder(artifact),
                    linked_artifact=_linked_artifact(
                        artifact_type="table",
                        artifact_key=artifact.artifact_key,
                        locator=artifact.locator,
                        source_block_id=block.block_id,
                        bound_block_ids=[block.block_id],
                    ),
                )
            )
            continue
        if isinstance(artifact, ParsedImageArtifact):
            entries.append(
                _ChunkBlockEntry(
                    block=block,
                    rendered_text=_image_placeholder(artifact),
                    linked_artifact=_linked_artifact(
                        artifact_type="image",
                        artifact_key=artifact.artifact_key,
                        locator=artifact.locator,
                        source_block_id=block.block_id,
                        bound_block_ids=[block.block_id],
                    ),
                )
            )
            continue
        entries.append(_ChunkBlockEntry(block=block, rendered_text=block.raw_text))
    return entries


def _narrative_chunks_from_blocks(
    *,
    section_title: str,
    section_heading_path: list[str],
    entries: list[_ChunkBlockEntry],
    start_index: int,
    max_chars: int,
    overlap_lines: int,
) -> list[ParsedChunk]:
    chunks: list[ParsedChunk] = []
    current: list[_ChunkBlockEntry] = []

    for entry in entries:
        primary_entry = _ChunkBlockEntry(
            block=entry.block,
            rendered_text=entry.rendered_text,
            linked_artifact=entry.linked_artifact,
            ownership="primary",
        )
        candidate = current + [primary_entry]
        if current and len(_block_entries_text(candidate)) > max_chars:
            chunk = _chunk_from_block_entries(
                section_title=section_title,
                section_heading_path=section_heading_path,
                entries=current,
                chunk_key=f"narrative_{start_index + len(chunks) + 1:03d}",
            )
            if chunk is not None:
                chunks.append(chunk)
            current = [_overlap_entry(item) for item in current[-overlap_lines:]] if overlap_lines else []
        current.append(primary_entry)

    if current:
        chunk = _chunk_from_block_entries(
            section_title=section_title,
            section_heading_path=section_heading_path,
            entries=current,
            chunk_key=f"narrative_{start_index + len(chunks) + 1:03d}",
        )
        if chunk is not None:
            chunks.append(chunk)
    return chunks


def _overlap_entry(entry: _ChunkBlockEntry) -> _ChunkBlockEntry:
    return _ChunkBlockEntry(
        block=entry.block,
        rendered_text=entry.rendered_text,
        linked_artifact=entry.linked_artifact,
        ownership="overlap",
    )


def _chunk_from_block_entries(
    *,
    section_title: str,
    section_heading_path: list[str],
    entries: list[_ChunkBlockEntry],
    chunk_key: str,
) -> ParsedChunk | None:
    content = _block_entries_text(entries).strip()
    if not content:
        return None
    linked_artifacts = [
        _linked_artifact_for_chunk(entry)
        for entry in entries
        if entry.linked_artifact is not None
    ]
    return ParsedChunk(
        title=section_title,
        content=content,
        line_start=entries[0].block.line_start,
        line_end=entries[-1].block.line_end,
        heading_path=section_heading_path,
        chunk_key=chunk_key,
        metadata_json={
            "knowledge_type": KNOWLEDGE_TYPE_NAME_DOCUMENT,
            "heading_path": section_heading_path,
            "chunk_kind": "narrative",
            "primary_block_ids": _block_ids_by_ownership(entries, "primary"),
            "overlap_block_ids": _block_ids_by_ownership(entries, "overlap"),
            "linked_artifacts": linked_artifacts,
        },
    )


def _artifact_chunks(
    *,
    table_artifacts: list[ParsedTableArtifact],
    image_artifacts: list[ParsedImageArtifact],
    parent_chunk_by_artifact_key: dict[str, str],
) -> list[ParsedChunk]:
    chunks: list[ParsedChunk] = []
    for artifact in table_artifacts:
        chunks.append(
            ParsedChunk(
                title=_artifact_title(artifact.heading_path, artifact.artifact_key),
                content=_table_summary_content(artifact),
                line_start=artifact.line_start,
                line_end=artifact.line_end,
                heading_path=artifact.heading_path,
                chunk_key=f"{artifact.artifact_key}_summary",
                metadata_json=_artifact_chunk_metadata(
                    artifact_type="table",
                    artifact_key=artifact.artifact_key,
                    chunk_kind="table_summary",
                    locator=artifact.locator,
                    heading_path=artifact.heading_path,
                    source_block_id=_optional_str(artifact.metadata_json.get("source_block_id")),
                    bound_block_ids=_list_metadata(artifact.metadata_json.get("bound_block_ids")),
                    parent_chunk_by_artifact_key=parent_chunk_by_artifact_key,
                ),
            )
        )
        chunks.append(
            ParsedChunk(
                title=_artifact_title(artifact.heading_path, artifact.artifact_key),
                content=f"Table {artifact.artifact_key} rows:\n{artifact.normalized_markdown}",
                line_start=artifact.line_start,
                line_end=artifact.line_end,
                heading_path=artifact.heading_path,
                chunk_key=f"{artifact.artifact_key}_rows_001",
                metadata_json=_artifact_chunk_metadata(
                    artifact_type="table",
                    artifact_key=artifact.artifact_key,
                    chunk_kind="table_rows",
                    locator=artifact.locator,
                    heading_path=artifact.heading_path,
                    source_block_id=_optional_str(artifact.metadata_json.get("source_block_id")),
                    bound_block_ids=_list_metadata(artifact.metadata_json.get("bound_block_ids")),
                    parent_chunk_by_artifact_key=parent_chunk_by_artifact_key,
                ),
            )
        )

    for artifact in image_artifacts:
        chunks.append(
            ParsedChunk(
                title=_artifact_title(artifact.heading_path, artifact.artifact_key),
                content=_image_summary_content(artifact),
                line_start=artifact.line_start,
                line_end=artifact.line_end,
                heading_path=artifact.heading_path,
                chunk_key=f"{artifact.artifact_key}_summary",
                metadata_json=_artifact_chunk_metadata(
                    artifact_type="image",
                    artifact_key=artifact.artifact_key,
                    chunk_kind="image_summary",
                    locator=artifact.locator,
                    heading_path=artifact.heading_path,
                    source_block_id=_optional_str(artifact.metadata_json.get("source_block_id")),
                    bound_block_ids=_list_metadata(artifact.metadata_json.get("bound_block_ids")),
                    parent_chunk_by_artifact_key=parent_chunk_by_artifact_key,
                ),
            )
        )
    return chunks


def _fence_marker(line: str) -> str | None:
    stripped = line.lstrip()
    if stripped.startswith("```"):
        return "```"
    if stripped.startswith("~~~"):
        return "~~~"
    return None


def _table_end_index(lines: list[str], start_index: int) -> int | None:
    if start_index + 1 >= len(lines):
        return None
    if not _is_table_row(lines[start_index]) or not _is_table_separator(lines[start_index + 1]):
        return None

    end_index = start_index + 1
    index = start_index + 2
    while index < len(lines) and _is_table_row(lines[index]):
        end_index = index
        index += 1
    return end_index


def _is_table_row(line: str) -> bool:
    stripped = line.strip()
    return "|" in stripped and bool(_table_cells(line))


def _is_table_separator(line: str) -> bool:
    cells = _table_cells(line)
    return bool(cells) and all(_TABLE_SEPARATOR_CELL_RE.match(cell.replace(" ", "")) for cell in cells)


def _table_cells(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped:
        return []
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _parse_table(lines: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    columns = [_safe_table_cell(cell) for cell in _table_cells(lines[0])]
    rows: list[dict[str, str]] = []
    for line in lines[2:]:
        cells = [_safe_table_cell(cell) for cell in _table_cells(line)]
        row = {
            column: cells[index] if index < len(cells) else ""
            for index, column in enumerate(columns)
        }
        if any(value for value in row.values()):
            rows.append(row)
    return columns, rows


def _normalized_table_markdown(columns: list[str], rows: list[dict[str, str]]) -> str:
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    body = [
        "| " + " | ".join(_escape_table_cell(row.get(column, "")) for column in columns) + " |"
        for row in rows
    ]
    return "\n".join([header, separator, *body])


def _table_summary(*, columns: list[str], rows: list[dict[str, str]]) -> str:
    return f"Markdown table with columns {', '.join(columns)} and {len(rows)} data row(s)."


def _table_summary_content(artifact: ParsedTableArtifact) -> str:
    return "\n".join(
        [
            f"Table {artifact.artifact_key}: {artifact.summary or _table_summary(columns=artifact.columns, rows=artifact.rows)}",
            f"Columns: {', '.join(artifact.columns)}",
            f"Rows: {len(artifact.rows)}",
            f"Locator: {artifact.locator}",
        ]
    )


def _image_summary_content(artifact: ParsedImageArtifact) -> str:
    parts = [
        f"Image {artifact.artifact_key}",
        f"Original URI: {artifact.original_uri}",
        f"Locator: {artifact.locator}",
    ]
    if artifact.alt_text:
        parts.append(f"Alt text: {artifact.alt_text}")
    if artifact.caption:
        parts.append(f"Caption: {artifact.caption}")
    if artifact.nearby_text:
        parts.append(f"Nearby text: {artifact.nearby_text}")
    return "\n".join(parts)


def _table_placeholder(artifact: ParsedTableArtifact) -> str:
    columns = " / ".join(artifact.columns[:3]) or "table"
    return f"[Table {artifact.artifact_key}: {columns}, {artifact.locator}]"


def _image_placeholder(artifact: ParsedImageArtifact) -> str:
    label = artifact.alt_text or artifact.original_uri
    return f"[Image {artifact.artifact_key}: {label}, {artifact.locator}]"


def _linked_artifact(
    *,
    artifact_type: str,
    artifact_key: str,
    locator: str,
    source_block_id: str,
    bound_block_ids: list[str],
) -> dict[str, Any]:
    return {
        "artifact_type": artifact_type,
        "artifact_key": artifact_key,
        "locator": locator,
        "source_block_id": source_block_id,
        "bound_block_ids": bound_block_ids,
        "role": "primary_reference",
    }


def _linked_artifact_for_chunk(entry: _ChunkBlockEntry) -> dict[str, Any]:
    if entry.linked_artifact is None:
        return {}
    linked = dict(entry.linked_artifact)
    linked["role"] = "context_reference" if entry.ownership == "overlap" else "primary_reference"
    return linked


def _block_ids_by_ownership(entries: list[_ChunkBlockEntry], ownership: str) -> list[str]:
    return [
        entry.block.block_id
        for entry in entries
        if entry.ownership == ownership and entry.block.block_type != "blank"
    ]


def _artifact_chunk_metadata(
    *,
    artifact_type: str,
    artifact_key: str,
    chunk_kind: str,
    locator: str,
    heading_path: list[str],
    source_block_id: str | None,
    bound_block_ids: list[str],
    parent_chunk_by_artifact_key: dict[str, str],
) -> dict[str, Any]:
    metadata = {
        "knowledge_type": KNOWLEDGE_TYPE_NAME_DOCUMENT,
        "heading_path": heading_path,
        "chunk_kind": chunk_kind,
        "artifact_type": artifact_type,
        "artifact_key": artifact_key,
        "artifact_locator": locator,
        "bound_block_ids": bound_block_ids,
        "parent_narrative_chunk_key": parent_chunk_by_artifact_key.get(artifact_key),
    }
    if source_block_id is not None:
        metadata["source_block_id"] = source_block_id
    return metadata


def _artifact_title(heading_path: list[str], artifact_key: str) -> str:
    if heading_path:
        return _safe_title(f"{heading_path[-1]} {artifact_key}")
    return artifact_key


def _block_entries_text(entries: list[_ChunkBlockEntry]) -> str:
    return "\n".join(entry.rendered_text for entry in entries)


def _parse_image_uri(raw_uri: str) -> str:
    uri = raw_uri.strip()
    if uri.startswith("<") and ">" in uri:
        return uri[1 : uri.index(">")]
    if " " in uri:
        return uri.split(" ", 1)[0].strip("<>")
    return uri.strip("<>")


def _nearby_text_for_image_block(*, blocks: list[ParsedMarkdownBlock], image_index: int) -> str | None:
    candidates: list[str] = []
    for block in reversed(blocks[:image_index]):
        if block.block_type == "blank":
            continue
        text = block.raw_text.strip()
        if text:
            candidates.append(text)
            break
    for block in blocks[image_index + 1 :]:
        if block.block_type == "blank":
            continue
        next_text = block.raw_text.strip()
        if next_text:
            candidates.append(next_text)
            break
    return _optional_str(" ".join(candidates))


def _list_metadata(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def _rows_metadata(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        rows.append({str(key): str(row_value) for key, row_value in item.items()})
    return rows


def _safe_table_cell(value: str) -> str:
    return value.replace("\n", " ").strip()


def _escape_table_cell(value: str) -> str:
    return _safe_table_cell(value).replace("|", "\\|")


def _split_lines(
    line_start: int,
    lines: list[str],
    max_chars: int,
    overlap_lines: int,
) -> list[tuple[int, list[str]]]:
    chunks: list[tuple[int, list[str]]] = []
    current_start = line_start
    current: list[str] = []

    for offset, line in enumerate(lines):
        current_line_no = line_start + offset
        candidate = current + [line]
        if current and len("\n".join(candidate)) > max_chars:
            chunks.append((current_start, current))
            overlap = current[-overlap_lines:] if overlap_lines else []
            current = overlap.copy()
            current_start = current_line_no - len(overlap)
        current.append(line)

    if current:
        chunks.append((current_start, current))
    return chunks


def _parse_ai_jsonl(*, path: Path, text: str, max_chars: int) -> ParsedSource:
    turns: list[_Turn] = []
    title: str | None = None

    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise IngestParseError(f"invalid JSONL at line {line_no}") from exc
        if not isinstance(payload, dict):
            raise IngestParseError(f"JSONL line {line_no} must be an object")

        title = title or _optional_str(payload.get("conversation_title")) or _optional_str(payload.get("title"))
        content = _turn_content(payload)
        if content is None:
            continue
        role = _optional_str(payload.get("role") or payload.get("speaker") or payload.get("author")) or "unknown"
        turns.append(_Turn(role=role, text=content, line_start=line_no, line_end=line_no))

    if not turns:
        raise IngestParseError("conversation JSONL produced no turns")

    return _conversation_source(
        path=path,
        title=_safe_title(title or path.stem),
        turns=turns,
        input_format="jsonl",
        line_count=len(text.splitlines()),
        max_chars=max_chars,
    )


def _parse_ai_transcript(*, path: Path, text: str, max_chars: int) -> ParsedSource:
    lines = text.splitlines()
    if not any(line.strip() for line in lines):
        raise IngestParseError("conversation transcript is empty")

    title: str | None = None
    turns: list[_Turn] = []
    current_role: str | None = None
    current_lines: list[str] = []
    current_start = 1
    current_end = 1

    def flush_turn() -> None:
        nonlocal current_role, current_lines, current_start, current_end
        if current_role is None or not any(line.strip() for line in current_lines):
            current_role = None
            current_lines = []
            return
        turns.append(
            _Turn(
                role=current_role,
                text="\n".join(current_lines).strip(),
                line_start=current_start,
                line_end=current_end,
            )
        )
        current_role = None
        current_lines = []

    for line_no, line in enumerate(lines, start=1):
        heading = _HEADING_RE.match(line)
        if heading and title is None:
            title = heading.group(2).strip()
            continue

        speaker = _SPEAKER_RE.match(line)
        if speaker:
            flush_turn()
            current_role = speaker.group(1).strip()
            current_lines = [speaker.group(2).strip()]
            current_start = line_no
            current_end = line_no
            continue

        if current_role is None:
            if not line.strip():
                continue
            current_role = "unknown"
            current_start = line_no
            current_lines = [line]
        else:
            current_lines.append(line)
        current_end = line_no

    flush_turn()

    if not turns:
        raise IngestParseError("conversation transcript produced no turns")

    return _conversation_source(
        path=path,
        title=_safe_title(title or path.stem),
        turns=turns,
        input_format="transcript",
        line_count=len(lines),
        max_chars=max_chars,
    )


def _conversation_source(
    *,
    path: Path,
    title: str,
    turns: list[_Turn],
    input_format: str,
    line_count: int,
    max_chars: int,
) -> ParsedSource:
    participants = sorted({turn.role for turn in turns})
    chunks: list[ParsedChunk] = []

    for window in _turn_windows(turns, max_chars):
        roles = [turn.role for turn in window.turns]
        content = "\n\n".join(_format_turn(turn) for turn in window.turns)
        chunks.append(
            ParsedChunk(
                title=title,
                content=content,
                line_start=window.turns[0].line_start,
                line_end=window.turns[-1].line_end,
                metadata_json={
                    "knowledge_type": KNOWLEDGE_TYPE_NAME_AI_CONVERSATION,
                    "format": input_format,
                    "roles": roles,
                    "turn_start": window.turn_start,
                    "turn_end": window.turn_end,
                    "turn_count": len(window.turns),
                },
            )
        )

    return ParsedSource(
        title=title,
        knowledge_type=KNOWLEDGE_TYPE_NAME_AI_CONVERSATION,
        metadata_json={
            "format": input_format,
            "line_count": line_count,
            "participants": participants,
            "turn_count": len(turns),
            "summary": None,
            "open_questions": [],
            "decisions": [],
        },
        chunks=chunks,
    )


def _turn_windows(turns: list[_Turn], max_chars: int) -> list[_TurnWindow]:
    windows: list[_TurnWindow] = []
    current: list[_Turn] = []
    current_start_index = 0

    for index, turn in enumerate(turns):
        if len(_format_turn(turn)) > max_chars:
            if current:
                windows.append(_TurnWindow(turns=current, turn_start=current_start_index, turn_end=index - 1))
                current = []
            windows.extend(_split_long_turn(turn, max_chars, index))
            continue

        candidate = current + [turn]
        if current and len("\n\n".join(_format_turn(item) for item in candidate)) > max_chars:
            windows.append(_TurnWindow(turns=current, turn_start=current_start_index, turn_end=index - 1))
            current = [turn]
            current_start_index = index
        else:
            if not current:
                current_start_index = index
            current = candidate

    if current:
        windows.append(_TurnWindow(turns=current, turn_start=current_start_index, turn_end=len(turns) - 1))
    return windows


def _split_long_turn(turn: _Turn, max_chars: int, index: int) -> list[_TurnWindow]:
    parts: list[_TurnWindow] = []
    text = turn.text
    start = 0
    while start < len(text):
        part = text[start : start + max_chars]
        parts.append(
            _TurnWindow(
                turns=[_Turn(role=turn.role, text=part, line_start=turn.line_start, line_end=turn.line_end)],
                turn_start=index,
                turn_end=index,
            )
        )
        start += max_chars
    return parts


def _format_turn(turn: _Turn) -> str:
    return f"{turn.role}: {turn.text}".strip()


def _turn_content(payload: dict[str, Any]) -> str | None:
    value = payload.get("content")
    if value is None:
        value = payload.get("text")
    if value is None:
        value = payload.get("message")
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_nonblank(lines: list[str]) -> str | None:
    for line in lines:
        if line.strip():
            return line.strip()
    return None


def _safe_title(value: str) -> str:
    return value[:500]
