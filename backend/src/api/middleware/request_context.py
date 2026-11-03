"""Request ID + access log. Pure ASGI (not BaseHTTPMiddleware) so context vars and
streaming responses behave correctly."""
import re
import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.shared.logging import get_logger
from src.shared.logging.context import request_id_var, user_id_var

logger = get_logger("src.api.access")

_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, *, access_log: bool = True, skip_paths: tuple[str, ...] = ()) -> None:
        self.app = app
        self.access_log = access_log
        self.skip_paths = skip_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope["headers"]).get(b"x-request-id", b"").decode("latin-1")
        request_id = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        # Not reset afterwards on purpose: each request runs in its own task (so nothing leaks),
        # and the 500 handler, which runs outside this middleware, still needs the request id.
        request_id_var.set(request_id)
        user_id_var.set(None)
        status_code = 500
        start = time.perf_counter()

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            path = scope["path"]
            if self.access_log and not path.startswith(self.skip_paths):
                level = 40 if status_code >= 500 else 30 if status_code >= 400 else 20
                logger.log(
                    level,
                    f"{scope['method']} {path} {status_code}",
                    extra={
                        "event": "http.request.completed",
                        "method": scope["method"],
                        "path": path,
                        "status": status_code,
                        "duration_ms": round((time.perf_counter() - start) * 1000, 2),
                    },
                )
