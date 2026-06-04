from dataclasses import dataclass

from pkcs import __version__
from pkcs.config import Settings


@dataclass(frozen=True)
class HealthStatus:
    status: str
    service: str
    version: str
    environment: str


def get_health_status(settings: Settings) -> HealthStatus:
    return HealthStatus(
        status="ok",
        service=settings.app_name,
        version=__version__,
        environment=settings.env,
    )

