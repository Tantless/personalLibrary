from mcp.server.fastmcp import FastMCP

from pkcs.config import get_settings
from pkcs.health import get_health_status
from pkcs.ingest import IngestService


def create_mcp_server() -> FastMCP:
    settings = get_settings()
    server = FastMCP(settings.app_name)

    @server.tool()
    def health_check() -> dict[str, str]:
        """Return service health status."""
        return get_health_status(settings).__dict__

    @server.tool()
    def ingest_source(path: str, source_type: str = "markdown_doc", canonical_key: str | None = None) -> dict:
        """Ingest a local file or non-recursive directory."""
        report = IngestService.from_settings(settings).ingest_source(
            path=path,
            source_type=source_type,
            canonical_key=canonical_key,
        )
        return report.to_dict()

    return server


mcp = create_mcp_server()
