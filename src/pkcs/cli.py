import json
from pathlib import Path

import typer

from pkcs.config import get_settings
from pkcs.context_pack import ContextPackService
from pkcs.health import get_health_status
from pkcs.ingest import IngestService
from pkcs.reader import ReadSourceService
from pkcs.search import SearchService

app = typer.Typer(help="Personal Knowledge Context Server CLI")


@app.command()
def health() -> None:
    """Print service health status."""
    status = get_health_status(get_settings())
    typer.echo(json.dumps(status.__dict__, ensure_ascii=False))


@app.command()
def ingest(
    path: Path = typer.Argument(..., help="Local file or non-recursive directory to ingest."),
    knowledge_type: str = typer.Option("document", "--knowledge-type", help="document or ai_conversation."),
    canonical_key: str | None = typer.Option(None, "--canonical-key", help="Stable source key for single-file ingest."),
) -> None:
    """Ingest a local file or non-recursive directory."""
    report = IngestService.from_settings(get_settings()).ingest_source(
        path=path,
        knowledge_type=knowledge_type,
        canonical_key=canonical_key,
    )
    typer.echo(json.dumps(report.to_dict(), ensure_ascii=False))


@app.command()
def search(
    query: str = typer.Argument(..., help="Full-text search query."),
    knowledge_type: str | None = typer.Option(None, "--knowledge-type", help="Optional knowledge type filter."),
    canonical_key: str | None = typer.Option(None, "--canonical-key", help="Optional canonical source key filter."),
    top_k: int | None = typer.Option(None, "--top-k", min=1, help="Maximum number of results."),
) -> None:
    """Search ingested knowledge with PostgreSQL full-text search."""
    response = SearchService.from_settings(get_settings()).search_knowledge(
        query=query,
        knowledge_type=knowledge_type,
        canonical_key=canonical_key,
        top_k=top_k,
    )
    typer.echo(json.dumps(response.to_dict(), ensure_ascii=False))


@app.command("read")
def read_source(
    chunk_id: str | None = typer.Option(None, "--chunk-id", help="Chunk id shortcut."),
    source_id: str | None = typer.Option(None, "--source-id", help="Source id for full citation addressing."),
    version_id: str | None = typer.Option(None, "--version-id", help="Version id for full citation addressing."),
    locator: str | None = typer.Option(None, "--locator", help="Line locator, for example 'line 1-3'."),
    context_lines: int = typer.Option(0, "--context-lines", min=0, help="Optional lines before and after citation."),
) -> None:
    """Read a source fragment by chunk id or source/version/locator."""
    fragment = ReadSourceService.from_settings(get_settings()).read_source(
        chunk_id=chunk_id,
        source_id=source_id,
        version_id=version_id,
        locator=locator,
        context_lines=context_lines,
    )
    typer.echo(json.dumps(fragment.to_dict(), ensure_ascii=False))


@app.command("context-pack")
def context_pack(
    query: str = typer.Argument(..., help="Query to build a Context Pack for."),
    knowledge_type: str | None = typer.Option(None, "--knowledge-type", help="Optional knowledge type filter."),
    canonical_key: str | None = typer.Option(None, "--canonical-key", help="Optional canonical source key filter."),
    top_k: int | None = typer.Option(None, "--top-k", min=1, help="Search candidate count."),
    budget_tokens: int | None = typer.Option(None, "--budget-tokens", min=1, help="Soft Markdown budget hint."),
) -> None:
    """Build Context Pack v0 as JSON plus Markdown."""
    response = ContextPackService.from_settings(get_settings()).get_context_pack(
        query=query,
        knowledge_type=knowledge_type,
        canonical_key=canonical_key,
        top_k=top_k,
        budget_tokens=budget_tokens,
    )
    typer.echo(json.dumps(response.to_dict(), ensure_ascii=False))


if __name__ == "__main__":
    app()
