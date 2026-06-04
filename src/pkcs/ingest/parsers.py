import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pkcs.ingest.models import ParsedChunk, ParsedSource, SOURCE_TYPE_AI_CONVERSATION, SOURCE_TYPE_MARKDOWN_DOC


class IngestParseError(ValueError):
    pass


@dataclass(frozen=True)
class _Section:
    title: str
    heading_path: list[str]
    line_start: int
    lines: list[str]


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


def parse_source_file(
    *,
    path: Path,
    source_type: str,
    content_bytes: bytes,
    max_chars: int,
    overlap_lines: int,
) -> ParsedSource:
    text = _decode_utf8(content_bytes, path)
    if source_type == SOURCE_TYPE_MARKDOWN_DOC:
        return _parse_markdown_doc(path=path, text=text, max_chars=max_chars, overlap_lines=overlap_lines)
    if source_type == SOURCE_TYPE_AI_CONVERSATION:
        if path.suffix.lower() == ".jsonl":
            return _parse_ai_jsonl(path=path, text=text, max_chars=max_chars)
        return _parse_ai_transcript(path=path, text=text, max_chars=max_chars)
    raise IngestParseError(f"unsupported source_type: {source_type}")


def _decode_utf8(content_bytes: bytes, path: Path) -> str:
    try:
        return content_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IngestParseError(f"{path} is not valid UTF-8 text") from exc


def _parse_markdown_doc(*, path: Path, text: str, max_chars: int, overlap_lines: int) -> ParsedSource:
    lines = text.splitlines()
    if not any(line.strip() for line in lines):
        raise IngestParseError("document is empty")

    if path.suffix.lower() == ".txt":
        title = _safe_title(_first_nonblank(lines) or path.stem)
        sections = [_Section(title=title, heading_path=[], line_start=1, lines=lines)]
    else:
        title, sections = _markdown_sections(path=path, lines=lines)

    chunks: list[ParsedChunk] = []
    for section in sections:
        chunks.extend(
            _chunks_from_section(
                section=section,
                source_type=SOURCE_TYPE_MARKDOWN_DOC,
                max_chars=max_chars,
                overlap_lines=overlap_lines,
            )
        )

    if not chunks:
        raise IngestParseError("document produced no chunks")

    return ParsedSource(
        title=_safe_title(title),
        source_type=SOURCE_TYPE_MARKDOWN_DOC,
        metadata_json={
            "format": path.suffix.lower().lstrip(".") or "text",
            "line_count": len(lines),
        },
        chunks=chunks,
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
    source_type: str,
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
                    "source_type": source_type,
                    "heading_path": section.heading_path,
                },
            )
        )
    return chunks


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
                    "source_type": SOURCE_TYPE_AI_CONVERSATION,
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
        source_type=SOURCE_TYPE_AI_CONVERSATION,
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
