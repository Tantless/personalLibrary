from mcp.server.fastmcp import FastMCP

from pkcs.config import get_settings
from pkcs.health import get_health_status


def create_mcp_server() -> FastMCP:
    settings = get_settings()
    server = FastMCP(settings.app_name)

    @server.tool()
    def health_check() -> dict[str, str]:
        """Return service health status."""
        return get_health_status(settings).__dict__

    return server


mcp = create_mcp_server()

