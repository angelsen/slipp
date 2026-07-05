"""slipp - fly.io-like operations CLI for self-hosted infrastructure."""

from dotenv import load_dotenv

__version__ = "0.2.0"

load_dotenv()


def main() -> None:
    """Run the slipp CLI application."""
    from slipp import output
    from slipp.cli import app
    from slipp.utils.errors import SlippError

    try:
        app()
    except SlippError as e:
        output.error(str(e))
        raise SystemExit(1)
