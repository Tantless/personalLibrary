from fastapi import FastAPI

from pkcs.config import get_settings
from pkcs.health import get_health_status


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)

    @app.get("/health")
    def health() -> dict[str, str]:
        return get_health_status(settings).__dict__

    return app


app = create_app()

