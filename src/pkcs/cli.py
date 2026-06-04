import json

import typer

from pkcs.config import get_settings
from pkcs.health import get_health_status

app = typer.Typer(help="Personal Knowledge Context Server CLI")


@app.command()
def health() -> None:
    """Print service health status."""
    status = get_health_status(get_settings())
    typer.echo(json.dumps(status.__dict__, ensure_ascii=False))


@app.command()
def ingest() -> None:
    """Placeholder for MVP ingest command."""
    raise typer.BadParameter("ingest is not implemented in PR1")


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

