"""JSON (staging/production) and console (development) formatters."""
import json
import logging
import traceback
from datetime import UTC, datetime
from typing import Any

from src.shared.logging.context import request_id_var, user_id_var

REDACTED = "***"
SENSITIVE_KEYS = {
    "password", "new_password", "hashed_password", "token", "access_token", "refresh_token",
    "authorization", "secret", "secret_key", "api_key", "cookie", "set-cookie",
}

# Attributes every LogRecord has; anything else came from `extra=`.
_STANDARD_ATTRS = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {"message", "asctime"}
_RESERVED = {"event", "color_message"}


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: REDACTED if str(k).lower() in SENSITIVE_KEYS else redact(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value


def _extras(record: logging.LogRecord) -> dict[str, Any]:
    return {
        k: v for k, v in vars(record).items()
        if k not in _STANDARD_ATTRS and k not in _RESERVED and not k.startswith("_")
    }


class ContextFilter(logging.Filter):
    """Adds service/env and request context to every record."""

    def __init__(self, service: str, env: str) -> None:
        super().__init__()
        self.service = service
        self.env = env

    def filter(self, record: logging.LogRecord) -> bool:
        record._service = self.service
        record._env = self.env
        record._request_id = request_id_var.get()
        record._user_id = user_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", None) or "log",
            "message": record.getMessage(),
            "service": getattr(record, "_service", None),
            "env": getattr(record, "_env", None),
        }
        if rid := getattr(record, "_request_id", None):
            payload["request_id"] = rid
        if uid := getattr(record, "_user_id", None):
            payload["user_id"] = uid
        payload.update(redact(_extras(record)))
        if record.exc_info and record.exc_info[0] is not None:
            exc_type, exc, tb = record.exc_info
            payload["exc_type"] = exc_type.__name__
            payload["exc_message"] = str(exc)
            payload["stack"] = "".join(traceback.format_exception(exc_type, exc, tb))
        return json.dumps(payload, default=str, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    COLORS = {"DEBUG": "\033[36m", "INFO": "\033[32m", "WARNING": "\033[33m", "ERROR": "\033[31m", "CRITICAL": "\033[41m"}
    RESET, DIM = "\033[0m", "\033[2m"

    def __init__(self, use_color: bool = True) -> None:
        super().__init__()
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S.%f")[:-3]
        level = record.levelname.ljust(8)
        if self.use_color:
            level = f"{self.COLORS.get(record.levelname, '')}{level}{self.RESET}"
        fields = redact(_extras(record))
        if event := getattr(record, "event", None):
            fields = {"event": event, **fields}
        if rid := getattr(record, "_request_id", None):
            fields["req"] = rid[:12]
        tail = " ".join(f"{k}={v}" for k, v in fields.items())
        if tail and self.use_color:
            tail = f"{self.DIM}{tail}{self.RESET}"
        line = f"{ts} {level} {record.name}: {record.getMessage()}" + (f"  {tail}" if tail else "")
        if record.exc_info and record.exc_info[0] is not None:
            line += "\n" + self.formatException(record.exc_info)
        return line
