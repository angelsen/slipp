"""Secret generation command.

Generates cryptographically secure random secrets for application use.
"""

import typer

from slipp import output
from slipp.services.vault import generate_secret


def secret_command(
    num_bytes: int = typer.Option(
        32, "--bytes", "-b", help="Bytes of entropy (default: 32 = 256-bit)"
    ),
    base64_encode: bool = typer.Option(
        False, "--base64", help="Output as base64 instead of hex"
    ),
    ulid: bool = typer.Option(False, "--ulid", help="Output as ULID (ignores --bytes)"),
) -> None:
    """Generate a cryptographically secure secret.

    Args:
        num_bytes: Bytes of entropy for random generation. Defaults to 32 (256-bit).
        base64_encode: If True, output as base64; otherwise output as hex.
        ulid: If True, output as ULID format (ignores num_bytes).
    """
    if ulid:
        secret = generate_secret(encoding="ulid")
        output.text(secret)
        output.hint("26 char ULID")
    else:
        encoding = "base64" if base64_encode else "hex"
        secret = generate_secret(num_bytes, encoding)
        bits = num_bytes * 8
        output.text(secret)
        output.hint(f"{len(secret)} {encoding} chars, {bits}-bit")
