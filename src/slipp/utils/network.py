"""Network-related utilities."""

import ipaddress


def is_ip_address(value: str) -> bool:
    """Check whether a string is an IPv4 or IPv6 address."""
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def format_app_url(domain: str, *, has_caddy: bool, port: int | None) -> str:
    """Build the public URL hint for a deployed app.

    A real domain with no slipp-managed Caddy is almost always fronted by
    an external proxy (Pangolin, wg-manage, Cloudflare Tunnel) that owns
    port translation on 443 -- only a bare IP target means "connect
    straight to app_port," since there's no TLS-terminating layer that
    could plausibly sit in front of it.
    """
    is_ip = is_ip_address(domain)
    scheme = "http" if is_ip else "https"
    if not has_caddy and is_ip and port is not None:
        return f"{scheme}://{domain}:{port}"
    return f"{scheme}://{domain}"
