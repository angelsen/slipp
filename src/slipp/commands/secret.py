"""Secret generation command.

Generates cryptographically secure random secrets for application use.
"""

from typing import Annotated

import typer

from slipp import output
from slipp.services.vault import generate_jwk, generate_secret


def secret_command(
    num_bytes: Annotated[
        int,
        typer.Option("--bytes", "-b", help="Bytes of entropy (default: 32 = 256-bit)"),
    ] = 32,
    base64_encode: Annotated[
        bool, typer.Option("--base64", help="Output as base64 instead of hex")
    ] = False,
    ulid: Annotated[
        bool, typer.Option("--ulid", help="Output as ULID (ignores --bytes)")
    ] = False,
    jwk: Annotated[
        bool, typer.Option("--jwk", help="Output as RSA JWK keypair")
    ] = False,
    bits: Annotated[
        int, typer.Option("--bits", help="RSA key size for --jwk (default: 2048)")
    ] = 2048,
) -> None:
    """Generate a cryptographically secure secret."""
    if jwk:
        secret = generate_jwk(bits)
        output.stdout(secret)
        output.hint(f"RSA-{bits} JWK (private key)")
        return

    encoding = "ulid" if ulid else ("base64" if base64_encode else "hex")
    secret = generate_secret(num_bytes, encoding)
    output.stdout(secret)
    if ulid:
        output.hint("26 char ULID")
    else:
        bits_entropy = num_bytes * 8
        output.hint(f"{len(secret)} {encoding} chars, {bits_entropy}-bit")
