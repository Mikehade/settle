"""Composition root: settings, logging, container, middleware, routers, error handlers.
No business logic and no routes live here."""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.exception_handlers import register_exception_handlers
from src.api.middleware.request_context import RequestContextMiddleware
from src.api.router import api_router
from src.config import get_settings
from src.config.container import Container
from src.shared.logging import configure_logging, get_logger

settings = get_settings()
configure_logging(level=settings.LOG_LEVEL, fmt=settings.LOG_FORMAT, service=settings.APP_NAME, env=settings.APP_ENV)
logger = get_logger(__name__)

# API root used when FastAPI is behind a reverse proxy such as Nginx.
API_ROOT = os.getenv("API_ROOT_PATH", "").strip().rstrip("/")
logger.info(f"API Root: {API_ROOT}")
if API_ROOT and not API_ROOT.startswith("/"):
    API_ROOT = f"/{API_ROOT}"


def create_app() -> FastAPI:
    container = Container()
    # Every module under src.api is wired, so @inject works without a module list.
    container.wire(packages=["src.api"])

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info("Starting", extra={"event": "app.startup", "version": settings.VERSION})
        yield
        await container.database().dispose()
        logger.info("Stopped", extra={"event": "app.shutdown"})

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.VERSION,
        lifespan=lifespan,
        docs_url="/docs" if settings.DOCS_ENABLED else None,
        root_path=API_ROOT,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.DOCS_ENABLED else None,
    )
    app.container = container  # type: ignore[attr-defined]  # tests use app.container.x.override(...)

    # Middleware runs in reverse order of registration: the last added is outermost.
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID"],
        )
    app.add_middleware(
        RequestContextMiddleware,
        access_log=settings.LOG_ACCESS,
        skip_paths=(f"{settings.API_PREFIX}/health",),
    )

    register_exception_handlers(app, expose_errors=settings.DEBUG)
    app.include_router(api_router, prefix=settings.API_PREFIX)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.APP_ENV == "development",
        log_config=None,  # keep our logging configuration
    )
