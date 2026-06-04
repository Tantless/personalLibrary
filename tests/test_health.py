import json

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from pkcs.cli import app as cli_app
from pkcs.http.app import create_app
from pkcs.mcp.server import create_mcp_server


def test_http_health() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "Personal Knowledge Context Server"


def test_cli_health() -> None:
    runner = CliRunner()

    result = runner.invoke(cli_app, ["health"])

    assert result.exit_code == 0
    body = json.loads(result.stdout)
    assert body["status"] == "ok"


def test_mcp_server_can_be_created() -> None:
    server = create_mcp_server()

    assert server is not None

