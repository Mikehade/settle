"""
Low-level PayPal HTTP client.

Owns the OAuth2 client-credentials token (fetched lazily, cached until
just before expiry) and a thin `request()` that attaches the bearer
token and raises a typed error on failure. httpx uses `trust_env=True`
so it honours the sandbox's outbound proxy automatically.
"""
import time
from typing import Any

import httpx

from src.domain.exceptions import ServiceUnavailableError
from src.shared.errors import ErrorCode
from src.shared.logging import get_logger

logger = get_logger(__name__)


class PayPalHttpClient:
    def __init__(self, *, client_id: str, client_secret: str, base_url: str, timeout: float = 30.0) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._token: str | None = None
        self._token_exp: float = 0.0

    def _ensure_configured(self) -> None:
        if not self._client_id or not self._client_secret:
            raise ServiceUnavailableError(
                ErrorCode.COMMON_SERVICE_UNAVAILABLE,
                "PayPal is not configured — set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET.",
            )

    async def _get_token(self) -> str:
        now = time.monotonic()
        if self._token and now < self._token_exp:
            return self._token
        self._ensure_configured()
        async with httpx.AsyncClient(timeout=self._timeout, trust_env=True) as client:
            resp = await client.post(
                f"{self._base_url}/v1/oauth2/token",
                data={"grant_type": "client_credentials"},
                auth=(self._client_id, self._client_secret),
                headers={"Accept": "application/json"},
            )
        if resp.status_code != 200:
            logger.error("PayPal token failed", extra={"event": "paypal.token_error", "status": resp.status_code})
            raise ServiceUnavailableError(ErrorCode.COMMON_SERVICE_UNAVAILABLE, "Could not authenticate with PayPal")
        payload = resp.json()
        self._token = payload["access_token"]
        # Refresh 60s before the real expiry.
        self._token_exp = now + max(0, int(payload.get("expires_in", 3200)) - 60)
        logger.info("PayPal token acquired", extra={"event": "paypal.token_ok"})
        return self._token

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        token = await self._get_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"}
        if extra_headers:
            headers.update(extra_headers)
        url = f"{self._base_url}{path}"
        async with httpx.AsyncClient(timeout=self._timeout, trust_env=True) as client:
            resp = await client.request(method, url, json=json, params=params, headers=headers)
        if resp.status_code >= 400:
            body = resp.text
            logger.error("PayPal API error", extra={"event": "paypal.api_error", "status": resp.status_code, "path": path, "body": body[:500]})
            raise ServiceUnavailableError(
                ErrorCode.COMMON_SERVICE_UNAVAILABLE,
                f"PayPal {method} {path} failed with {resp.status_code}",
            )
        if resp.status_code == 204 or not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError:
            return {"raw": resp.text}
