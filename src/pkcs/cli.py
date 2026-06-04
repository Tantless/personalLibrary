import json
from pathlib import Path

import typer

from pkcs.config import get_settings
from pkcs.health import get_health_status
from pkcs.ingest import IngestService

app = typer.Typer(help="Personal Knowledge Context Server CLI")


@app.command()
def health() -> None:
    """Print service health status."""
    status = get_health_status(get_settings())
    typer.echo(json.dumps(status.__dict__, ensure_ascii=False))


@app.command()
def ingest(
    path: Path = typer.Argument(..., help="Local file or non-recursive directory to ingest."),
    source_type: str = typer.Option("markdown_doc", "--source-type", help="markdown_doc or ai_conversation."),
    canonical_key: str | None = typer.Option(None, "--canonical-key", help="Stable source key for single-file ingest."),
) -> None:
    """Ingest a local file or non-recursive directory."""
    report = IngestService.from_settings(get_settings()).ingest_source(
        path=path,
        source_type=source_type,
        canonical_key=canonical_key,
    )
    typer.echo(json.dumps(report.to_dict(), ensure_ascii=False))


@app.command()
def search() -> None:
    """Placeholder for MVP search command."""
    raise typer.BadParameter("search is not implemented in PR1")


@app.command("read")
def read_source() -> None:
    """Placeholder for MVP read_source command."""
    raise typer.BadParameter("read is not implemented in PR1")


@app.command("context-pack")
def context_pack() -> None:
    """Placeholder for MVP context-pack command."""
    raise typer.BadParameter("context-pack is not implemented in PR1")


if __name__ == "__main__":
    app()
