import logging
import sys

from src.shared.logging.formatters import ConsoleFormatter, ContextFilter, JsonFormatter

# Third-party loggers routed through our handler instead of their own.
_ADOPTED = ("uvicorn", "uvicorn.error", "sqlalchemy.engine", "alembic")


def configure_logging(*, level: str = "INFO", fmt: str = "json", service: str = "app", env: str = "development") -> None:
    """Configure the root logger once at startup. Safe to call again (replaces handlers)."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if fmt == "json" else ConsoleFormatter(use_color=sys.stdout.isatty()))
    handler.addFilter(ContextFilter(service=service, env=env))

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())

    for name in _ADOPTED:
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    # We emit our own access log (see api/middleware/request_context.py).
    logging.getLogger("uvicorn.access").disabled = True


def get_logger(name: str | None = None) -> logging.Logger:
    """Usage: logger.info("Order created", extra={"event": "order.created", "order_id": id})"""
    return logging.getLogger(name)
