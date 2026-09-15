"""Authenticated HTTP transport for the verified Frigate 0.17.2 API.

This module is deliberately transport-only: mutation authorization remains in
``FrigateEnrollmentService``.  Keeping that gate above this client ensures a
configured HTTP client cannot bypass ``FRIGATE_ENROLLMENT_ENABLED=false``.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.config import FrigateConfig


class HttpxFrigateTransport:
    """Target-bound Frigate transport with bounded timeouts and reactive login.

    Frigate permits unauthenticated read access in some configurations.  On an
    authentication challenge, credentials supplied only through ``FrigateConfig``
    are exchanged for Frigate's session cookie and the original request is retried
    once.  No credential value is logged or persisted by this class.
    """

    def __init__(self, config: FrigateConfig, *, client: httpx.Client | None = None) -> None:
        parsed = urlparse(config.api_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("FRIGATE_API_URL must be an absolute http(s) URL")
        self._config = config
        self._base_url = config.api_url.rstrip("/") + "/"
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(
                config.http_timeout_seconds,
                connect=config.http_connect_timeout_seconds,
            ),
            verify=config.tls_verify,
            follow_redirects=False,
        )
        self._authenticated = False

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        files: dict | None = None,
    ) -> tuple[int, Any]:
        """Execute one API request, mapping transport failures to stdlib errors."""
        url = self._url(path)
        try:
            response = self._client.request(method, url, json=json, files=files)
            if response.status_code in (401, 403) and not self._authenticated and self._config.auth_configured:
                self._login()
                response = self._client.request(method, url, json=json, files=files)
        except httpx.TimeoutException as exc:
            raise TimeoutError("Frigate request timed out") from exc
        except httpx.HTTPError as exc:
            raise ConnectionError("Frigate HTTP request failed") from exc
        return response.status_code, self._response_body(response)

    def _login(self) -> None:
        """Obtain the Frigate session cookie only after an auth challenge."""
        response = self._client.post(
            self._url("/api/login"),
            json={"user": self._config.auth_username, "password": self._config.auth_password},
        )
        if response.status_code in (401, 403):
            return
        if 200 <= response.status_code < 300:
            self._authenticated = True

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            raise ValueError("Frigate API paths must be absolute")
        return urljoin(self._base_url, path.lstrip("/"))

    @staticmethod
    def _response_body(response: httpx.Response) -> Any:
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            return {"message": response.text}
