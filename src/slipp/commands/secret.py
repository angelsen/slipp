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
    generate_secret_value,
)
from slipp.constants import SecretEncoding


def secret_command(
    num_bytes: NumBytesOption = 32,
    encoding: EncodingOption = SecretEncoding.hex,
    jwk: JwkOption = False,
    bits: BitsOption = 2048,
) -> None:
    """Generate a cryptographically secure secret."""
    secret = generate_secret_value(num_bytes, encoding, jwk=jwk, bits=bits)
    output.stdout(secret)
    output.hint(describe_secret(secret, encoding, num_bytes, jwk=jwk, bits=bits))
