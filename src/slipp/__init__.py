"""slipp - fly.io-like operations CLI for self-hosted infrastructure."""

__version__ = "0.1.0"


def main() -> None:
    """Run the slipp CLI application."""
    from slipp.cli import app

    app()
