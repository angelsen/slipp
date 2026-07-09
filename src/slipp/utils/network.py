"""Network-related utilities."""

import ipaddress


def is_ip_address(value: str) -> bool:
    """Check whether a string is an IPv4 or IPv6 address."""
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False
