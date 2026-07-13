"""Cryptographically secure secret generation."""

import base64
import os

from slipp.constants import SecretEncoding


def generate_secret(
    num_bytes: int = 32, encoding: SecretEncoding = SecretEncoding.hex
) -> str:
    """Generate cryptographically secure secret.

    Args:
        num_bytes: Number of bytes of entropy (default: 32 = 256-bit)
        encoding: Output encoding - hex, base64, or ulid

    Returns:
        Secret string in specified encoding

    Examples:
        >>> generate_secret()  # 64 hex chars (256-bit)
        >>> generate_secret(16)  # 32 hex chars (128-bit)
        >>> generate_secret(32, SecretEncoding.base64)  # 43 base64 chars (256-bit)
        >>> generate_secret(encoding=SecretEncoding.ulid)  # 26 char ULID
    """
    if encoding == SecretEncoding.ulid:
        from ulid import ULID

        return str(ULID())

    raw_bytes = os.urandom(num_bytes)

    if encoding == SecretEncoding.base64:
        return base64.b64encode(raw_bytes).decode("ascii")
    else:
        return raw_bytes.hex()


def generate_jwk(bits: int = 2048) -> str:
    """Generate RSA keypair as JWK JSON.

    Args:
        bits: RSA key size (default: 2048)

    Returns:
        JSON string containing private JWK (includes public components)

    Examples:
        >>> generate_jwk()  # 2048-bit RSA
        >>> generate_jwk(4096)  # 4096-bit RSA
    """
    from jwcrypto import jwk

    key = jwk.JWK.generate(
        kty="RSA",
        size=bits,
        alg="RS256",
        use="sig",
        kid=f"key-{generate_secret(4, SecretEncoding.hex)}",
    )
    return key.export_private()
