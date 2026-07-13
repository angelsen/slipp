"""Secret generation command.

Generates cryptographically secure random secrets for application use.
"""

from slipp import output
from slipp.commands.common import (
    BitsOption,
    EncodingOption,
    JwkOption,
    NumBytesOption,
    describe_secret,
    validate_num_bytes_encoding,
)
from slipp.constants import SecretEncoding
from slipp.services.vault import generate_jwk, generate_secret


def secret_command(
    num_bytes: NumBytesOption = 32,
    encoding: EncodingOption = SecretEncoding.hex,
    jwk: JwkOption = False,
    bits: BitsOption = 2048,
) -> None:
    """Generate a cryptographically secure secret."""
    if jwk:
        secret = generate_jwk(bits)
        output.stdout(secret)
        output.hint(describe_secret(secret, encoding, num_bytes, jwk=True, bits=bits))
        return

    validate_num_bytes_encoding(num_bytes, encoding)
    secret = generate_secret(num_bytes, encoding)
    output.stdout(secret)
    output.hint(describe_secret(secret, encoding, num_bytes))
