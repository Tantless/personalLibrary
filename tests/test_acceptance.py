import json
from collections import Counter
from contextlib import nullcontext
from pathlib import Path
from uuid import uuid4

from typer.testing import CliRunner

from pkcs.cli import app as cli_app
from pkcs.config import get_settings
from pkcs.ingest import IngestService
from pkcs.mcp.server import create_mcp_server
from pkcs.search import PostgresFTSSearchProvider, SearchService
from pkcs.storage.raw_archive import RawArchiveWriter

FIXTURES_ROOT = Path("tests/fixtures")
EVAL_QUERIES_PATH = FIXTURES_ROOT / "eval_queries.jsonl"


def make_ingest_service(db_session, raw_root: Path) -> IngestService:
    return IngestService(
        session_factory=lambda: nullcontext(db_session),
        raw_archive_writer=RawArchiveWriter(raw_root),
        chunk_max_chars=500,
        chunk_overlap_lines=1,
    )


def make_search_service(db_session) -> SearchService:
    return SearchService(
        provider=PostgresFTSSearchProvider(session_factory=lambda: nullcontext(db_session)),
        default_top_k=10,
    )


def load_eval_queries() -> list[dict]:
    rows: list[dict] = []
    for line_number, line in enumerate(EVAL_QUERIES_PATH.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        assert row["query"].strip(), f"missing query on eval line {line_number}"
        assert row["expected_fixture"].strip(), f"missing expected fixture on eval line {line_number}"
        assert row["expected_canonical_keys"], f"missing expected canonical keys on eval line {line_number}"
        assert row["expected_knowledge_types"], f"missing expected knowledge types on eval line {line_number}"
        rows.append(row)
    return rows


def parse_mcp_json(result) -> dict:
    content = result[0] if isinstance(result, tuple) else result
    return json.loads(content[0].text)


def fixture_files(knowledge_type: str) -> list[Path]:
    if knowledge_type == "document":
        root = FIXTURES_ROOT / "markdown"
        patterns = ("*.md", "*.txt")
    elif knowledge_type == "ai_conversation":
        root = FIXTURES_ROOT / "conversations"
        patterns = ("*.md", "*.txt", "*.jsonl")
    else:
        raise ValueError(f"unsupported knowledge_type: {knowledge_type}")

    files: list[Path] = []
    for pattern in patterns:
        files.extend(root.glob(pattern))
    return sorted(files)


def copy_fixture_with_marker(source_path: Path, target_path: Path, marker: str) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if source_path.suffix.lower() == ".jsonl":
        marked_lines = []
        for line in source_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            for field in ("content", "text", "message"):
                if isinstance(payload.get(field), str):
                    payload[field] = f"{payload[field]} {marker}"
                    break
            else:
                payload["content"] = marker
            marked_lines.append(json.dumps(payload, ensure_ascii=False))
        target_path.write_text("\n".join(marked_lines) + "\n", encoding="utf-8")
        return

    marked_text = "\n".join(
        f"{line} {marker}" if line.strip() else line
        for line in source_path.read_text(encoding="utf-8").splitlines()
    )
    target_path.write_text(marked_text, encoding="utf-8")


def test_mvp_eval_fixture_corpus_and_queries_have_required_shape() -> None:
    markdown_files = fixture_files("document")
    conversation_files = fixture_files("ai_conversation")
    eval_rows = load_eval_queries()
    fixture_relpaths = {
        file.relative_to(FIXTURES_ROOT).as_posix() for file in [*markdown_files, *conversation_files]
    }
    knowledge_type_counts = Counter(row["expected_knowledge_types"][0] for row in eval_rows)

    assert len(markdown_files) >= 10
    assert len(conversation_files) >= 10
    assert len(eval_rows) >= 20
    assert knowledge_type_counts["document"] >= 10
    assert knowledge_type_counts["ai_conversation"] >= 10
    assert {row["expected_fixture"] for row in eval_rows} <= fixture_relpaths


def test_mvp_eval_queries_meet_retrieval_thresholds(db_session, tmp_path) -> None:
    run_id = uuid4().hex
    ingest = make_ingest_service(db_session, tmp_path / "raw")
    eval_rows = load_eval_queries()
    ingested_by_fixture: dict[str, str] = {}
    markers_by_fixture: dict[str, str] = {}

    for index, row in enumerate(eval_rows, start=1):
        fixture_relpath = row["expected_fixture"]
        if fixture_relpath in ingested_by_fixture:
            continue

        knowledge_types = row["expected_knowledge_types"]
        assert len(knowledge_types) == 1
        expected_key = row["expected_canonical_keys"][0].format(run_id=run_id)
        marker = f"evalmarker{run_id}{index}"
        marked_fixture_path = tmp_path / "eval_corpus" / fixture_relpath
        copy_fixture_with_marker(FIXTURES_ROOT / fixture_relpath, marked_fixture_path, marker)
        report = ingest.ingest_source(
            path=marked_fixture_path,
            knowledge_type=knowledge_types[0],
            canonical_key=expected_key,
        )

        assert report.status == "completed"
        assert len(report.succeeded) == 1
        assert report.failed == []
        ingested_by_fixture[fixture_relpath] = expected_key
        markers_by_fixture[fixture_relpath] = marker

    assert sum(1 for key in ingested_by_fixture if key.startswith("markdown/")) >= 10
    assert sum(1 for key in ingested_by_fixture if key.startswith("conversations/")) >= 10

    search = make_search_service(db_session)
    top_10_hits = 0
    top_5_hits = 0
    misses: list[dict] = []

    for row in eval_rows:
        expected_keys = {key.format(run_id=run_id) for key in row["expected_canonical_keys"]}
        response = search.search_knowledge(query=f"{row['query']} {markers_by_fixture[row['expected_fixture']]}", top_k=10)
        result_keys = [result.canonical_key for result in response.results]
        rank = next((index for index, key in enumerate(result_keys, start=1) if key in expected_keys), None)

        if rank is not None and rank <= 10:
            top_10_hits += 1
        if rank is not None and rank <= 5:
            top_5_hits += 1
        if rank is None:
            misses.append({"query": row["query"], "expected": sorted(expected_keys), "actual": result_keys})

    total = len(eval_rows)
    assert top_10_hits / total >= 0.80, misses
    assert top_5_hits / total >= 0.60, misses


def test_final_acceptance_cli_ingest_search_read_context_pack_flow(monkeypatch, migrated_database_url, tmp_path) -> None:
    token = f"cliaccept{uuid4().hex}"
    source_path = tmp_path / "cli-acceptance.md"
    source_path.write_text(
        "# CLI Acceptance\n\n"
        f"The {token} flow proves ingest, search, read, and context pack commands.\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PKCS_DATABASE_URL", migrated_database_url)
    monkeypatch.setenv("PKCS_RAW_ARCHIVE_PATH", str(tmp_path / "raw"))
    get_settings.cache_clear()
    runner = CliRunner()

    try:
        ingest_result = runner.invoke(
            cli_app,
            [
                "ingest",
                str(source_path),
                "--knowledge-type",
                "document",
                "--canonical-key",
                f"document:cli-acceptance-{token}",
            ],
        )
        assert ingest_result.exit_code == 0
        assert json.loads(ingest_result.stdout)["status"] == "completed"

        search_result = runner.invoke(cli_app, ["search", token, "--top-k", "1"])
        assert search_result.exit_code == 0
        search_body = json.loads(search_result.stdout)
        chunk_id = search_body["results"][0]["chunk_id"]

        read_result = runner.invoke(cli_app, ["read", "--chunk-id", chunk_id, "--context-lines", "1"])
        assert read_result.exit_code == 0
        read_body = json.loads(read_result.stdout)
        assert token in read_body["content"]

        pack_result = runner.invoke(cli_app, ["context-pack", token, "--top-k", "5", "--budget-tokens", "400"])
        assert pack_result.exit_code == 0
        pack_body = json.loads(pack_result.stdout)
        assert pack_body["evidence"]
        assert "## Conflicts / Caveats" in pack_body["context_pack_markdown"]
    finally:
        get_settings.cache_clear()


async def test_codex_first_mcp_acceptance_generic_client_fallback(
    monkeypatch,
    migrated_database_url,
    tmp_path,
) -> None:
    token = f"mcpaccept{uuid4().hex}"
    source_path = tmp_path / "mcp-acceptance.md"
    source_path.write_text(
        "# MCP Acceptance\n\n"
        f"The {token} flow proves health, ingest, search, read, and context pack tools.\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PKCS_DATABASE_URL", migrated_database_url)
    monkeypatch.setenv("PKCS_RAW_ARCHIVE_PATH", str(tmp_path / "raw"))
    get_settings.cache_clear()

    try:
        server = create_mcp_server()
        tools = await server.list_tools()
        tool_names = {tool.name for tool in tools}
        assert {
            "health_check",
            "ingest_source",
            "search_knowledge",
            "read_source",
            "get_context_pack",
        } <= tool_names

        health_result = await server.call_tool("health_check", {})
        assert parse_mcp_json(health_result)["status"] == "ok"

        ingest_result = await server.call_tool(
            "ingest_source",
            {
                "path": str(source_path),
                "knowledge_type": "document",
                "canonical_key": f"document:mcp-acceptance-{token}",
            },
        )
        assert parse_mcp_json(ingest_result)["status"] == "completed"

        search_result = await server.call_tool("search_knowledge", {"query": token, "top_k": 1})
        search_body = parse_mcp_json(search_result)
        chunk_id = search_body["results"][0]["chunk_id"]

        read_result = await server.call_tool("read_source", {"chunk_id": chunk_id, "context_lines": 1})
        read_body = parse_mcp_json(read_result)
        assert token in read_body["content"]

        pack_result = await server.call_tool("get_context_pack", {"query": token, "top_k": 5, "budget_tokens": 400})
        pack_body = parse_mcp_json(pack_result)
        assert pack_body["evidence"]
        assert "## Conflicts / Caveats" in pack_body["context_pack_markdown"]
    finally:
        get_settings.cache_clear()
