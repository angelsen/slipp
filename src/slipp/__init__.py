"""slipp - fly.io-like operations CLI for self-hosted infrastructure."""

from dotenv import load_dotenv

__version__ = "0.1.0"

load_dotenv()


def main() -> None:
    """Run the slipp CLI application."""
    from slipp.cli import app

    app()
