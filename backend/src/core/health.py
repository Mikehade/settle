import asyncio

from src.domain.interfaces.services import HealthCheck
from src.shared.logging import get_logger

logger = get_logger(__name__)


class HealthService:
    def __init__(self, checks: list[HealthCheck], timeout_seconds: float = 3.0) -> None:
        self._checks = checks
        self._timeout = timeout_seconds

    async def readiness(self) -> dict[str, bool]:
        results = await asyncio.gather(*(self._run(c) for c in self._checks))
        return {c.name: ok for c, ok in zip(self._checks, results, strict=True)}

    async def _run(self, check: HealthCheck) -> bool:
        try:
            return await asyncio.wait_for(check.ping(), self._timeout)
        except Exception:
            logger.warning("Health check failed", extra={"event": "health.check_failed", "check": check.name}, exc_info=True)
            return False
