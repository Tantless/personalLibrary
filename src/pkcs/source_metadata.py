from pathlib import Path


SOURCE_FORMAT_MD = 1
SOURCE_FORMAT_TXT = 2
SOURCE_FORMAT_JSONL = 3
SOURCE_FORMAT_PDF = 4
SOURCE_FORMAT_DOCX = 5
SOURCE_FORMAT_XLSX = 6

NORMALIZED_FORMAT_MARKDOWN = 1
NORMALIZED_FORMAT_PLAIN_TEXT = 2
NORMALIZED_FORMAT_TABLE_MARKDOWN = 3

KNOWLEDGE_TYPE_DOCUMENT = 1
KNOWLEDGE_TYPE_AI_CONVERSATION = 2
KNOWLEDGE_TYPE_WIKI_ARTICLE = 3
KNOWLEDGE_TYPE_GAME_GUIDE = 4
KNOWLEDGE_TYPE_DIARY = 5
KNOWLEDGE_TYPE_EMAIL = 6

SOURCE_FORMAT_NAMES = {
    SOURCE_FORMAT_MD: "md",
    SOURCE_FORMAT_TXT: "txt",
    SOURCE_FORMAT_JSONL: "jsonl",
    SOURCE_FORMAT_PDF: "pdf",
    SOURCE_FORMAT_DOCX: "docx",
    SOURCE_FORMAT_XLSX: "xlsx",
}
SOURCE_FORMAT_CODES = {name: code for code, name in SOURCE_FORMAT_NAMES.items()}
SOURCE_FORMAT_CODES_BY_EXTENSION = {
    ".md": SOURCE_FORMAT_MD,
    ".txt": SOURCE_FORMAT_TXT,
    ".jsonl": SOURCE_FORMAT_JSONL,
    ".pdf": SOURCE_FORMAT_PDF,
    ".docx": SOURCE_FORMAT_DOCX,
    ".xlsx": SOURCE_FORMAT_XLSX,
}

NORMALIZED_FORMAT_NAMES = {
    NORMALIZED_FORMAT_MARKDOWN: "markdown",
    NORMALIZED_FORMAT_PLAIN_TEXT: "plain_text",
    NORMALIZED_FORMAT_TABLE_MARKDOWN: "table_markdown",
}
NORMALIZED_FORMAT_BY_SOURCE_FORMAT = {
    SOURCE_FORMAT_MD: NORMALIZED_FORMAT_MARKDOWN,
    SOURCE_FORMAT_TXT: NORMALIZED_FORMAT_PLAIN_TEXT,
    SOURCE_FORMAT_JSONL: NORMALIZED_FORMAT_PLAIN_TEXT,
    SOURCE_FORMAT_XLSX: NORMALIZED_FORMAT_TABLE_MARKDOWN,
}

KNOWLEDGE_TYPE_NAMES = {
    KNOWLEDGE_TYPE_DOCUMENT: "document",
    KNOWLEDGE_TYPE_AI_CONVERSATION: "ai_conversation",
    KNOWLEDGE_TYPE_WIKI_ARTICLE: "wiki_article",
    KNOWLEDGE_TYPE_GAME_GUIDE: "game_guide",
    KNOWLEDGE_TYPE_DIARY: "diary",
    KNOWLEDGE_TYPE_EMAIL: "email",
}
KNOWLEDGE_TYPE_CODES = {name: code for code, name in KNOWLEDGE_TYPE_NAMES.items()}
KNOWLEDGE_TYPE_KEY_PREFIXES = {
    KNOWLEDGE_TYPE_DOCUMENT: "D",
    KNOWLEDGE_TYPE_AI_CONVERSATION: "A",
    KNOWLEDGE_TYPE_WIKI_ARTICLE: "W",
    KNOWLEDGE_TYPE_GAME_GUIDE: "G",
    KNOWLEDGE_TYPE_DIARY: "J",
    KNOWLEDGE_TYPE_EMAIL: "E",
}

SUPPORTED_KNOWLEDGE_TYPE_CODES = {KNOWLEDGE_TYPE_DOCUMENT, KNOWLEDGE_TYPE_AI_CONVERSATION}
SUPPORTED_SOURCE_FORMAT_CODES_BY_KNOWLEDGE_TYPE = {
    KNOWLEDGE_TYPE_DOCUMENT: {SOURCE_FORMAT_MD, SOURCE_FORMAT_TXT},
    KNOWLEDGE_TYPE_AI_CONVERSATION: {SOURCE_FORMAT_MD, SOURCE_FORMAT_TXT, SOURCE_FORMAT_JSONL},
}


def source_format_code_for_path(path: Path) -> int:
    try:
        return SOURCE_FORMAT_CODES_BY_EXTENSION[path.suffix.lower()]
    except KeyError as exc:
        raise ValueError(f"unsupported source format: {path.suffix.lower()}") from exc


def normalized_format_code_for_source_format(source_format_code: int) -> int:
    try:
        return NORMALIZED_FORMAT_BY_SOURCE_FORMAT[source_format_code]
    except KeyError as exc:
        raise ValueError(f"unsupported normalized format for source format code: {source_format_code}") from exc


def knowledge_type_code_for_name(knowledge_type: str) -> int:
    try:
        code = KNOWLEDGE_TYPE_CODES[knowledge_type]
    except KeyError as exc:
        raise ValueError(f"unsupported knowledge_type: {knowledge_type}") from exc
    if code not in SUPPORTED_KNOWLEDGE_TYPE_CODES:
        raise ValueError(f"unsupported knowledge_type: {knowledge_type}")
    return code


def source_format_name(source_format_code: int) -> str:
    return SOURCE_FORMAT_NAMES.get(source_format_code, f"unknown:{source_format_code}")


def normalized_format_name(normalized_format_code: int) -> str:
    return NORMALIZED_FORMAT_NAMES.get(normalized_format_code, f"unknown:{normalized_format_code}")


def knowledge_type_name(knowledge_type_code: int) -> str:
    return KNOWLEDGE_TYPE_NAMES.get(knowledge_type_code, f"unknown:{knowledge_type_code}")


def canonical_key_prefix_for_knowledge_type(knowledge_type_code: int) -> str:
    try:
        return KNOWLEDGE_TYPE_KEY_PREFIXES[knowledge_type_code]
    except KeyError as exc:
        raise ValueError(f"unsupported canonical key prefix for knowledge_type_code: {knowledge_type_code}") from exc


def validate_source_format_for_knowledge_type(*, source_format_code: int, knowledge_type_code: int) -> None:
    supported = SUPPORTED_SOURCE_FORMAT_CODES_BY_KNOWLEDGE_TYPE.get(knowledge_type_code, set())
    if source_format_code not in supported:
        source_format = source_format_name(source_format_code)
        knowledge_type = knowledge_type_name(knowledge_type_code)
        raise ValueError(f"unsupported source format for {knowledge_type}: {source_format}")
