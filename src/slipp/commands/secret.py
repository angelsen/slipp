"""Secret generation command.

Generates cryptographically secure random secrets for application use.
"""

import typer

from slipp import output
from slipp.services.vault import generate_jwk, generate_secret


def secret_command(
    num_bytes: int = typer.Option(
        32, "--bytes", "-b", help="Bytes of entropy (default: 32 = 256-bit)"
    ),
    base64_encode: bool = typer.Option(
        False, "--base64", help="Output as base64 instead of hex"
    ),
    ulid: bool = typer.Option(False, "--ulid", help="Output as ULID (ignores --bytes)"),
    jwk: bool = typer.Option(False, "--jwk", help="Output as RSA JWK keypair"),
    bits: int = typer.Option(
        2048, "--bits", help="RSA key size for --jwk (default: 2048)"
    ),
) -> None:
    """Generate a cryptographically secure secret."""
    if jwk:
        secret = generate_jwk(bits)
        output.stdout(secret)
        output.hint(f"RSA-{bits} JWK (private key)")
    elif ulid:
        secret = generate_secret(encoding="ulid")
        output.stdout(secret)
        output.hint("26 char ULID")
    else:
        encoding = "base64" if base64_encode else "hex"
        secret = generate_secret(num_bytes, encoding)
        bits_entropy = num_bytes * 8
        output.stdout(secret)
        output.hint(f"{len(secret)} {encoding} chars, {bits_entropy}-bit")
