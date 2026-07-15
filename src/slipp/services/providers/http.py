"""Shared httpx request/error handling for provider API clients."""

from types import TracebackType
from typing import Any

import httpx

from slipp.utils.errors import ProviderError


class ApiClientMixin:
    """Shared `_request` for provider clients wrapping an httpx.Client.

    Subclasses set `PROVIDER_NAME` (used in error messages) and `self._client`
    (a configured httpx.Client) in their own `__init__`. Usable as a context
    manager to close the underlying connection pool deterministically.
    """

    PROVIDER_NAME: str
    _client: httpx.Client

    def close(self) -> None:
        """Close the underlying httpx.Client's connection pool."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Issue a request and return the parsed JSON body.

        Raises:
            ProviderError: On any HTTP error status or network failure.
        """
        try:
            response = self._client.request(method, path, params=params, json=json)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            detail = _extract_error_message(e.response)
            raise ProviderError(
                f"{self.PROVIDER_NAME} API error ({e.response.status_code}) "
                f"on {method} {path}: {detail}"
            ) from e
        except httpx.RequestError as e:
            raise ProviderError(
                f"Network error calling {self.PROVIDER_NAME} API ({method} {path}): {e}"
            ) from e

        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            return {}

    def _request_data(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        default: Any,
    ) -> Any:
        """`_request` plus unwrapping the `{"data": ...}` envelope every endpoint here uses.

        Collapses the `result = self._request(...); return result.get("data", default)`
        pair repeated at nearly every provider client call site into one line.
        """
        result = self._request(method, path, params=params, json=json)
        return result.get("data", default)


def _extract_error_message(response: httpx.Response) -> str:
    """Pull a human-readable message out of an error response body."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:200] or response.reason_phrase

    if isinstance(body, dict):
        for key in ("message", "error"):
            value = body.get(key)
            if value:
                return str(value)
    return response.text[:200] or response.reason_phrase
