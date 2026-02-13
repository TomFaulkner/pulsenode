"""HTTP Tool for PulseNode Agent.

Provides HTTP request capabilities with security controls.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from structlog import get_logger

from pulsenode.agent.agent_config import HttpConfig

logger = get_logger(__name__)


class HttpTool:
    """HTTP tool for making HTTP requests."""

    def __init__(self, config: HttpConfig):
        self.config = config
        self.metrics = {
            "requests": 0,
            "errors": 0,
            "total_duration": 0.0,
        }
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.default_timeout),
                follow_redirects=True,
                verify=False,
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _parse_url(self, url: str) -> tuple[str, str]:
        """Parse URL to extract scheme and host."""
        try:
            parsed = httpx.URL(url)
            return parsed.scheme, parsed.host or ""
        except Exception:
            return "", ""

    def _is_host_allowed(self, url: str) -> tuple[bool, str]:
        """Check if URL host is allowed based on config."""
        _, host = self._parse_url(url)

        if not host:
            return False, "Invalid URL: could not parse host"

        # Check blocked hosts first
        if self.config.blocked_hosts:
            for blocked in self.config.blocked_hosts:
                if blocked in host:
                    return False, f"Host '{host}' is blocked"

        # Check allowed hosts (if specified)
        if self.config.allowed_hosts:
            allowed = False
            for allowed_host in self.config.allowed_hosts:
                if allowed_host in host:
                    allowed = True
                    break
            if not allowed:
                return False, f"Host '{host}' is not in allowed list"

        return True, ""

    async def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: str | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """
        Make an HTTP request.

        Args:
            method: HTTP method (GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS)
            url: Target URL
            headers: Request headers
            body: Request body
            timeout: Request timeout in seconds

        Returns:
            Dict with status, headers, body, and timing info
        """
        start_time = time.time()
        self.metrics["requests"] += 1

        # Validate URL
        allowed, error_msg = self._is_host_allowed(url)
        if not allowed:
            self.metrics["errors"] += 1
            logger.warning("http_request_blocked", url=url, reason=error_msg)
            return {
                "success": False,
                "error": error_msg,
                "status_code": 0,
                "headers": {},
                "body": "",
                "response_time": 0.0,
            }

        client = await self._get_client()
        req_timeout = timeout or self.config.default_timeout

        try:
            response = await client.request(
                method=method.upper(),
                url=url,
                headers=headers,
                content=body.encode() if body else None,
                timeout=httpx.Timeout(req_timeout),
            )

            response_time = time.time() - start_time
            self.metrics["total_duration"] += response_time

            # Parse response body
            try:
                response_body = response.text
            except Exception:
                response_body = "[Binary content]"

            # Convert headers to dict
            resp_headers = dict(response.headers)

            logger.info(
                "http_request_success",
                method=method,
                url=url,
                status=response.status_code,
                duration=response_time,
            )

            return {
                "success": True,
                "status_code": response.status_code,
                "status_text": response.reason_phrase,
                "headers": resp_headers,
                "body": response_body,
                "response_time": response_time,
            }

        except httpx.ReadTimeout as e:
            self.metrics["errors"] += 1
            logger.error("http_read_timeout", url=url, error=str(e))
            return {
                "success": False,
                "error": f"Read timeout: {str(e)}",
                "status_code": 0,
                "headers": {},
                "body": "",
                "response_time": time.time() - start_time,
            }

        except httpx.ConnectTimeout as e:
            self.metrics["errors"] += 1
            logger.error("http_connect_timeout", url=url, error=str(e))
            return {
                "success": False,
                "error": f"Connect timeout: {str(e)}",
                "status_code": 0,
                "headers": {},
                "body": "",
                "response_time": time.time() - start_time,
            }

        except httpx.HTTPError as e:
            self.metrics["errors"] += 1
            logger.error("http_error", url=url, error=str(e))
            return {
                "success": False,
                "error": f"HTTP error: {str(e)}",
                "status_code": 0,
                "headers": {},
                "body": "",
                "response_time": time.time() - start_time,
            }

        except Exception as e:
            self.metrics["errors"] += 1
            logger.error("http_unknown_error", url=url, error=str(e))
            return {
                "success": False,
                "error": f"Request failed: {str(e)}",
                "status_code": 0,
                "headers": {},
                "body": "",
                "response_time": time.time() - start_time,
            }

    async def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Perform GET request."""
        return await self.request("GET", url, headers=headers, timeout=timeout)

    async def post(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        body: str | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Perform POST request."""
        return await self.request(
            "POST", url, headers=headers, body=body, timeout=timeout
        )

    async def put(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        body: str | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Perform PUT request."""
        return await self.request(
            "PUT", url, headers=headers, body=body, timeout=timeout
        )

    async def patch(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        body: str | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Perform PATCH request."""
        return await self.request(
            "PATCH", url, headers=headers, body=body, timeout=timeout
        )

    async def delete(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Perform DELETE request."""
        return await self.request("DELETE", url, headers=headers, timeout=timeout)

    async def head(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Perform HEAD request."""
        return await self.request("HEAD", url, headers=headers, timeout=timeout)

    async def options(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Perform OPTIONS request."""
        return await self.request("OPTIONS", url, headers=headers, timeout=timeout)

    def get_metrics(self) -> dict[str, Any]:
        """Get performance metrics."""
        return self.metrics.copy()
