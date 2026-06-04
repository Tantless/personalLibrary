# Personal Knowledge Context Server

PKCS is a local-first personal knowledge context service for external agents.

The confirmed MVP PRD is in `.trellis/tasks/06-03-pkcs-mvp-m1-m2/prd.md`.

## PR1 Scope

This scaffold includes:

* FastAPI health endpoint
* FastMCP server skeleton
* Typer CLI skeleton
* Docker Compose PostgreSQL
* Basic tests for startup and health

## Local Setup

```powershell
uv sync
docker compose up -d postgres
uv run pytest
```

## Health Checks

```powershell
uv run pkcs health
uv run uvicorn pkcs.http.app:app --host 127.0.0.1 --port 8765
```

The HTTP health endpoint is `GET /health`.
