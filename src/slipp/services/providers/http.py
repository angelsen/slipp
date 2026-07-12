"""Shared httpx request/error handling for provider API clients."""

from typing import Any

import httpx

from slipp.utils.errors import ProviderError


def api_request(
    client: httpx.Client,
    provider: str,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Issue a request and return the parsed JSON body.

    Args:
        client: Configured httpx client (base_url, auth headers).
        provider: Human-readable provider name for error messages
            (e.g. "Gigahost", "Pangolin").

    Raises:
        ProviderError: On any HTTP error status or network failure.
    """
    try:
        response = client.request(method, path, params=params, json=json)
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        detail = _extract_error_message(e.response)
        raise ProviderError(
            f"{provider} API error ({e.response.status_code}) on {method} {path}: {detail}"
        ) from e
    except httpx.RequestError as e:
        raise ProviderError(
            f"Network error calling {provider} API ({method} {path}): {e}"
        ) from e

    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {}


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
