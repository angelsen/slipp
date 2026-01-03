"""Proxy route parsing for CLI specifications."""

from slipp.utils.errors import ProxyRouteError


def parse_proxy_spec(spec: str) -> tuple[str, str, str]:
    """Parse proxy route specification.

    Args:
        spec: Proxy route specification in format 'from@host -> to'

    Returns:
        Tuple of (from_url, to_url, host)

    Raises:
        ProxyRouteError: If spec format is invalid

    Examples:
        >>> parse_proxy_spec("matrix.example.com/api@myserver -> localhost:5173/api")
        ('matrix.example.com/api', 'localhost:5173/api', 'myserver')
    """
    if " -> " not in spec:
        raise ProxyRouteError(
            f"Invalid proxy spec: {spec}\nExpected: from@host -> to"
        )

    from_part, to_url = spec.split(" -> ", 1)

    if "@" not in from_part:
        raise ProxyRouteError(
            f"Missing @host in proxy spec: {spec}\nExpected: from@host -> to"
        )

    from_url, host = from_part.rsplit("@", 1)
    return from_url.strip(), to_url.strip(), host.strip()
